# Requirements: synthetic input fixtures; no private source or network in tests.
# Ambiguity: these tests do not establish the upstream source closure.
# Research: real sync/build results remain separate acceptance criteria.
# Optimization: standard library only, small temporary directories.
# Risks: unsafe output paths, corrupt source downloads, unlocked manifests.
# Validation: reject each boundary before writing or invoking a build.
import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import source_inputs as source


def manifest(projects=None):
    if projects is None:
        projects = '<project name="platform/build" path="build/make" revision="' + '1' * 40 + '"/>'
    return ('<manifest><remote name="aosp" fetch="https://android.googlesource.com"/>'
            '<default remote="aosp"/>' + projects + '</manifest>').encode()


def entry(data=b'fixture'):
    return {'path': 'default.xml', 'destination': 'default.xml', 'size': len(data),
            'blob': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()}


class InputTests(unittest.TestCase):
    def test_repository_lock(self):
        lock = source.load_lock()
        self.assertEqual(len(lock['files']), 10)
        self.assertEqual(lock['source']['manifest_projects'], 282)
        self.assertEqual(lock['device']['overlay_files'], 4)
        self.assertEqual(lock['build']['target'], 'bootimage')

    def test_path_boundaries(self):
        for value in ['', '.', '..', '../outside', '/absolute', 'a/../b', 'a//b',
                      './a', 'a/.git/config', 'a/.repo/config', 'a\\b', 'a\nnew']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                source.relative_path(value)
        self.assertEqual(str(source.relative_path('device/xiaomi/selene')), 'device/xiaomi/selene')

    def test_manifest_accepts_locked_project_and_links(self):
        project = '<project name="platform/build" path="build/make" revision="' + '1' * 40 + '"><linkfile src="envsetup.sh" dest="build/envsetup.sh"/></project>'
        self.assertEqual(len(source.validate_manifest(manifest(project), 1)), 1)

    def test_reject_unlocked_and_duplicate_projects(self):
        for projects in [
            '<project name="p" revision="main"/>',
            '<project name="p" path="a"/>',
            '<project name="p" path="a" revision="' + '1' * 40 + '"/><project name="q" path="a" revision="' + '2' * 40 + '"/>',
        ]:
            with self.subTest(projects=projects), self.assertRaises((ValueError, source.ET.ParseError)):
                source.validate_manifest(manifest(projects), 1 if 'name="q"' not in projects else 2)

    def test_reject_unknown_directives_and_source_hosts(self):
        bad = [manifest().replace(b'android.googlesource.com', b'example.com'),
               manifest().replace(b'https://android', b'http://android'),
               manifest().replace(b'https://android', b'https://user:secret@android'),
               manifest('<include name="other.xml"/>'),
               manifest().replace(b'<manifest>', b'<!DOCTYPE x><manifest>')]
        for data in bad:
            with self.subTest(data=data), self.assertRaises(ValueError):
                source.validate_manifest(data, 1)

    def test_reject_copyfile_escape(self):
        project = '<project name="p" revision="' + '1' * 40 + '"><copyfile src="file" dest="../escape"/></project>'
        with self.assertRaises(ValueError):
            source.validate_manifest(manifest(project), 1)

    def test_reject_symlink_without_creating_external_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root'
            outside = Path(temp) / 'outside'
            root.mkdir()
            outside.mkdir()
            (root / 'link').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                source.write_new(root, 'link/new/file', b'x')
            self.assertFalse((outside / 'new').exists())

    def test_reject_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source.write_new(root, 'file', b'original')
            with self.assertRaises(FileExistsError):
                source.write_new(root, 'file', b'new')
            self.assertEqual((root / 'file').read_bytes(), b'original')

    def test_blob_corruption(self):
        with self.assertRaises(ValueError):
            source.verify_blob(b'damaged', entry())

    def test_large_content_falls_back_to_blob_endpoint(self):
        data = b'fixture'
        locked = entry(data)
        client = source.SourceClient('owner/repo', '1' * 40, 'test-credential')
        metadata = {'type': 'file', 'size': len(data), 'sha': locked['blob'], 'encoding': 'none'}
        blob = {'sha': locked['blob'], 'encoding': 'base64', 'content': base64.b64encode(data).decode()}
        with patch.object(client, 'request', side_effect=[metadata, blob]) as request:
            self.assertEqual(client.read(locked), data)
        self.assertTrue(request.call_args_list[1].args[0].startswith('/git/blobs/'))

    def test_no_token_redirects(self):
        request = urllib.request.Request('https://api.github.com/repos/owner/repo', headers={'Authorization': 'Bearer test-credential'})
        with self.assertRaises(ValueError):
            source.NoRedirect().redirect_request(request, None, 302, '', {}, 'https://example.com')

    def test_fetch_is_fresh_and_manifest_is_validated(self):
        data = manifest()
        lock = {'source': {'manifest_projects': 1, 'commit': '1' * 40}, 'files': [entry(data)]}
        class Client:
            def read(self, _):
                return data
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'inputs'
            source.fetch(lock, output, Client())
            self.assertEqual((output / 'default.xml').read_bytes(), data)
            self.assertEqual(json.loads((output / 'input-identities.json').read_text())['source_commit'], '1' * 40)
            with self.assertRaises(FileExistsError):
                source.fetch(lock, output, Client())


if __name__ == '__main__':
    unittest.main()
