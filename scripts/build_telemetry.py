#!/usr/bin/env python3
# Requirements: expose numeric build progress, timing and host resource information.
# Ambiguity: Ninja percentages describe the current batch, not the entire build.
# Research: private log text must never be returned by the telemetry parser.
# Optimization: inspect at most 256 KiB per log sample and emit bounded records.
# Risks: credential/source disclosure, malformed counters and misleading progress.
# Validation: fixed stages, numeric allowlists, atomic records and privacy tests.
"""Collect restricted build telemetry without returning raw log lines."""

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import time

STAGES = {'initialization', 'repo_tool', 'repo_initialization', 'repo_tool_verification',
          'source_sync', 'checkout_verification', 'public_resources', 'preflight', 'compile',
          'static_validation', 'complete'}
LIMIT = 256 * 1024
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
REPO = re.compile(r'(?:^|[\r\n])\s*(Fetching|Checking out|Syncing):\s*\d{1,3}%\s*\((\d{1,7})/(\d{1,7})\)')
NINJA = re.compile(r'(?:^|[\r\n])\s*\[\s*(?:\d{1,3}%\s+)?(\d{1,9})/(\d{1,9})\]')
NUMERIC = {'elapsed_seconds', 'stage_elapsed_seconds', 'disk_free_mib',
           'memory_available_mib', 'swap_free_mib', 'load_1m', 'log_bytes',
           'log_idle_seconds'}


def number(value, maximum=10**12):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and 0 <= value <= maximum and math.isfinite(value))


def sanitize_metrics(value):
    if not isinstance(value, dict):
        return {}
    result = {key: value[key] for key in NUMERIC if number(value.get(key))}
    progress = value.get('progress')
    if (isinstance(progress, dict) and isinstance(progress.get('kind'), str)
            and progress['kind'] in {'fetch', 'checkout', 'sync', 'ninja'}):
        done, total = progress.get('completed'), progress.get('total')
        maximum = 10**7 if progress['kind'] == 'ninja' else 10000
        if (isinstance(done, int) and not isinstance(done, bool)
                and isinstance(total, int) and not isinstance(total, bool)
                and 0 <= done <= total <= maximum and total > 0):
            result['progress'] = {'kind': progress['kind'], 'completed': done,
                                  'total': total, 'percent': round(100 * done / total, 1)}
    timings = value.get('stage_seconds')
    if isinstance(timings, dict):
        result['stage_seconds'] = {key: value for key, value in timings.items()
                                   if key in STAGES and number(value, 7 * 86400)}
    return result


def read_json(path, default=None):
    try:
        if path.is_symlink() or path.stat().st_size > LIMIT:
            return default
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def write_json(path, value):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def set_stage(work, stage, exit_code=None, now=None):
    if not isinstance(stage, str) or stage not in STAGES or (exit_code is not None and
            (not isinstance(exit_code, int) or isinstance(exit_code, bool)
             or not 0 <= exit_code <= 255)):
        raise ValueError('invalid stage record')
    now = time.monotonic() if now is None else now
    if not number(now):
        raise ValueError('invalid stage clock')
    output = Path(work) / 'output'
    previous = read_json(output / 'status.json', {})
    previous = previous if isinstance(previous, dict) else {}
    timings = read_json(output / 'stage-timings.json', {})
    timings = sanitize_metrics({'stage_seconds': timings}).get('stage_seconds', {})
    before = previous.get('stage')
    started = previous.get('started_monotonic')
    if isinstance(before, str) and before in STAGES and number(started) and now >= started:
        if before != stage or exit_code is not None:
            timings[before] = round(now - started, 3)
    status = {'stage': stage, 'started_monotonic':
              started if before == stage and number(started) and started <= now else now}
    if exit_code is not None:
        status['exit_code'] = exit_code
    write_json(output / 'stage-timings.json', timings)
    write_json(output / 'status.json', status)


def progress_counts(text, stage):
    text = ANSI.sub('', text)
    if stage == 'source_sync':
        matches = list(REPO.finditer(text))
        if matches:
            match = matches[-1]
            kind = {'Fetching': 'fetch', 'Checking out': 'checkout', 'Syncing': 'sync'}[match[1]]
            candidate = {'kind': kind, 'completed': int(match[2]), 'total': int(match[3])}
            return sanitize_metrics({'progress': candidate}).get('progress')
    elif stage == 'compile':
        matches = list(NINJA.finditer(text))
        if matches:
            match = matches[-1]
            candidate = {'kind': 'ninja', 'completed': int(match[1]), 'total': int(match[2])}
            return sanitize_metrics({'progress': candidate}).get('progress')
    return None


def memory_mib(path=Path('/proc/meminfo')):
    try:
        text = path.read_text()
    except OSError:
        return {}
    fields = {'MemAvailable': 'memory_available_mib', 'SwapFree': 'swap_free_mib'}
    result = {}
    for key, value in re.findall(r'^(MemAvailable|SwapFree):\s*(\d{1,15})\s+kB$', text, re.M):
        result[fields[key]] = int(value) // 1024
    return result


def sample(work, started, now=None):
    now = time.monotonic() if now is None else now
    work = Path(work)
    status = read_json(work / 'output/status.json', {})
    status = status if isinstance(status, dict) else {}
    stage = status.get('stage')
    if not isinstance(stage, str) or stage not in STAGES:
        stage = 'initialization'
    result = {'elapsed_seconds': round(max(0, now - started), 1)}
    phase_start = status.get('started_monotonic')
    if number(phase_start) and phase_start <= now:
        result['stage_elapsed_seconds'] = round(now - phase_start, 1)
    try:
        result['disk_free_mib'] = shutil.disk_usage(work).free // 1024**2
        result['load_1m'] = round(os.getloadavg()[0], 2)
    except OSError:
        pass
    result.update(memory_mib())
    result['stage_seconds'] = read_json(work / 'output/stage-timings.json', {})
    filename = {'source_sync': 'repo-sync.log', 'repo_initialization': 'repo-init.log',
                'compile': 'compile.log'}.get(stage, 'native.log')
    log = work / 'logs' / filename
    try:
        if not log.is_symlink():
            with log.open('rb') as stream:
                metadata = os.fstat(stream.fileno())
                stream.seek(max(0, metadata.st_size - LIMIT))
                tail = stream.read(LIMIT).decode('utf-8', errors='replace')
            result.update(log_bytes=metadata.st_size,
                          log_idle_seconds=round(max(0, time.time() - metadata.st_mtime), 1))
            progress = progress_counts(tail, stage)
            if progress:
                result['progress'] = progress
    except OSError:
        pass
    result = sanitize_metrics(result)
    write_json(work / 'output/telemetry.json', result)
    return stage, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--stage', choices=sorted(STAGES), required=True)
    parser.add_argument('--exit-code', type=int)
    args = parser.parse_args()
    set_stage(args.work, args.stage, args.exit_code)


if __name__ == '__main__':
    main()
