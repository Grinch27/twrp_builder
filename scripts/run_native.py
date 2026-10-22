#!/usr/bin/env python3
# Requirements: native build with private logs, live numeric heartbeats and timing.
# Ambiguity: native execution has no Docker memory limit or filesystem isolation.
# Research: preserve host HOME unchanged; omit CI credentials from the build child.
# Optimization: bounded log samples; upload progress only at phase transitions.
# Risks: leaked output, inherited credentials, stale work and orphaned build groups.
# Validation: numeric-only metrics, no source leakage, real exit and group cleanup.
"""Run a native build while keeping compiler output out of public Actions logs."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from build_telemetry import sample

ENVIRONMENT = {'PATH', 'HOME', 'USER', 'LOGNAME', 'SHELL', 'LANG', 'LC_ALL', 'TZ', 'TERM'}


def build_environment(parent, builder, work):
    # Values such as HOME are inherited unchanged; no host configuration is changed.
    result = {key: value for key, value in parent.items() if key in ENVIRONMENT}
    result.update(BUILDER_SELF=str(builder), BUILD_ROOT=str(work), GIT_TERMINAL_PROMPT='0')
    return result


class Interrupted(Exception):
    def __init__(self, signum):
        self.status = 128 + signum


def stop_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def run_build(builder, work, checkpoint=None, interval=15, heartbeat=60):
    builder, work = Path(builder).resolve(), Path(work).resolve()
    (work / 'logs').mkdir(exist_ok=True)
    (work / 'output').mkdir(exist_ok=True)
    started = time.monotonic()
    last_stage, last_heartbeat = None, started - heartbeat

    def emit(force=False):
        nonlocal last_stage, last_heartbeat
        try:
            stage, metrics = sample(work, started)
        except (OSError, ValueError, TypeError):
            print('Restricted build telemetry unavailable.', flush=True)
            return
        now = time.monotonic()
        changed = stage != last_stage
        if changed or force or now - last_heartbeat >= heartbeat:
            if changed:
                print('Build stage: ' + stage, flush=True)
            print('BUILD_METRICS ' + json.dumps({'stage': stage, **metrics}, sort_keys=True), flush=True)
            last_heartbeat = now
        last_stage = stage
        if changed and not force:
            report()

    def report():
        if checkpoint is not None:
            try:
                checkpoint()
            except (OSError, ValueError, TypeError, subprocess.SubprocessError):
                print('Restricted progress checkpoint unavailable.', flush=True)

    def interrupt(signum, frame):
        raise Interrupted(signum)

    descriptor = os.open(work / 'logs/native.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as log:
        process = subprocess.Popen(
            ['bash', str(builder / 'scripts/build.sh')], cwd=work,
            env=build_environment(os.environ, builder, work),
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
        handlers = {s: signal.signal(s, interrupt) for s in (signal.SIGINT, signal.SIGTERM)}
        try:
            while process.poll() is None:
                emit()
                time.sleep(interval)
            result = process.wait()
        finally:
            stop_group(process)
            for signum, handler in handlers.items():
                signal.signal(signum, handler)
            emit(force=True)
            report()
    result = 128 - result if result < 0 else result
    print('Native build exit: ' + str(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    builder = Path(__file__).resolve().parents[1]
    if not args.work.is_dir() or args.work.resolve() == builder:
        raise ValueError('native paths unavailable')

    def checkpoint():
        subprocess.run([sys.executable, str(builder / 'scripts/report_progress.py'),
                        '--work', str(args.work)], check=False, timeout=180)

    return run_build(builder, args.work, checkpoint)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Interrupted as error:
        sys.exit(error.status)
    except (OSError, ValueError, subprocess.SubprocessError):
        print('Native build launcher failed.', file=sys.stderr)
        sys.exit(1)
