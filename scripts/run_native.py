#!/usr/bin/env python3
# Requirements: run the existing build pipeline directly on a disposable runner.
# Ambiguity: native execution has no Docker memory limit or filesystem isolation.
# Research: preserve host HOME unchanged; omit CI credentials from the build child.
# Optimization: reuse locked source, restricted progress and image validation code.
# Risks: leaked output, inherited credentials, stale work and orphaned build groups.
# Validation: environment allowlist, private exclusive log, real exit and group cleanup.
"""Run a native build while keeping compiler output out of public Actions logs."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from report_progress import STAGES

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


def run_build(builder, work, checkpoint=None, interval=15):
    builder, work = Path(builder).resolve(), Path(work).resolve()
    (work / 'logs').mkdir(exist_ok=True)
    (work / 'output').mkdir(exist_ok=True)

    def report():
        if checkpoint is not None:
            try:
                checkpoint()
            except (OSError, ValueError, subprocess.SubprocessError):
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
            last_stage = None
            while process.poll() is None:
                try:
                    stage = json.loads((work / 'output/status.json').read_text()).get('stage')
                except (OSError, ValueError, AttributeError):
                    stage = None
                if isinstance(stage, str) and stage in STAGES and stage != last_stage:
                    print('Build stage: ' + stage, flush=True)
                    report()
                    last_stage = stage
                time.sleep(interval)
            result = process.wait()
        finally:
            stop_group(process)
            for signum, handler in handlers.items():
                signal.signal(signum, handler)
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
