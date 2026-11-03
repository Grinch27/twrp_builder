#!/usr/bin/env python3
# Requirements: restore the stock resource filegroup required by recovery tests.
# Ambiguity: public test data does not establish an image or device result.
# Research: use the exact AOSP 12.1 r4 resources and their original NOTICE.
# Optimization: four readers, bounded transient retries and a shared time budget.
# Risks: destination collisions, partial downloads and private input expansion.
# Validation: existing Git input identities, new-only writes and fixture tests.
"""Restore locked public test assets without replacing any original project."""

import argparse
import base64
import binascii
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import time
import urllib.error
import urllib.request

from source_inputs import NoRedirect, SHA, load_lock, verify_blob, write_new

CODES = {'SUCCESS', 'LOCK_INVALID', 'DESTINATION_COLLISION', 'BLUEPRINT_INVALID',
         'HTTP_ERROR', 'REDIRECT_BLOCKED', 'NETWORK_ERROR', 'TLS_ERROR', 'TIMEOUT', 'PAYLOAD_INVALID',
         'IDENTITY_MISMATCH', 'IO_ERROR', 'UNEXPECTED_FAILURE'}
RETRY_HTTP = {408, 429, 500, 502, 503, 504}


class ResourceFailure(ValueError):
    def __init__(self, code, *, status=0, attempts=0):
        super().__init__(code)
        self.code, self.status, self.attempts = code, status, attempts


def public_status(value, lock):
    """Allow only fixed categories and numbers bound to the locked public source."""
    try:
        revision = resource_lock(lock)['revision']
        if (not isinstance(value, dict)
                or set(value) != {'schema', 'revision', 'code', 'http_status', 'attempts'}
                or type(value['schema']) is not int or value['schema'] != 1
                or value['revision'] != revision or value['code'] not in CODES
                or type(value['http_status']) is not int
                or value['http_status'] not in ({0} | set(range(300, 600)))
                or type(value['attempts']) is not int or not 0 <= value['attempts'] <= 3):
            return None
        return dict(value)
    except (KeyError, TypeError, ValueError):
        return None


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


def read_public(entry, revision, *, deadline=None, opener=None, sleep=time.sleep):
    url = ('https://android.googlesource.com/platform/bootable/recovery/+/'
           + revision + '/' + entry['path'] + '?format=TEXT')
    opener = opener or urllib.request.build_opener(NoRedirect)
    limit = ((entry['size'] + 2) // 3) * 4 + 8192
    for attempt in range(1, 4):
        remaining = 20 if deadline is None else min(20, deadline - time.monotonic())
        if remaining <= 0:
            raise ResourceFailure('TIMEOUT', attempts=attempt - 1)
        retry = False
        try:
            with opener.open(url, timeout=remaining) as response:
                encoded = response.read(limit + 1)
            if len(encoded) > limit:
                raise ResourceFailure('PAYLOAD_INVALID', attempts=attempt)
            try:
                return base64.b64decode(b''.join(encoded.split()), validate=True)
            except (ValueError, binascii.Error) as error:
                raise ResourceFailure('PAYLOAD_INVALID', attempts=attempt) from error
        except urllib.error.HTTPError as error:
            failure = ResourceFailure('REDIRECT_BLOCKED' if 300 <= error.code < 400
                                      else 'HTTP_ERROR', status=error.code, attempts=attempt)
            retry = error.code in RETRY_HTTP
        except (TimeoutError, urllib.error.URLError, ssl.SSLError,
                ConnectionError, http.client.IncompleteRead) as error:
            reason = error.reason if isinstance(error, urllib.error.URLError) else error
            if isinstance(reason, ssl.SSLError):
                failure = ResourceFailure('TLS_ERROR', attempts=attempt)
            else:
                failure = ResourceFailure('TIMEOUT' if isinstance(reason, TimeoutError)
                                          else 'NETWORK_ERROR', attempts=attempt)
                retry = True
        if not retry or attempt == 3:
            raise failure
        delay = 2 ** (attempt - 1)
        if deadline is not None and time.monotonic() + delay >= deadline:
            raise failure
        sleep(delay)


def restore(lock, source, blueprint, reader=None):
    try:
        value = resource_lock(lock)
    except (KeyError, TypeError, ValueError) as error:
        raise ResourceFailure('LOCK_INVALID') from error
    source = Path(source).absolute()
    destination = source / value['destination']
    if (source != source.resolve() or destination.parent != destination.parent.resolve()
            or not (source / 'bootable/recovery').is_dir()
            or destination.exists() or destination.is_symlink()):
        raise ResourceFailure('DESTINATION_COLLISION')
    definition = Path(blueprint).read_bytes()
    if b'name: "res-testdata"' not in definition:
        raise ResourceFailure('BLUEPRINT_INVALID')
    deadline = time.monotonic() + 240
    read = reader or (lambda entry: read_public(entry, value['revision'], deadline=deadline))
    with ThreadPoolExecutor(max_workers=4) as pool:
        payloads = list(pool.map(read, value['files']))
    # Validate downloads before creating a module; never create an empty placeholder.
    for entry, data in zip(value['files'], payloads):
        try:
            verify_blob(data, entry)
        except ValueError as error:
            raise ResourceFailure('IDENTITY_MISMATCH') from error
    for entry, data in zip(value['files'], payloads):
        write_new(source, value['destination'] + '/' + entry['path'], data)
    write_new(source, value['destination'] + '/Android.bp', definition)
    return len(payloads)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--status-output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    lock = load_lock()
    status = {'schema': 1, 'revision': lock['public_test_resources']['revision'],
              'code': 'SUCCESS', 'http_status': 0, 'attempts': 0}
    try:
        count = restore(lock, args.source, root / 'patches/recovery-testdata.Android.bp')
    except Exception as error:
        status.update(code=error.code if isinstance(error, ResourceFailure) else
                      ('IO_ERROR' if isinstance(error, OSError) else 'UNEXPECTED_FAILURE'),
                      http_status=getattr(error, 'status', 0),
                      attempts=getattr(error, 'attempts', 0))
        raise
    finally:
        if args.status_output is not None:
            # The diagnostic contains no exception messages, URLs, paths or response bodies.
            try:
                fd = os.open(args.status_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(status, stream, sort_keys=True)
            except OSError:
                print('Public resource status unavailable.', flush=True)
    print('PUBLIC_TEST_RESOURCE_FILES=' + str(count), flush=True)


if __name__ == '__main__':
    main()
