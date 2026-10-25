# Requirements: restore actual resources into a new directory, preserving sources.
# Ambiguity: synthetic assets do not prove recovery tests or an image build.
# Research: exercise pinned public input and the real restore operation offline.
# Optimization: two tiny source fixtures; no network or Android checkout.
# Risks: missing resources, overwrite, symlink escape and wrong source identity.
# Validation: reject these failures before creating a usable filegroup.
import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from restore_public_testdata import resource_lock, restore


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
