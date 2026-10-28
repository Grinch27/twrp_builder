#!/usr/bin/env python3
# Requirements: checkpoint aria2 before the job deadline and resume on a fresh runner.
# Ambiguity: a saved checkpoint is not a completed ROM or a successful publication.
# Research: aria2 INT/exit 7, GNU sparse tar and cross-run Actions artifacts.
# Optimization: preserve sparse extents and upload only data, control and metadata.
# Risks: incomplete checkpoints, untrusted archive paths, cancellation and relay loops.
# Validation: synthetic stop/resume, sparse round trips and real Actions relay testing.
"""Bounded download and allowlisted checkpoint handling for the fixed stock ROM."""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import time


PARTIAL = 'rom.tgz.partial'
CONTROL = PARTIAL + '.aria2'
MANIFEST = 'resume.json'
CHECKPOINT = 'stock-rom-relay.tar'
RESERVE = 1024 ** 3


def positive_id(value):
    return bool(re.fullmatch(r'[1-9][0-9]*', value))


def validate_inputs(env):
    """Accept a complete source-artifact pair or an independent new chain."""
    run_id = env.get('RESUME_RUN_ID', '')
    artifact_id = env.get('RESUME_ARTIFACT_ID', '')
    chain = env.get('RELAY_CHAIN', '')
    if run_id or artifact_id:
        if not all(positive_id(value) for value in (run_id, artifact_id, chain)):
            raise ValueError('Resume requires positive run, artifact and chain IDs')
    elif chain:
        raise ValueError('A new chain must not specify relay_chain')
    return bool(run_id)


def github_json(endpoint):
    return json.loads(subprocess.check_output(['gh', 'api', endpoint], text=True))


def prepare(env):
    """Check space and ensure a resumed artifact belongs to a trusted main run."""
    resume = validate_inputs(env)
    if not 1 <= int(env['RELAY_SECONDS']) <= 19800:
        raise ValueError('Relay window must leave at least 30 minutes before six hours')
    if int(env['MAX_RELAY_ROUNDS']) < 2:
        raise ValueError('MAX_RELAY_ROUNDS must allow at least two rounds')
    if shutil.disk_usage(env['ROM_WORK']).free < 12 * RESERVE:
        raise ValueError('At least 12 GiB free is required for data and checkpoint copies')
    if not resume:
        return
    repo = env['GITHUB_REPOSITORY']
    run_id = env['RESUME_RUN_ID']
    run = github_json(f'repos/{repo}/actions/runs/{run_id}')
    if (str(run['id']) != run_id or run['head_branch'] != 'main'
            or run['event'] not in ('push', 'workflow_dispatch')
            or run['path'] != '.github/workflows/stock_rom.yml'
            or run['head_repository']['full_name'] != repo):
        raise ValueError('Checkpoint source must be this stock workflow on main')
    artifact = github_json(f"repos/{repo}/actions/artifacts/{env['RESUME_ARTIFACT_ID']}")
    if (artifact['expired'] or str(artifact['workflow_run']['id']) != run_id
            or artifact['name'] != f"stock-rom-relay-{run_id}-{run['run_attempt']}"):
        raise ValueError('Checkpoint artifact does not belong to the specified run/attempt')


def restore(archive, work, env, state):
    """Validate the tiny allowlist before extracting, preserving sparse holes."""
    expected = {MANIFEST, 'rom.tgz'} if state == 'complete' else {MANIFEST, PARTIAL, CONTROL}
    with tarfile.open(archive, 'r:') as source:
        members = []
        names = set()
        for member in source:
            if (member.name not in expected or member.name in names
                    or not member.isfile() or member.size <= 0):
                raise ValueError('Unexpected, duplicate or non-regular checkpoint member')
            if member.size > (8 * RESERVE if member.name in (PARTIAL, 'rom.tgz') else 1024 ** 2):
                raise ValueError('Checkpoint member exceeds its size bound')
            members.append(member)
            names.add(member.name)
        if names != expected:
            raise ValueError('Checkpoint is missing its data, control or metadata')
        manifest_member = next(member for member in members if member.name == MANIFEST)
        if manifest_member.size > 16384:
            raise ValueError('Oversized checkpoint metadata')
        metadata = json.load(source.extractfile(manifest_member))
        if (metadata.get('schema') != 1 or metadata.get('state') != state
                or metadata.get('url') != env['ROM_URL']
                or metadata.get('rom_version') != env['ROM_VERSION']
                or metadata.get('chain') != env['RELAY_CHAIN']
                or metadata.get('run_id') != env['RESUME_RUN_ID']
                or type(metadata.get('round')) is not int or metadata['round'] < 1):
            raise ValueError('Checkpoint metadata does not match this download chain')
        data_name = 'rom.tgz' if state == 'complete' else PARTIAL
        data_member = next(member for member in members if member.name == data_name)
        if metadata.get('apparent_bytes') != data_member.size:
            raise ValueError('Checkpoint data length differs from its metadata')
        if any((work / name).exists() or (work / name).is_symlink() for name in expected):
            raise ValueError('Refusing to overwrite existing checkpoint data')
        if shutil.disk_usage(work).free < data_member.size + RESERVE:
            raise ValueError('Insufficient space to restore checkpoint')
        source.extractall(work, members=members, filter='data')
    archive.unlink()
    print(f"Restored {state} checkpoint: chain={metadata['chain']}, "
          f"previous_run={metadata['run_id']}, round={metadata['round']}", flush=True)
    return metadata


def pack(work, metadata):
    """Pack a stopped process's files, never the work directory or event log."""
    names = [MANIFEST, 'rom.tgz'] if metadata['state'] == 'complete' else [MANIFEST, PARTIAL, CONTROL]
    (work / MANIFEST).write_text(json.dumps(metadata, indent=2) + '\n')
    for name in names:
        path = work / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
            raise ValueError(f'Missing regular checkpoint file: {name}')
    needed = sum((work / name).stat().st_blocks * 512 for name in names) + RESERVE
    if shutil.disk_usage(work).free < needed:
        raise ValueError('Insufficient space to package checkpoint')
    archive = work / CHECKPOINT
    subprocess.run(['tar', '--sparse', '--format=pax', '-cf', str(archive),
                    '-C', str(work), *names], check=True)
    print(f'Checkpoint archive bytes: {archive.stat().st_size}', flush=True)
    return archive


def aria2_args(work, url):
    return [
        'aria2c', '--no-conf=true', '--no-netrc=true', '--enable-rpc=false',
        '--max-concurrent-downloads=1', '--max-connection-per-server=16', '--split=16',
        '--min-split-size=1M', '--continue=true', '--auto-save-interval=5',
        '--file-allocation=none', '--auto-file-renaming=false', '--allow-overwrite=false',
        '--always-resume=true', '--connect-timeout=30', '--timeout=60',
        '--max-tries=3', '--retry-wait=5', '--max-download-limit=0',
        '--max-overall-download-limit=0', '--follow-torrent=false', '--follow-metalink=false',
        '--console-log-level=info', '--log-level=info', '--summary-interval=5',
        '--show-console-readout=true', '--truncate-console-readout=false',
        '--human-readable=true', '--download-result=full', '--enable-color=false',
        f'--log={work}/aria2-download.log', f'--dir={work}', f'--out={PARTIAL}', url,
    ]


def wait_download(command, seconds):
    """Return the real aria2 exit code and whether our deadline sent INT."""
    with subprocess.Popen(command) as process:
        try:
            return process.wait(timeout=seconds), False
        except subprocess.TimeoutExpired:
            print('Relay deadline reached; sending SIGINT and waiting for aria2.', flush=True)
            try:
                process.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                return process.wait(timeout=60), True
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise RuntimeError('aria2 did not stop cleanly; checkpoint will not be uploaded')


def summary(text):
    """Display failures here must not replace the downloader's real exit code."""
    path = os.environ.get('GITHUB_STEP_SUMMARY')
    if path:
        try:
            with open(path, 'a') as target:
                target.write(text)
        except OSError as error:
            print(f'Unable to append Job Summary: {error}', file=sys.stderr)


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def disk_info(work):
    try:
        subprocess.run(['df', '-h', str(work)], check=False)
    except OSError as error:
        print(f'Unable to display disk information: {error}', file=sys.stderr)


def download(env):
    """Resume or start one bounded round and produce a paused/complete artifact."""
    work = Path(env['ROM_WORK'])
    previous = None
    previous_control = None
    if validate_inputs(env):
        previous = restore(work / 'incoming' / CHECKPOINT, work, env, 'paused')
        previous_control = (work / CONTROL).read_bytes()
    round_number = previous['round'] + 1 if previous else 1
    chain = previous['chain'] if previous else env['GITHUB_RUN_ID']
    remaining = float(env['RELAY_JOB_STARTED']) + int(env['RELAY_SECONDS']) - time.time()
    if remaining <= 0:
        raise ValueError('Preparation/restoration exhausted the relay window')
    command = aria2_args(work, env['ROM_URL'])
    started = utc_now()
    started_seconds = time.monotonic()
    print(f'Download started (UTC): {started}\nSource URL: {env["ROM_URL"]}\n'
          f'Output directory: {work}\nChain: {chain}; round: {round_number}\n'
          f'Remaining job download budget: {remaining:.1f} seconds\n'
          'Progress: completed/total (%), CN=connections, DL=speed, ETA=time remaining.\n'
          f'Effective command: {shlex.join(command)}', flush=True)
    disk_info(work)
    code, deadline_reached = wait_download(command, remaining)
    finished = utc_now()
    elapsed = time.monotonic() - started_seconds
    partial = work / PARTIAL
    try:
        apparent = partial.stat().st_size if partial.is_file() else 'unknown'
    except OSError:
        apparent = 'unknown'
    print(f'Download finished (UTC): {finished}\naria2 exit code: {code}\n'
          f'Elapsed seconds: {elapsed:.1f}\nLocal apparent file bytes: {apparent}\n'
          f'Event log: {work}/aria2-download.log', flush=True)
    disk_info(work)
    summary('### aria2 official ROM relay\n\n'
            f'| Field | Value |\n| --- | --- |\n| Source | {env["ROM_URL"]} |\n'
            f'| Chain / round | {chain} / {round_number} |\n| Connections / splits | 16 / 16 |\n'
            f'| Started UTC | {started} |\n| Finished UTC | {finished} |\n'
            f'| aria2 exit code | {code} |\n| Elapsed seconds | {elapsed:.1f} |\n'
            f'| Local apparent bytes | {apparent} |\n| Planned deadline | {deadline_reached} |\n\n'
            'Apparent length is not completed byte count. INFO logs stay on this runner.\n\n')
    if code == 0:
        if not partial.is_file() or (work / CONTROL).exists():
            raise ValueError('aria2 success is missing a complete output file')
        if (work / 'rom.tgz').exists():
            raise ValueError('Refusing to overwrite a completed ROM')
        partial.rename(work / 'rom.tgz')
        state = 'complete'
        progressed = True
    elif code == 7 and deadline_reached:
        if not partial.is_file() or not (work / CONTROL).is_file():
            raise ValueError('Planned pause has no resumable data/control pair')
        state = 'paused'
        progressed = previous_control is None or previous_control != (work / CONTROL).read_bytes()
    else:
        return code if code > 0 else 128 - code
    metadata = {
        'schema': 1, 'state': state, 'url': env['ROM_URL'],
        'rom_version': env['ROM_VERSION'], 'chain': chain, 'round': round_number,
        'run_id': env['GITHUB_RUN_ID'], 'run_attempt': env['GITHUB_RUN_ATTEMPT'],
        'apparent_bytes': (work / ('rom.tgz' if state == 'complete' else PARTIAL)).stat().st_size,
    }
    archive = pack(work, metadata)
    can_continue = progressed and round_number < int(env['MAX_RELAY_ROUNDS'])
    with open(env['GITHUB_OUTPUT'], 'a') as target:
        target.write(f'state={state}\nchain={chain}\nround={round_number}\n'
                     f'can_continue={str(can_continue).lower()}\ncheckpoint_path={archive}\n')
    print(f'Round state: {state}; saved progress changed: {progressed}; '
          f'automatic continuation allowed: {can_continue}', flush=True)
    summary(f'Checkpoint state: **{state}**. Saved progress changed: **{progressed}**.\n\n')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare', 'download', 'restore-complete'))
    args = parser.parse_args()
    os.umask(0o077)
    env = os.environ
    if args.operation == 'prepare':
        prepare(env)
    elif args.operation == 'download':
        return download(env)
    else:
        restore(Path(env['ROM_WORK']) / 'incoming' / CHECKPOINT,
                Path(env['ROM_WORK']), env, 'complete')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError, tarfile.TarError) as error:
        print(f'Stock ROM relay failed: {error}', file=sys.stderr)
        sys.exit(1)
