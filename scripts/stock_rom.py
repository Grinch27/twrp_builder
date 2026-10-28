#!/usr/bin/env python3
# Requirements: list the official selene archive and retain all images/ payloads.
# Ambiguity: package contents and correspondence with either device slot are unknown.
# Research: tarfile streams and GitHub's per-asset limit; never run OEM scripts.
# Optimization: write large payloads directly to bounded parts, without a second copy.
# Risks: archive paths/links, partial transfers, disk exhaustion and public firmware.
# Validation: synthetic archives and exact copy sizes; no extra hashes or image scans.
"""Prepare official stock firmware payloads for a separate public Release."""

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile


ROM_URL = (
    'https://bigota.d.miui.com/V14.0.4.0.TKUCNXM/'
    'selene_images_V14.0.4.0.TKUCNXM_20231228.0000.00_13.0_cn_cfe62df805.tgz'
)
ROM_VERSION = 'V14.0.4.0.TKUCNXM'
PART_BYTES = 1_900_000_000
RESERVE_BYTES = 1024 ** 3
METADATA_NAMES = ('archive-inventory.json', 'stock-rom-manifest.json')
SCRIPT_SUFFIXES = {'.sh', '.bat', '.cmd', '.ps1', '.exe'}
IMAGE_SUFFIXES = {'.img', '.bin', '.elf', '.mbn'}
SAFE_NAME = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9._-]{0,178}[A-Za-z0-9_-])?\Z')


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


def plan_assets(payloads, part_bytes):
    """Plan unique Release filenames before writing any payload bytes."""
    if not 0 < part_bytes <= PART_BYTES:
        raise ValueError('Invalid part size')
    used = {name.casefold() for name in METADATA_NAMES}
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


def extract_rom(archive, output, part_bytes=PART_BYTES):
    """List, extract and document payloads; an error prevents Release publication."""
    archive, output = Path(archive), Path(output)
    if output.exists():
        raise FileExistsError(output)
    inventory, payloads = inspect_archive(archive)
    planned = plan_assets(payloads, part_bytes)
    for entry in inventory:
        print(f"ARCHIVE {entry['type']} {entry['bytes']} {entry['path']}", flush=True)
    required = sum(item['bytes'] for item in planned) + RESERVE_BYTES
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
    manifest = {
        'source_url': ROM_URL, 'rom_version': ROM_VERSION, 'device': 'selene',
        'is_device_backup': False, 'device_slot_correspondence': 'NOT_VERIFIED',
        'part_bytes': part_bytes, 'payloads': planned,
    }
    for name, data in zip(METADATA_NAMES, (inventory, manifest)):
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
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    extract_rom(args.archive, args.output)


if __name__ == '__main__':
    main()
