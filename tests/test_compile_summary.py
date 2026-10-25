# Requirements: synthetic public Git data and compiler errors only.
# Ambiguity: private or unverified diagnostic values must be omitted.
# Research: dependencies are eligible only when literal in a pinned public blob.
# Optimization: tiny synthetic repositories; no Android source downloads.
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
from report_progress import public_module_catalog, public_module_names, record


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

    def test_multiple_failures_in_one_public_file_are_all_reported(self):
        (self.project / 'Android.bp').write_text('cc_library { name: "demo", shared_libs: ["libpublic", "libother"] }\n')
        self.git('add', '.')
        self.git('commit', '--quiet', '-m', 'additional public dependency')
        revision = self.git('rev-parse', 'HEAD').strip()
        manifest = self.manifest.replace(self.revision.encode(), revision.encode())
        result = summarize('external/public/Android.bp:1: depends on undefined module "libpublic"\n'
                           'external/public/Android.bp:1: depends on undefined module "libother"',
                           manifest, self.source)
        self.assertEqual(result['public_dependencies'], ['libother', 'libpublic'])
        self.assertEqual(len(result['public_locations']), 1)

    def test_invalid_apex_name_requires_public_blob_and_progress_recheck(self):
        (self.project / 'Android.bp').write_text(
            'cc_library { name: "demo", apex_available: ["com.android.public"] }\n')
        self.git('add', '.')
        self.git('commit', '--quiet', '-m', 'public apex fixture')
        revision = self.git('rev-parse', 'HEAD').strip()
        manifest = self.manifest.replace(self.revision.encode(), revision.encode())
        result = summarize(
            'external/public/Android.bp:1: module demo: apex_available: '
            '"com.android.public" is not a valid module name\n'
            'external/public/Android.bp:1: apex_available: '
            '"private_value" is not a valid module name', manifest, self.source)
        self.assertEqual(result['public_dependencies'], ['com.android.public'])
        self.assertIn('INVALID_APEX_AVAILABLE', result['categories'])
        value = record({'stage': 'compile', 'exit_code': 1}, 42, 'a' * 40,
                       result, self.source, manifest)
        self.assertEqual(value['public_dependencies'], ['com.android.public'])
        self.assertEqual(value['categories'], ['INVALID_APEX_AVAILABLE'])
        self.assertNotIn('private_value', json.dumps(value))

    def test_invalid_apex_worktree_and_excluded_overlay_never_authorize_names(self):
        (self.project / 'Android.bp').write_text('apex_available: ["private_value"]\n')
        message = ('external/public/Android.bp:1: apex_available: '
                   '"private_value" is not a valid module name')
        for excluded in ((), ('external/public/Android.bp',)):
            with self.subTest(excluded=excluded):
                result = summarize(message, self.manifest, self.source, excluded)
                self.assertEqual(result['public_dependencies'], [])
                self.assertNotIn('private_value', json.dumps(result))

    def test_progress_mirror_rechecks_names_and_drops_private_content(self):
        value = record({'stage': 'compile', 'exit_code': 1, 'raw': 'private'}, 42, 'a' * 40,
                       {'categories': ['UNDEFINED_MODULE', 'private'],
                        'public_locations': [{'path': 'external/public/Android.bp', 'line': 1},
                                             {'path': '../private', 'line': 1}],
                        'public_dependencies': ['libpublic', 'private'], 'raw': 'secret'},
                       self.source, self.manifest)
        self.assertEqual(value['public_dependencies'], ['libpublic'])
        self.assertEqual(value['categories'], ['UNDEFINED_MODULE'])
        self.assertNotIn('private', json.dumps(value))
        self.assertNotIn('secret', json.dumps(value))

    def test_module_catalog_uses_pinned_git_and_ignores_private_worktree(self):
        (self.project / 'Named.bp').write_text('cc_library {\n    name: "public_catalog_name",\n}\n')
        self.git('add', '.')
        self.git('commit', '--quiet', '-m', 'public catalog fixture')
        revision = self.git('rev-parse', 'HEAD').strip()
        manifest = self.manifest.replace(self.revision.encode(), revision.encode())
        (self.project / 'Named.bp').write_text('name: "private_worktree_value"\n')
        (self.project / 'Untracked.bp').write_text('name: "private_untracked_value"\n')
        names = public_module_names(manifest, self.source)
        self.assertIn('public_catalog_name', names)
        self.assertNotIn('private_worktree_value', names)
        self.assertNotIn('private_untracked_value', names)

    def test_module_catalog_rejects_wrong_commit(self):
        manifest = self.manifest.replace(self.revision.encode(), b'1' * 40)
        with self.assertRaises(ValueError):
            public_module_names(manifest, self.source)

    def test_catalog_distinguishes_project_origins_without_exporting_worktree_data(self):
        (self.project / 'Names.bp').write_text(
            'cc_library {\n name: "source_only",\n}\n'
            'cc_library {\n name: "shared_name",\n}\n')
        self.git('add', '.')
        self.git('commit', '--quiet', '-m', 'source origin fixture')
        manifest = self.manifest.replace(self.revision.encode(), self.git('rev-parse', 'HEAD').strip().encode())
        prebuilt = self.source / 'prebuilts/public'
        prebuilt.mkdir(parents=True)

        def git(*args):
            return subprocess.check_output([
                'git', '-C', str(prebuilt), '-c', 'user.name=test',
                '-c', 'user.email=test@example.invalid', *args],
                text=True, stderr=subprocess.DEVNULL)

        git('init', '--quiet')
        (prebuilt / 'Android.bp').write_text(
            'cc_prebuilt_library {\n name: "prebuilt_only",\n}\n'
            'cc_prebuilt_library {\n name: "shared_name",\n}\n')
        git('add', '.')
        git('commit', '--quiet', '-m', 'prebuilts origin fixture')
        revision = git('rev-parse', 'HEAD').strip()
        manifest = manifest.replace(b'</manifest>', (
            '<project name="platform/prebuilts/public" path="prebuilts/public" revision="'
            + revision + '"/></manifest>').encode())
        (self.project / 'Names.bp').write_text('name: "private_source_worktree"\n')
        (prebuilt / 'Android.bp').write_text('name: "private_prebuilt_worktree"\n')
        (prebuilt / 'Untracked.bp').write_text('name: "private_untracked"\n')
        catalog = public_module_catalog(manifest, self.source)
        self.assertEqual(catalog['public_module_names'], ['prebuilt_only', 'shared_name', 'source_only'])
        self.assertEqual(catalog['public_prebuilts_project_only_names'], ['prebuilt_only'])
        self.assertNotIn('private_', json.dumps(catalog))

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

    def add_public_default(self, name='inherited.bp'):
        text = ('package public\nvar inherited = "libinherited"\n' if name.endswith('.go') else
                'java_defaults { name: "public_defaults", libs: ["libinherited"] }\n')
        (self.project / name).write_text(text)
        self.git('add', name)
        self.git('commit', '--quiet', '-m', 'public inherited dependency fixture')
        revision = self.git('rev-parse', 'HEAD').strip()
        return self.manifest.replace(self.revision.encode(), revision.encode())

    def test_soong_bare_list_keeps_only_pinned_public_dependency_names(self):
        result = summarize('external/public/Android.bp:1: module demo missing dependencies: libpublic, secret_value',
                           self.manifest, self.source)
        self.assertEqual(result['public_dependencies'], ['libpublic'])
        self.assertNotIn('secret_value', json.dumps(result))

    def test_inherited_dependency_requires_separate_pinned_public_evidence(self):
        manifest = self.add_public_default()
        text = 'external/public/Android.bp:1: depends on undefined module "libinherited"'
        result = summarize(text, manifest, self.source)
        self.assertEqual(result['public_dependencies'], ['libinherited'])
        self.assertEqual(result['public_locations'], [{'path': 'external/public/Android.bp', 'line': 1}])
        self.assertEqual(result['public_dependency_sources'], [
            {'path': 'external/public/inherited.bp', 'line': 1, 'dependencies': ['libinherited']}])
        value = record({'stage': 'compile', 'exit_code': 1}, 42, 'a' * 40,
                       result, self.source, manifest)
        self.assertEqual(value['public_dependencies'], ['libinherited'])
        self.assertEqual(value['public_dependency_sources'], result['public_dependency_sources'])

    def test_go_generated_dependency_literal_can_be_verified_without_exporting_code(self):
        manifest = self.add_public_default('generated.go')
        result = summarize('external/public/Android.bp:1: module demo missing dependencies: libinherited',
                           manifest, self.source)
        self.assertEqual(result['public_dependencies'], ['libinherited'])
        self.assertTrue(result['public_dependency_sources'][0]['path'].endswith('generated.go'))
        self.assertNotIn('java_defaults', json.dumps(result))

    def test_excluded_default_file_never_authorizes_a_dependency(self):
        manifest = self.add_public_default()
        result = summarize('external/public/Android.bp:1: depends on undefined module "libinherited"',
                           manifest, self.source, {'external/public/inherited.bp'})
        self.assertEqual(result['public_dependencies'], [])
        self.assertNotIn('public_dependency_sources', result)

    def test_private_error_location_cannot_trigger_global_public_literal_search(self):
        manifest = self.add_public_default()
        result = summarize('external/public/BoardConfig.mk:1: depends on undefined module "libinherited"',
                           manifest, self.source, {'external/public/BoardConfig.mk'})
        self.assertEqual(result['public_dependencies'], [])
        self.assertNotIn('public_dependency_sources', result)

    def test_progress_rechecks_global_evidence_instead_of_trusting_summary_fields(self):
        manifest = self.add_public_default()
        (self.project / 'inherited.bp').write_text('name: "private_worktree_value"\n')
        summary = {'categories': ['UNDEFINED_MODULE'], 'public_locations': [],
                   'public_dependencies': ['libinherited', 'private_worktree_value'],
                   'public_dependency_sources': [
                       {'path': 'external/public/inherited.bp', 'line': 1,
                        'dependencies': ['libinherited', 'private_worktree_value']} ]}
        value = record({'stage': 'compile', 'exit_code': 1}, 42, 'a' * 40,
                       summary, self.source, manifest)
        self.assertEqual(value['public_dependencies'], ['libinherited'])
        self.assertNotIn('private_worktree_value', json.dumps(value))
        excluded = record({'stage': 'compile', 'exit_code': 1}, 42, 'a' * 40,
                          summary, self.source, manifest, {'external/public/inherited.bp'})
        self.assertEqual(excluded['public_dependencies'], [])

    def test_unknown_name_in_another_worktree_file_is_not_public_evidence(self):
        (self.project / 'untracked.go').write_text('var Name = "private_worktree_value"\n')
        result = summarize('external/public/Android.bp:1: module demo missing dependencies: private_worktree_value',
                           self.manifest, self.source)
        self.assertEqual(result['public_dependencies'], [])
        self.assertNotIn('private_worktree_value', json.dumps(result))

    def commit_public_label(self, name='Android.bp', value='libpublic'):
        (self.project / name).write_text(
            'filegroup { name: "public_sources", srcs: [":' + value + '"] }\n')
        self.git('add', name)
        self.git('commit', '--quiet', '-m', 'public source label fixture')
        revision = self.git('rev-parse', 'HEAD').strip()
        return self.manifest.replace(self.revision.encode(), revision.encode())

    def test_source_label_is_confirmed_and_rechecked_by_progress(self):
        manifest = self.commit_public_label()
        for message in ('depends on undefined module "libpublic"',
                        'depends on undefined module ":libpublic"',
                        'module demo missing dependencies: :libpublic, private_value'):
            with self.subTest(message=message):
                summary = summarize('external/public/Android.bp:1: ' + message,
                                    manifest, self.source)
                self.assertEqual(summary['public_dependencies'], ['libpublic'])
                value = record({'stage': 'compile', 'exit_code': 1}, 42, 'a' * 40,
                               summary, self.source, manifest)
                self.assertEqual(value['public_dependencies'], ['libpublic'])
                self.assertNotIn('private_value', json.dumps(value))

    def test_inherited_source_label_requires_pinned_evidence(self):
        manifest = self.commit_public_label('inherited.bp', 'libinherited')
        summary = summarize('external/public/Android.bp:1: '
                            'depends on undefined module "libinherited"',
                            manifest, self.source)
        self.assertEqual(summary['public_dependencies'], ['libinherited'])
        self.assertEqual(summary['public_dependency_sources'], [
            {'path': 'external/public/inherited.bp', 'line': 1,
             'dependencies': ['libinherited']}])
        value = record({'stage': 'compile', 'exit_code': 1}, 42, 'a' * 40,
                       summary, self.source, manifest)
        self.assertEqual(value['public_dependencies'], ['libinherited'])
        excluded = summarize('external/public/Android.bp:1: '
                             'depends on undefined module "libinherited"',
                             manifest, self.source, {'external/public/inherited.bp'})
        self.assertEqual(excluded['public_dependencies'], [])

    def test_private_source_labels_in_worktree_do_not_authorize_names(self):
        manifest = self.commit_public_label()
        (self.project / 'Android.bp').write_text('srcs: [":private_label"]\n')
        (self.project / 'Untracked.bp').write_text('srcs: [":private_label"]\n')
        summary = summarize('external/public/Android.bp:1: '
                            'depends on undefined module ":private_label"',
                            manifest, self.source)
        self.assertEqual(summary['public_dependencies'], [])
        forged = dict(summary, public_dependencies=['private_label'])
        value = record({'stage': 'compile', 'exit_code': 1}, 42, 'a' * 40,
                       forged, self.source, manifest)
        self.assertEqual(value['public_dependencies'], [])
        self.assertNotIn('private_label', json.dumps(value))

    def test_source_label_partial_matches_and_path_labels_remain_unverified(self):
        manifest = self.commit_public_label(value='libpublic_suffix')
        for name in ('libpublic', 'public_suffix', 'path/to/libpublic',
                     '//namespace:libpublic'):
            with self.subTest(name=name):
                summary = summarize('external/public/Android.bp:1: '
                                    'depends on undefined module "' + name + '"',
                                    manifest, self.source)
                self.assertEqual(summary['public_dependencies'], [])
