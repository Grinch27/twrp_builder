#!/usr/bin/env python3
# Requirements: restore the stock resource filegroup required by recovery tests.
# Ambiguity: public test data does not establish an image or device result.
# Research: use the exact AOSP 12.1 r4 resources and their original NOTICE.
# Optimization: download only the 4.5 MB resource set; four bounded readers.
# Risks: destination collisions, partial downloads and private input expansion.
# Validation: existing Git input identities, new-only writes and fixture tests.
"""Restore locked public test assets without replacing any original project."""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import urllib.request

from source_inputs import NoRedirect, SHA, load_lock, verify_blob, write_new


def resource_lock(lock):
    value = lock['public_test_resources']
    if (set(value) != {'project', 'revision', 'upstream', 'destination', 'files'}
            or value['project'] != 'platform/bootable/recovery'
            or not SHA.fullmatch(value['revision'])
            or value['upstream'] != 'refs/tags/android-12.1.0_r4'
            or value['destination'] != 'bootable/recovery/builder-testdata'):
        raise ValueError('unreviewed public test resource source')
    files = value['files']
    if not isinstance(files, list) or not 2 <= len(files) <= 200:
        raise ValueError('empty or oversized resource set')
    paths = set()
    for entry in files:
        if (set(entry) != {'path', 'blob', 'size'}
                or not isinstance(entry['path'], str)
                or not re.fullmatch(r'NOTICE|res-[a-z0-9]+/images/[a-z_]+_text\.png', entry['path'])
                or not SHA.fullmatch(entry['blob'])
                or not isinstance(entry['size'], int) or isinstance(entry['size'], bool)
                or not 0 < entry['size'] <= 2 * 1024**2 or entry['path'] in paths):
            raise ValueError('invalid public test resource entry')
        paths.add(entry['path'])
    if 'NOTICE' not in paths or sum(e['size'] for e in files) > 32 * 1024**2:
        raise ValueError('missing license or resource size limit')
    return value


def read_public(entry, revision):
    url = ('https://android.googlesource.com/platform/bootable/recovery/+/'
           + revision + '/' + entry['path'] + '?format=TEXT')
    opener = urllib.request.build_opener(NoRedirect)
    limit = ((entry['size'] + 2) // 3) * 4 + 8192
    with opener.open(url, timeout=30) as response:
        encoded = response.read(limit + 1)
    if len(encoded) > limit:
        raise ValueError('public resource download size limit')
    return base64.b64decode(b''.join(encoded.split()), validate=True)


def restore(lock, source, blueprint, reader=None):
    value = resource_lock(lock)
    source = Path(source).absolute()
    destination = source / value['destination']
    if (source != source.resolve() or destination.parent != destination.parent.resolve()
            or not (source / 'bootable/recovery').is_dir()
            or destination.exists() or destination.is_symlink()):
        raise ValueError('public test resource destination collision')
    definition = Path(blueprint).read_bytes()
    if b'name: "res-testdata"' not in definition:
        raise ValueError('missing reviewed resource filegroup')
    read = reader or (lambda entry: read_public(entry, value['revision']))
    with ThreadPoolExecutor(max_workers=4) as pool:
        payloads = list(pool.map(read, value['files']))
    # Validate downloads before creating a module; never create an empty placeholder.
    for entry, data in zip(value['files'], payloads):
        verify_blob(data, entry)
    for entry, data in zip(value['files'], payloads):
        write_new(source, value['destination'] + '/' + entry['path'], data)
    write_new(source, value['destination'] + '/Android.bp', definition)
    return len(payloads)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    count = restore(load_lock(), args.source, root / 'patches/recovery-testdata.Android.bp')
    print('PUBLIC_TEST_RESOURCE_FILES=' + str(count), flush=True)


if __name__ == '__main__':
    main()
