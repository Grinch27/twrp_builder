#!/usr/bin/env python3
# Requirements: publish the original official ROM and all images/ payloads.
# Ambiguity: package contents and correspondence with either device slot are unknown.
# Research: tarfile streams and GitHub's per-asset limit; never run OEM scripts.
# Optimization: stream payloads and the original ROM directly into bounded parts.
# Risks: archive paths/links, partial transfers, disk exhaustion and public firmware.
# Validation: synthetic archives and exact copy sizes; no extra hashes or image scans.
"""Prepare official stock firmware payloads for a separate public Release."""

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile


ROM_URL = (
    'https://bigota.d.miui.com/V14.0.4.0.TKUCNXM/'
    'selene_images_V14.0.4.0.TKUCNXM_20231228.0000.00_13.0_cn_cfe62df805.tgz'
)
ROM_VERSION = 'V14.0.4.0.TKUCNXM'
PART_BYTES = 1_900_000_000
RESERVE_BYTES = 1024 ** 3
METADATA_NAMES = ('archive-inventory.json', 'stock-rom-manifest.json', 'original-rom-manifest.json')
SCRIPT_SUFFIXES = {'.sh', '.bat', '.cmd', '.ps1', '.exe'}
IMAGE_SUFFIXES = {'.img', '.bin', '.elf', '.mbn'}
SAFE_NAME = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9._-]{0,178}[A-Za-z0-9_-])?\Z')
STOCK_TAG = re.compile(re.escape(f'selene-stock-{ROM_VERSION}-') + r'[1-9][0-9]*-[1-9][0-9]*\Z')
DA_NAMES = {'MTK_AllInOne_DA_mt6768.bin', 'MTK_AllInOne_DA.bin'}


def safe_parts(name):
    """Reject unsafe tar paths without writing any archive-controlled path."""
    if (not name or name.startswith('/') or '\\' in name
            or '..' in name.split('/')
            or any(ord(char) < 32 or ord(char) == 127 for char in name)):
        raise ValueError(f'Unsafe archive path: {name!r}')
    return PurePosixPath(name).parts


def inspect_archive(archive):
    """List entries and select complete regular payloads in one images directory."""
    inventory = []
    payloads = []
    image_root = None
    seen = set()
    with tarfile.open(archive, 'r:gz') as source:
        for member in source:
            parts = safe_parts(member.name)
            if len(inventory) >= 10000:
                raise ValueError('Archive contains too many entries')
            inventory.append({
                'path': member.name, 'bytes': member.size,
                'type': 'file' if member.isfile() else 'directory' if member.isdir() else 'other',
            })
            if member.isdir():
                continue
            if (len(parts) == 2 and parts[0] == f'selene_images_{ROM_VERSION}_13.0'
                    and parts[1] in DA_NAMES):
                if not member.isfile() or member.issparse() or member.size <= 0:
                    raise ValueError('Non-regular or empty download-agent companion')
                inventory[-1]['role'] = 'download-agent-companion'
                continue
            index = parts.index('images') if 'images' in parts else -1
            if index in (0, 1) and len(parts) == index + 1:
                raise ValueError(f'Non-regular images directory: {member.name}')
            if index not in (0, 1) or len(parts) <= index + 1:
                if PurePosixPath(member.name).suffix.lower() in IMAGE_SUFFIXES:
                    raise ValueError(f'Image-like entry outside images/: {member.name}')
                continue
            root = parts[:index + 1]
            if image_root is not None and root != image_root:
                raise ValueError('Multiple images directories require manual review')
            image_root = root
            if not member.isfile() or member.issparse():
                raise ValueError(f'Non-regular or tar-sparse payload: {member.name}')
            name = parts[-1]
            if not SAFE_NAME.fullmatch(name):
                raise ValueError(f'Unsupported Release filename: {name!r}')
            if PurePosixPath(name).suffix.lower() in SCRIPT_SUFFIXES:
                continue
            if name.casefold() in seen:
                raise ValueError(f'Duplicate payload filename: {name}')
            seen.add(name.casefold())
            if member.size < 0 or (member.size == 0 and PurePosixPath(name).suffix.lower() in IMAGE_SUFFIXES):
                raise ValueError(f'Empty or invalid image: {name}')
            payloads.append({'path': member.name, 'name': name, 'bytes': member.size})
    if not any(item['name'] == 'boot.img' for item in payloads):
        raise ValueError('Archive has no regular images/boot.img')
    return inventory, payloads


def plan_assets(payloads, part_bytes, reserved_names=()):
    """Plan unique Release filenames before writing any payload bytes."""
    if not 0 < part_bytes <= PART_BYTES:
        raise ValueError('Invalid part size')
    used = {name.casefold() for name in (*METADATA_NAMES, *reserved_names)}
    planned = []
    for payload in payloads:
        item = dict(payload)
        count = max(1, (item['bytes'] + part_bytes - 1) // part_bytes)
        if count > 1000 - len(used):
            raise ValueError('Release exceeds the 1000-asset limit')
        names = [item['name']] if count == 1 else [
            f"{item['name']}.part{index:04d}" for index in range(1, count + 1)
        ]
        item['assets'] = []
        remaining = item['bytes']
        for name in names:
            if name.casefold() in used:
                raise ValueError(f'Conflicting Release asset: {name}')
            used.add(name.casefold())
            size = min(remaining, part_bytes)
            item['assets'].append({'name': name, 'bytes': size})
            remaining -= size
        planned.append(item)
    if len(used) > 1000:
        raise ValueError('Release exceeds the 1000-asset limit')
    return planned


def copy_exact(source, destination, size):
    """Copy the declared payload bytes, refusing truncated input or overwrites."""
    with destination.open('xb') as target:
        remaining = size
        while remaining:
            chunk = source.read(min(remaining, 1024 * 1024))
            if not chunk:
                raise EOFError(f'Truncated payload: {destination.name}')
            target.write(chunk)
            remaining -= len(chunk)


def original_plan(archive, part_bytes):
    return plan_assets([{'name': ROM_URL.rsplit('/', 1)[-1],
                         'bytes': archive.stat().st_size}], part_bytes)[0]


def write_original(archive, assets, staging, original):
    """Copy raw bytes without inspecting ROM contents; write the manifest last."""
    with archive.open('rb') as source:
        for part in original['assets']:
            partial = staging / part['name']
            copy_exact(source, partial, part['bytes'])
            partial.rename(assets / part['name'])
        if source.read(1):
            raise ValueError('Original ROM changed while preparing Release assets')
    metadata = {'schema': 1, 'source_url': ROM_URL, 'rom_version': ROM_VERSION,
                'original_rom': original}
    with (assets / METADATA_NAMES[2]).open('x') as target:
        json.dump(metadata, target, indent=2)
        target.write('\n')


def prepare_original_rom(archive, output, part_bytes=PART_BYTES):
    """Prepare a durable raw-ROM backup before any images/ directory checks."""
    archive, output = Path(archive), Path(output)
    if output.exists():
        raise FileExistsError(output)
    original = original_plan(archive, part_bytes)
    if original['bytes'] <= 0:
        raise ValueError('Original ROM is empty')
    if shutil.disk_usage(output.parent).free < original['bytes'] + RESERVE_BYTES:
        raise OSError('Insufficient space for original ROM Release parts')
    assets, staging = output / 'assets', output / 'partial'
    assets.mkdir(parents=True, mode=0o700)
    staging.mkdir(mode=0o700)
    write_original(archive, assets, staging, original)
    command = (f"cat -- {' '.join(p['name'] for p in original['assets'])} > {original['name']}"
               if len(original['assets']) > 1 else f"# Original archive: {original['name']}")
    (output / 'release-notes.md').write_text(
        f'# selene stock ROM {ROM_VERSION}\n\nOfficial source: {ROM_URL}\n\n'
        'Original ROM backup saved before payload extraction. Payload preparation is pending.\n\n'
        f"Original bytes: {original['bytes']}\n\n```bash\n{command}\n```\n")
    return original


def find_original_release(repo):
    """Prefer the newest stock backup marker, including drafts, before upstream IO."""
    pages = json.loads(subprocess.check_output(
        ['gh', 'api', '--paginate', '--slurp', f'repos/{repo}/releases?per_page=100'],
        text=True))
    candidates = [release for page in pages for release in page
                  if STOCK_TAG.fullmatch(release['tag_name'])
                  and any(a['name'] == METADATA_NAMES[2]
                          and a.get('state') == 'uploaded' and 0 < a['size'] <= 16384
                          for a in release['assets'])]
    if not candidates:
        return None
    return max(candidates, key=lambda release: release['id'])['tag_name']


def restore_original_release(tag, archive):
    """Restore only the exact fixed-ROM parts declared by a saved Release manifest."""
    archive = Path(archive)
    repo = os.environ['GITHUB_REPOSITORY']
    if tag == 'auto':
        tag = find_original_release(repo)
        if tag is None:
            print('No saved original-ROM backup found; use the official source.', flush=True)
            return None
    if not STOCK_TAG.fullmatch(tag):
        raise ValueError('Unexpected stock Release tag')
    if archive.exists():
        raise FileExistsError(archive)
    prefix = ['gh', 'release']
    remote = json.loads(subprocess.check_output(
        prefix + ['view', tag, '--repo', repo, '--json', 'assets'], text=True))['assets']
    manifests = [a for a in remote if a['name'] == METADATA_NAMES[2]]
    if len(manifests) != 1 or not 0 < manifests[0]['size'] <= 16384:
        raise ValueError('Release has no complete original-ROM manifest')
    with tempfile.TemporaryDirectory(prefix='stock-release.', dir=archive.parent) as temporary:
        staging = Path(temporary)
        subprocess.run(prefix + ['download', tag, '--repo', repo, '--pattern',
                                METADATA_NAMES[2], '--dir', str(staging)], check=True)
        manifest_path = staging / METADATA_NAMES[2]
        if manifest_path.stat().st_size > 16384:
            raise ValueError('Oversized original-ROM manifest')
        metadata = json.loads(manifest_path.read_text())
        original = metadata.get('original_rom', {})
        size = original.get('bytes')
        if (metadata.get('schema') != 1 or metadata.get('source_url') != ROM_URL
                or metadata.get('rom_version') != ROM_VERSION
                or type(size) is not int or not 0 < size <= 8 * 1024 ** 3):
            raise ValueError('Release manifest does not identify the fixed ROM')
        expected = plan_assets([{'name': ROM_URL.rsplit('/', 1)[-1], 'bytes': size}], PART_BYTES)[0]
        if original != expected:
            raise ValueError('Unexpected original-ROM part names or sizes')
        for part in original['assets']:
            matches = [a for a in remote if a['name'] == part['name']]
            if len(matches) != 1 or matches[0]['size'] != part['bytes']:
                raise ValueError('Release original-ROM part is missing or incomplete')
        if shutil.disk_usage(archive.parent).free < 2 * size + RESERVE_BYTES:
            raise OSError('Insufficient space to restore Release parts and ROM')
        for part in original['assets']:
            subprocess.run(prefix + ['download', tag, '--repo', repo, '--pattern',
                                    part['name'], '--dir', str(staging)], check=True)
            if (staging / part['name']).stat().st_size != part['bytes']:
                raise ValueError('Downloaded Release part has an unexpected length')
        partial = archive.with_name(archive.name + '.restoring')
        with partial.open('xb') as target:
            for part in original['assets']:
                with (staging / part['name']).open('rb') as source:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
        partial.rename(archive)
    print(f'Restored complete original ROM from Release {tag}; bytes={size}', flush=True)
    return tag


def extract_rom(archive, output, part_bytes=PART_BYTES, include_original=True):
    """List, extract and document payloads; an error prevents Release publication."""
    archive, output = Path(archive), Path(output)
    if output.exists():
        raise FileExistsError(output)
    inventory, payloads = inspect_archive(archive)
    original = original_plan(archive, part_bytes)
    original_name = original['name']
    planned = plan_assets(payloads, part_bytes,
                          reserved_names=[part['name'] for part in original['assets']])
    for entry in inventory:
        print(f"ARCHIVE {entry['type']} {entry['bytes']} {entry['path']}", flush=True)
    required = (sum(item['bytes'] for item in planned) + RESERVE_BYTES
                + (original['bytes'] if include_original else 0))
    if shutil.disk_usage(output.parent).free < required:
        raise OSError(f'Insufficient extraction disk space; need {required} free bytes')
    assets = output / 'assets'
    assets.mkdir(parents=True, mode=0o700)
    staging = output / 'partial'
    staging.mkdir(mode=0o700)
    by_path = {item['path']: item for item in planned}
    completed = set()
    with tarfile.open(archive, 'r|gz') as source:
        for member in source:
            item = by_path.get(member.name)
            if item is None:
                continue
            if (member.name in completed or not member.isfile()
                    or member.size != item['bytes'] or member.issparse()):
                raise ValueError('Archive payload changed between listing and extraction')
            print(f"EXTRACT {item['name']} {item['bytes']}", flush=True)
            stream = source.extractfile(member)
            if stream is None:
                raise ValueError(f'Missing payload stream: {member.name}')
            with stream:
                for part in item['assets']:
                    partial = staging / part['name']
                    copy_exact(stream, partial, part['bytes'])
                    partial.rename(assets / part['name'])
            completed.add(member.name)
    if len(completed) != len(planned):
        raise ValueError('Not all planned payloads were extracted')
    if include_original:
        write_original(archive, assets, staging, original)
    manifest = {
        'source_url': ROM_URL, 'rom_version': ROM_VERSION, 'device': 'selene',
        'is_device_backup': False, 'device_slot_correspondence': 'NOT_VERIFIED',
        'part_bytes': part_bytes, 'original_rom': original, 'payloads': planned,
    }
    for name, data in zip(METADATA_NAMES[:2], (inventory, manifest)):
        with (assets / name).open('x', encoding='utf-8') as target:
            json.dump(data, target, ensure_ascii=False, indent=2)
            target.write('\n')
    notes = [
        f'# selene stock firmware {ROM_VERSION}', '',
        f'Official source: {ROM_URL}', '',
        'Original images/ payloads and companion metadata; no OEM flashing scripts were run.',
        'This is an official-ROM extraction, NOT a backup of boot_a or boot_b.',
        'Device correspondence and restore/flash safety are NOT_VERIFIED.',
        'Android sparse images remain in their original format; do not run simg2img.',
        'Release assets do not have the three-day Actions Artifact expiry.', '',
        '## Original ROM archive', '',
        f"`{original_name}`: {original['bytes']} bytes; original downloaded bytes, without repacking.",
        'Download all original-ROM parts into a new empty directory and reassemble in this order:',
        '', '```bash',
        (f"cat -- {' '.join(part['name'] for part in original['assets'])} > {original_name}"
         if len(original['assets']) > 1 else f'# Original archive: {original_name}'),
        '```', '',
        '## Payloads', '',
    ]
    for item in planned:
        notes.append(f"- `{item['name']}`: {item['bytes']} bytes, {len(item['assets'])} asset(s).")
    notes += ['', '## Reassemble split images', '',
              'Download every part from this Release into a new empty directory. Then:', '', '```bash']
    for item in planned:
        if len(item['assets']) > 1:
            parts = ' '.join(part['name'] for part in item['assets'])
            notes.append(f"cat -- {parts} > {item['name']}")
    notes += ['```', '', 'Do not flash an individual part or a GitHub Source code archive.', '']
    (output / 'release-notes.md').write_text('\n'.join(notes), encoding='utf-8')
    print(f'Prepared {len(planned)} payloads for Release publication.', flush=True)
    return manifest


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('output', type=Path, nargs='?')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare-original', action='store_true')
    mode.add_argument('--payload-only', action='store_true')
    mode.add_argument('--restore-release')
    args = parser.parse_args()
    if args.restore_release:
        tag = restore_original_release(args.restore_release, args.archive)
        if tag and os.environ.get('GITHUB_ENV'):
            with Path(os.environ['GITHUB_ENV']).open('a') as target:
                target.write(f'ROM_RELEASE_TAG={tag}\n')
    elif args.output is None:
        parser.error('output is required when preparing Release assets')
    elif args.prepare_original:
        prepare_original_rom(args.archive, args.output)
    else:
        extract_rom(args.archive, args.output, include_original=not args.payload_only)


if __name__ == '__main__':
    main()
