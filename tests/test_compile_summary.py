# Requirements: synthetic public Git data and compiler errors only.
# Ambiguity: private or unverified diagnostic values must be omitted.
# Research: dependencies are eligible only when literal in a pinned public blob.
# Optimization: one tiny repository per test case; no Android source downloads.
# Risks: arbitrary paths, edited overlays, untracked files and source disclosure.
# Validation: exact Git revision, excluded overlays and non-disclosure assertions.
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from summarize_compile_failure import summarize


class CompileSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name)
        self.project = self.source / 'external/public'
        self.project.mkdir(parents=True)
        self.git('init', '--quiet')
        self.git('config', 'user.name', 'test')
        self.git('config', 'user.email', 'test@example.invalid')
        (self.project / 'Android.bp').write_text('cc_library { name: "demo", shared_libs: ["libpublic"] }\n')
        (self.project / 'BoardConfig.mk').write_text('PUBLIC_SETTING := 1\n')
        self.git('add', '.')
        self.git('commit', '--quiet', '-m', 'public fixture')
        self.revision = self.git('rev-parse', 'HEAD').strip()
        self.manifest = ('<manifest><project name="platform/public" path="external/public" revision="'
                         + self.revision + '"/></manifest>').encode()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.project), *args],
                                       text=True, stderr=subprocess.DEVNULL)

    def test_confirmed_public_location_and_dependency(self):
        result = summarize('error: external/public/Android.bp:1:1: "demo" depends on undefined module "libpublic".',
                           self.manifest, self.source)
        self.assertEqual(result['public_locations'], [{'path': 'external/public/Android.bp', 'line': 1}])
        self.assertEqual(result['public_dependencies'], ['libpublic'])
        self.assertIn('UNDEFINED_MODULE', result['categories'])

    def test_private_values_and_messages_are_not_returned(self):
        result = summarize('error: external/public/Android.bp:1:1: depends on undefined module "secretvalue". '
                           'private fstab contents https://private.example?token=secretvalue',
                           self.manifest, self.source)
        encoded = json.dumps(result)
        for value in ('secretvalue', 'fstab', 'private.example', 'cc_library'):
            self.assertNotIn(value, encoded)
        self.assertEqual(result['public_dependencies'], [])

    def test_worktree_edit_does_not_authorize_private_identifier(self):
        (self.project / 'Android.bp').write_text('name: "secretvalue"\n')
        result = summarize('external/public/Android.bp:1:1: depends on undefined module "secretvalue"',
                           self.manifest, self.source)
        self.assertEqual(result['public_dependencies'], [])

    def test_private_overlay_is_excluded_even_if_upstream_tracks_it(self):
        result = summarize('external/public/BoardConfig.mk:1: error private overlay', self.manifest,
                           self.source, {'external/public/BoardConfig.mk'})
        self.assertEqual(result['public_locations'], [])

    def test_untracked_and_traversal_paths_are_not_returned(self):
        (self.project / 'private.mk').write_text('secretvalue')
        result = summarize('external/public/private.mk:1: error\n'
                           '../secret.mk:2: error\nunknown/private.mk:3: error',
                           self.manifest, self.source)
        self.assertEqual(result['public_locations'], [])

    def test_wrong_revision_cannot_authorize_metadata(self):
        manifest = self.manifest.replace(self.revision.encode(), b'1' * 40)
        result = summarize('external/public/Android.bp:1: error', manifest, self.source)
        self.assertEqual(result['public_locations'], [])

    def test_unknown_failure_remains_unclassified(self):
        result = summarize('error: arbitrary private content', self.manifest, self.source)
        self.assertEqual(result, {'categories': ['UNCLASSIFIED_COMPILE_FAILURE'],
                                  'public_locations': [], 'public_dependencies': []})

    def test_host_capacity_and_tool_categories(self):
        result = summarize('error while loading shared libraries: private.so\nNo space left on device',
                           self.manifest, self.source)
        self.assertIn('DISK_EXHAUSTED', result['categories'])
        self.assertIn('HOST_TOOL_EXECUTION_FAILURE', result['categories'])
        self.assertNotIn('private.so', json.dumps(result))
