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
import subprocess
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


def public_fixture():
    data = manifest().replace(b'<default remote="aosp"/>',
                              b'<default remote="aosp" revision="refs/tags/android-12.1.0_r4"/>')
    lock = {'source': {'manifest_projects': 1, 'commit': '1' * 40}, 'files': [entry(data)],
            'public_projects': [{'name': 'platform/cts', 'path': 'cts', 'revision': '2' * 40,
                                 'upstream': 'refs/tags/android-12.1.0_r4'}]}
    return data, lock


class InputTests(unittest.TestCase):
    def test_repository_lock(self):
        lock = source.load_lock()
        self.assertEqual(len(lock['files']), 10)
        self.assertEqual(lock['source']['manifest_projects'], 282)
        self.assertEqual(lock['device']['overlay_files'], 4)
        self.assertEqual(lock['build']['target'], 'bootimage')
        self.assertGreaterEqual(len(lock['public_projects']), 3)
        self.assertEqual(lock['public_projects'][0]['name'], 'platform/cts')
        self.assertEqual(lock['public_projects'][1]['name'], 'platform/platform_testing')
        self.assertEqual(lock['public_projects'][2]['name'], 'platform/tools/tradefederation/prebuilts')

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

    def test_compose_preserves_archive_and_adds_a_pinned_public_project(self):
        data, lock = public_fixture()
        effective = source.compose_manifest(lock, data)
        root = source.ET.fromstring(effective)
        self.assertEqual(len(root.findall('project')), 2)
        self.assertEqual(source.ET.tostring(root.findall('project')[0]),
                         source.ET.tostring(source.ET.fromstring(data).find('project')))
        cts = root.findall('project')[1]
        self.assertEqual(cts.get('revision'), '2' * 40)
        self.assertEqual(cts.get('remote'), 'builder-reviewed-aosp')
        self.assertEqual(cts.get('clone-depth'), '1')
        self.assertEqual(len(lock['files']), 1)
        source.verify_blob(data, lock['files'][0])

    def test_compose_rejects_changed_archive_manifest(self):
        data, lock = public_fixture()
        with self.assertRaises(ValueError):
            source.compose_manifest(lock, data + b'\n')

    def test_reviewed_public_device_and_kernel_alias_compose_without_private_changes(self):
        for name, path in [('device/google/cuttlefish', 'device/google/cuttlefish'),
                           ('kernel/prebuilts/5.10/x86-64', 'kernel/prebuilts/5.10/x86_64')]:
            with self.subTest(name=name):
                data, lock = public_fixture()
                lock['public_projects'][0].update(name=name, path=path)
                effective = source.ET.fromstring(source.compose_manifest(lock, data))
                added = effective.findall('project')[1]
                self.assertEqual((added.get('name'), added.get('path')), (name, path))
                self.assertEqual(added.get('remote'), 'builder-reviewed-aosp')
                self.assertEqual(len(lock['files']), 1)
                source.verify_blob(data, lock['files'][0])

    def test_nonplatform_public_names_require_the_exact_reviewed_name_path_pair(self):
        for name, path in [('device/google/cuttlefish', 'device/google/other'),
                           ('device/unreviewed/project', 'device/google/cuttlefish'),
                           ('kernel/prebuilts/5.10/x86_64', 'kernel/prebuilts/5.10/x86_64'),
                           ('kernel/prebuilts/5.10/x86-64', 'kernel/prebuilts/5.10/arm64')]:
            with self.subTest(name=name, path=path):
                data, lock = public_fixture()
                lock['public_projects'][0].update(name=name, path=path)
                with self.assertRaises(ValueError):
                    source.compose_manifest(lock, data)

    def test_compose_rejects_unlocked_or_unreviewed_public_projects(self):
        for key, value in [('revision', 'main'), ('path', '../escape'),
                           ('name', 'unreviewed/project'), ('upstream', 'main'),
                           ('fetch', 'https://example.com')]:
            with self.subTest(key=key):
                data, lock = public_fixture()
                lock['public_projects'][0][key] = value
                with self.assertRaises(ValueError):
                    source.compose_manifest(lock, data)

    def test_compose_rejects_names_paths_versions_and_remote_collisions(self):
        for key, value in [('name', 'platform/build'), ('path', 'build'),
                           ('path', 'build/make'), ('path', 'build/make/child'),
                           ('upstream', 'refs/tags/android-13.0.0_r1')]:
            with self.subTest(key=key, value=value):
                data, lock = public_fixture()
                lock['public_projects'][0][key] = value
                with self.assertRaises(ValueError):
                    source.compose_manifest(lock, data)
        data, lock = public_fixture()
        data = data.replace(b'</manifest>', b'<remote name="builder-reviewed-aosp" '
                            b'fetch="https://github.com"/></manifest>')
        lock['files'] = [entry(data)]
        with self.assertRaises(ValueError):
            source.compose_manifest(lock, data)

    def test_compose_rejects_copy_destinations_and_duplicate_additions(self):
        data, lock = public_fixture()
        data = data.replace(b'"1' + b'1' * 39 + b'"/>',
                            b'"' + b'1' * 40 + b'"><linkfile src="x" dest="cts/input"/></project>')
        lock['files'] = [entry(data)]
        with self.assertRaises(ValueError):
            source.compose_manifest(lock, data)
        data, lock = public_fixture()
        lock['public_projects'] *= 2
        with self.assertRaises(ValueError):
            source.compose_manifest(lock, data)

    def test_checkout_checks_public_revision_and_clean_state(self):
        data, lock = public_fixture()
        with tempfile.TemporaryDirectory() as temp:
            manifest_file = Path(temp) / 'default.xml'
            manifest_file.write_bytes(data)
            for outputs, passes in [(['1' * 40, '', '2' * 40, ''], True),
                                    (['1' * 40, '', '3' * 40], False),
                                    (['1' * 40, '', '2' * 40, ' M Android.bp'], False)]:
                with self.subTest(outputs=outputs), patch.object(
                        source.subprocess, 'check_output', side_effect=outputs) as call:
                    if passes:
                        self.assertEqual(source.verify_checkout(lock, manifest_file, temp), 2)
                        self.assertEqual(call.call_args_list[2].args[0][2], str(Path(temp) / 'cts'))
                    else:
                        with self.assertRaises(ValueError):
                            source.verify_checkout(lock, manifest_file, temp)

    def test_compose_cli_creates_new_output_without_overwriting(self):
        data, lock = public_fixture()
        lock.update(schema=1)
        lock['source']['repository'] = 'owner/repo'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'input.xml').write_bytes(data)
            (root / 'lock.json').write_text(json.dumps(lock))
            command = [sys.executable, str(Path(source.__file__)), '--lock', str(root / 'lock.json'),
                       'compose', '--manifest', str(root / 'input.xml'), '--output', str(root / 'output.xml')]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / 'output.xml').read_bytes(), source.compose_manifest(lock, data))
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 1)
            self.assertEqual((root / 'input.xml').read_bytes(), data)
            self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
