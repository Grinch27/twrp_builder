#!/usr/bin/env python3
# Requirements: clean only the recorded native build session within 175 seconds.
# Ambiguity: GitHub's built-in Complete job has no per-step YAML timeout.
# Research: use Linux proc stat, never read process environments or command lines.
# Optimization: TERM grace then KILL; bounded polling of this build session only.
# Risks: PID reuse, killing unrelated groups, uninterruptible kernel processes.
# Validation: session/start-time guards, stale records, real stubborn-child cleanup.
"""Bounded cleanup of a native build session; not a Runner finalization timeout."""

import argparse
import json
import os
from pathlib import Path
import signal
import sys
import time


def process_info(pid):
    try:
        text = Path(f'/proc/{pid}/stat').read_text()
        fields = text[text.rfind(')') + 2:].split()
        return {'state': fields[0], 'group': os.getpgid(pid),
                'session': os.getsid(pid), 'start': int(fields[19])}
    except (OSError, ValueError, IndexError):
        return None


def remember_group(work, pid):
    info = process_info(pid)
    if info is None or info['group'] != pid or info['session'] != pid:
        raise ValueError('native session identity unavailable')
    target = Path(work) / 'output/native-session.json'
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump({'group': pid, 'start': info['start']}, stream)


def live_members(group, started):
    # The session leader's original start time prevents a reused PID being targeted.
    leader = process_info(group)
    if leader is not None and leader['start'] != started:
        raise ValueError('native session identity changed')
    result = []
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal():
            continue
        info = process_info(int(path.name))
        if info is not None and info['group'] == group:
            if info['session'] != group or info['start'] < started:
                raise ValueError('native session membership changed')
            if info['state'] not in {'Z', 'X'}:
                result.append(int(path.name))
    return result


def cleanup_group(group, started, timeout=170, grace=20):
    if (type(group) is not int or type(started) is not int or group <= 1
            or started <= 0 or group == os.getpgrp()):
        raise ValueError('invalid native session identity')
    deadline = time.monotonic() + timeout
    if not live_members(group, started):
        return True
    try:
        os.killpg(group, signal.SIGTERM)
    except ProcessLookupError:
        return True
    kill_at = min(deadline, time.monotonic() + grace)
    killed = False
    while time.monotonic() < deadline:
        if not live_members(group, started):
            return True
        if not killed and time.monotonic() >= kill_at:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                return True
            killed = True
        time.sleep(min(0.2, max(0, deadline - time.monotonic())))
    return False


def cleanup_work(work):
    path = Path(work) / 'output/native-session.json'
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except FileNotFoundError:
        return True
    with os.fdopen(descriptor) as stream:
        value = json.loads(stream.read(256))
    if set(value) != {'group', 'start'}:
        raise ValueError('invalid native session record')
    return cleanup_group(value['group'], value['start'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    args = parser.parse_args()
    if (os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'):
        raise ValueError('cleanup requires this campaign disposable hosted runner')
    done = cleanup_work(args.work)
    print('Native session cleanup: ' + ('complete.' if done else 'time budget exhausted; skipped.'))
    return 0 if done else 124


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError):
        print('Native session cleanup unavailable; skipped.', file=sys.stderr)
        sys.exit(1)
