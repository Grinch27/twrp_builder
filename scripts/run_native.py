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
import re
import signal
import subprocess
import sys
import time

from build_telemetry import sample
from native_cleanup import remember_group

ENVIRONMENT = {'PATH', 'HOME', 'USER', 'LOGNAME', 'SHELL', 'LANG', 'LC_ALL', 'TZ', 'TERM'}


def build_environment(parent, builder, work):
    # Values such as HOME are inherited unchanged; no host configuration is changed.
    result = {key: value for key, value in parent.items() if key in ENVIRONMENT}
    result.update(BUILDER_SELF=str(builder), BUILD_ROOT=str(work), GIT_TERMINAL_PROMPT='0')
    # Public builder identity enables pinned patch proof; credentials remain excluded.
    commit = parent.get('GITHUB_SHA', '')
    if re.fullmatch(r'[0-9a-f]{40}', commit):
        result['GITHUB_SHA'] = commit
    return result


# Command names and descriptions are fixed public literals; the file never contains arguments.
PUBLIC_COMMANDS = {
    "repo_fetch": "curl -fLsS --retry 2 <locked public git-repo launcher> -o <repo>",
    "repo_verify": "sha256sum --check --status <locked git-repo launcher digest>",
    "manifest_compose": "python3 scripts/source_inputs.py compose --manifest <private input> --output <local locked manifest>",
    "manifest_commit": "git init/add/commit <local locked manifest>",
    "repo_init": "timeout 180s repo init --manifest-url=<local manifest> --depth=1 --groups=all --no-clone-bundle --no-use-superproject --repo-rev=<locked>",
    "repo_commit_verify": "git -C .repo/repo rev-parse HEAD == <locked SHA>",
    "repo_sync": "timeout 140m repo sync -c -j4 --no-clone-bundle --no-tags --fail-fast --retry-fetches=2",
    "checkout_verify": "python3 scripts/source_inputs.py checkout --manifest <private input> --source <checkout>",
    "overlay_copy": "cp -a <private reviewed overlay> <checkout>",
    "stock_prebuilts_copy": "cp -a <private reviewed prebuilts> <local work>",
    "testdata_restore": "timeout 6m python3 scripts/restore_public_testdata.py --source <checkout>",
    "recovery_patch_check": "git -C bootable/recovery apply --check patches/recovery-required-modules.patch",
    "recovery_patch_apply": "git -C bootable/recovery apply patches/recovery-required-modules.patch",
    "task_profiles_patch_check": "git -C system/core apply --check patches/native-task-profiles.patch",
    "task_profiles_patch_apply": "git -C system/core apply patches/native-task-profiles.patch",
    "selene_module_patch_check": "git -C device/xiaomi/selene apply --check patches/selene-module-names.patch",
    "selene_module_patch_apply": "git -C device/xiaomi/selene apply patches/selene-module-names.patch",
    "disk_preflight": "df --output=avail -B1 <work> (minimum 18 GiB)",
    "jdk_preflight": "test -s prebuilts/jdk/jdk11/linux-x86/lib/modules",
    "monitor_preflight": "test -s prebuilts/tools/common/m2/repository/.../monitor-1.0.2-alpha1.aar",
    "java_version": "prebuilts/jdk/jdk11/linux-x86/bin/java -version",
    "envsetup_lunch": "source build/envsetup.sh && lunch twrp_selene-eng",
    "bootimage_compile": "timeout 160m bash -c 'source build/envsetup.sh; lunch twrp_selene-eng; mka bootimage -j4'",
    "avb_info": "python3 external/avb/avbtool.py info_image --image <boot.img>",
    "avb_verify": "python3 external/avb/avbtool.py verify_image --image <boot.img> --key <public AVB test key>",
    "boot_static_verify": "python3 scripts/verify_boot.py --image <boot.img> --stock <reviewed stock inputs> --report <private work>",
    "boot_copy": "cp <boot.img> <private output>",
    "cms_seal": "python3 scripts/seal_output.py --output <private output> --certificate delivery-recipient.pem",
}
PUBLIC_TRACE_LIMIT = 8192


def safe_command_events(path, offset=0):
    """Read only reviewed marker IDs; never return source text or dynamic command arguments."""
    import datetime
    import re
    path = Path(path)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as stream:
            size = os.fstat(stream.fileno()).st_size
            if size > PUBLIC_TRACE_LIMIT:
                return [], offset
            content = stream.read(PUBLIC_TRACE_LIMIT)
        if not content.endswith(b'\n'):
            content = content[:content.rfind(b'\n') + 1]
        lines = content.decode('ascii').splitlines()
        if len(lines) > 128 or offset > len(lines):
            return [], offset
        safe = []
        for line in lines[offset:]:
            stamp, separator, identifier = line.partition(' ')
            if not separator or identifier not in PUBLIC_COMMANDS:
                continue
            try:
                datetime.datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%SZ')
            except ValueError:
                continue
            if not re.fullmatch(r'20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', stamp):
                continue
            safe.append((stamp, identifier, PUBLIC_COMMANDS[identifier]))
        return safe, len(lines)
    except (OSError, UnicodeError, ValueError):
        return [], offset


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
        pass
    # The shell can exit before a TERM-resistant grandchild; kill the group anyway.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        print('Native process reap time budget exhausted.', flush=True)


def run_build(builder, work, checkpoint=None, interval=15, heartbeat=60):
    builder, work = Path(builder).resolve(), Path(work).resolve()
    (work / 'logs').mkdir(exist_ok=True)
    (work / 'output').mkdir(exist_ok=True)
    started = time.monotonic()
    last_stage, last_heartbeat = None, started - heartbeat
    command_offset = 0

    def emit(force=False):
        nonlocal last_stage, last_heartbeat, command_offset
        events, command_offset = safe_command_events(work / 'output/command-trace.log', command_offset)
        for stamp, identifier, template in events:
            print(f'BUILD_COMMAND {stamp} [{identifier}] $ {template}', flush=True)
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
            try:
                remember_group(work, process.pid)
            except (OSError, ValueError):
                print('Native session record unavailable; direct group cleanup remains active.', flush=True)
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
