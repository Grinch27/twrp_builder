# Requirements: restore actual resources into a new directory, preserving sources.
# Ambiguity: synthetic assets do not prove recovery tests or an image build.
# Research: exercise pinned public input and the real restore operation offline.
# Optimization: two tiny source fixtures; no network or Android checkout.
# Risks: missing resources, overwrite, symlink escape and wrong source identity.
# Validation: reject these failures before creating a usable filegroup.
import copy
import base64
import hashlib
import io
import json
import ssl
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from restore_public_testdata import ResourceFailure, public_status, read_public, resource_lock, restore


class PublicTestDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.recovery = self.root / 'bootable/recovery'
        self.recovery.mkdir(parents=True)
        (self.recovery / 'Android.bp').write_text('original public source\n')
        self.blueprint = self.root / 'definition.bp'
        self.blueprint.write_text('filegroup { name: "res-testdata", srcs: ["res-*/images/*_text.png"] }\n')
        self.payloads = {'NOTICE': b'original license',
                         'res-hdpi/images/error_text.png': b'public resource fixture'}
        files = []
        for path, data in self.payloads.items():
            blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            files.append({'path': path, 'blob': blob, 'size': len(data)})
        self.lock = {'public_test_resources': {
            'project': 'platform/bootable/recovery', 'revision': 'a' * 40,
            'upstream': 'refs/tags/android-12.1.0_r4',
            'destination': 'bootable/recovery/builder-testdata', 'files': files}}

    def read(self, entry):
        return self.payloads[entry['path']]

    def test_restores_nonempty_resources_and_keeps_existing_source(self):
        count = restore(self.lock, self.root, self.blueprint, self.read)
        destination = self.recovery / 'builder-testdata'
        self.assertEqual(count, 2)
        for path, data in self.payloads.items():
            self.assertEqual((destination / path).read_bytes(), data)
        self.assertEqual((destination / 'Android.bp').read_bytes(), self.blueprint.read_bytes())
        self.assertEqual((self.recovery / 'Android.bp').read_text(), 'original public source\n')

    def test_changed_bytes_never_create_a_placeholder_module(self):
        with self.assertRaises(ValueError):
            restore(self.lock, self.root, self.blueprint, lambda entry: b'wrong source')
        self.assertFalse((self.recovery / 'builder-testdata').exists())

    def test_existing_destination_is_not_overwritten(self):
        destination = self.recovery / 'builder-testdata'
        destination.mkdir()
        (destination / 'keep').write_text('keep')
        with self.assertRaises(ValueError):
            restore(self.lock, self.root, self.blueprint, self.read)
        self.assertEqual((destination / 'keep').read_text(), 'keep')

    def test_empty_or_unlicensed_resources_are_rejected(self):
        for files in ([], self.lock['public_test_resources']['files'][1:]):
            value = copy.deepcopy(self.lock)
            value['public_test_resources']['files'] = files
            with self.assertRaises(ValueError):
                resource_lock(value)

    def test_path_source_and_duplicate_entries_are_rejected(self):
        for change in ('path', 'source', 'duplicate'):
            with self.subTest(change=change):
                value = copy.deepcopy(self.lock)
                data = value['public_test_resources']
                if change == 'path':
                    data['files'][1]['path'] = '../outside'
                elif change == 'source':
                    data['project'] = 'private/source'
                else:
                    data['files'].append(data['files'][0])
                with self.assertRaises(ValueError):
                    resource_lock(value)

    def test_symlink_destination_cannot_escape_source(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.recovery / 'builder-testdata').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            restore(self.lock, self.root, self.blueprint, self.read)
        self.assertEqual(list(outside.iterdir()), [])

    def opener(self, outcomes):
        class Opener:
            calls = 0

            def open(inner, url, timeout):
                self.assertTrue(url.startswith('https://android.googlesource.com/'))
                self.assertGreater(timeout, 0)
                self.assertLessEqual(timeout, 20)
                value = outcomes[min(inner.calls, len(outcomes) - 1)]
                inner.calls += 1
                if isinstance(value, Exception):
                    raise value
                return io.BytesIO(value)
        return Opener()

    def test_transient_public_download_retries_then_returns_original_bytes(self):
        error = urllib.error.HTTPError('private-message', 503, 'private-body', {}, None)
        opener = self.opener([error, error, base64.b64encode(b'original license')])
        sleeps = []
        data = read_public(self.lock['public_test_resources']['files'][0], 'a' * 40,
                           opener=opener, sleep=sleeps.append)
        self.assertEqual(data, b'original license')
        self.assertEqual(opener.calls, 3)
        self.assertEqual(sleeps, [1, 2])

    def test_retry_budget_and_nonretry_http_tls_errors(self):
        for error, expected, calls in [
            (urllib.error.HTTPError('private', 503, 'secret', {}, None), 'HTTP_ERROR', 3),
            (urllib.error.HTTPError('private', 404, 'secret', {}, None), 'HTTP_ERROR', 1),
            (urllib.error.HTTPError('private', 302, 'secret', {}, None), 'REDIRECT_BLOCKED', 1),
            (urllib.error.URLError(ssl.SSLCertVerificationError('secret')), 'TLS_ERROR', 1),
            (TimeoutError('secret'), 'TIMEOUT', 3),
        ]:
            with self.subTest(expected=expected, calls=calls):
                opener = self.opener([error])
                with self.assertRaises(ResourceFailure) as result:
                    read_public(self.lock['public_test_resources']['files'][0], 'a' * 40,
                                opener=opener, sleep=lambda _: None)
                self.assertEqual(result.exception.code, expected)
                self.assertEqual(result.exception.attempts, calls)
                self.assertEqual(opener.calls, calls)
                self.assertNotIn('secret', str(result.exception))

    def test_invalid_payload_and_expired_deadline_are_not_retried(self):
        entry = self.lock['public_test_resources']['files'][0]
        for data in (b'!invalid-base64!', b'A' * 10000):
            opener = self.opener([data])
            with self.assertRaises(ResourceFailure) as result:
                read_public(entry, 'a' * 40, opener=opener, sleep=lambda _: self.fail('retry'))
            self.assertEqual(result.exception.code, 'PAYLOAD_INVALID')
            self.assertEqual(opener.calls, 1)
        opener = self.opener([])
        with self.assertRaises(ResourceFailure) as result:
            read_public(entry, 'a' * 40, deadline=-1, opener=opener)
        self.assertEqual(result.exception.code, 'TIMEOUT')
        self.assertEqual(opener.calls, 0)

    def test_public_status_rejects_unbound_identity_raw_text_and_booleans(self):
        value = {'schema': 1, 'revision': 'a' * 40, 'code': 'HTTP_ERROR',
                 'http_status': 503, 'attempts': 3}
        self.assertEqual(public_status(value, self.lock), value)
        for change in ({'revision': 'b' * 40}, {'code': 'private-message'},
                       {'raw': 'private-secret'}, {'http_status': True}, {'attempts': 4}):
            self.assertIsNone(public_status({**value, **change}, self.lock))

    def test_cli_collision_records_fixed_status_and_preserves_failure(self):
        (self.recovery / 'builder-testdata').mkdir()
        status = self.root / 'status.json'
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, str(root / 'scripts/restore_public_testdata.py'),
                                 '--source', str(self.root), '--status-output', str(status)],
                                capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        value = json.loads(status.read_text())
        self.assertEqual(value['code'], 'DESTINATION_COLLISION')
        self.assertEqual(status.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(str(self.root), json.dumps(value))
