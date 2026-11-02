# Requirements: Native traces/storage fixes with all patch checks before mutation.
# Ambiguity: shell fixtures do not prove Android compilation or device behavior.
# Research: preserve crypto configuration and distinguish storage/keystore waits.
# Optimization: execute only the real preflight fragment with a bounded Git stub.
# Risks: partial patching after failed checks or enabling paused Docker diagnostics.
# Validation: patch failures, fixed Native scope and plaintext/CMS delivery branches.
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_native import build_environment

ROOT = Path(__file__).resolve().parents[1]


class StartupDiagnosticsTests(unittest.TestCase):
    def preflight(self, enabled=None, failure='', repairs=None, target_version=None, layout=None):
        source = (ROOT / 'scripts/build.sh').read_text()
        start = source.index('trace_public_command recovery_patch_check\n')
        end = source.index('trace_public_command disk_preflight\n', start)
        program = '''set -eo pipefail
trace_public_command() { :; }
git() {
  printf '%s\\n' "$*"
  if [[ "$*" == "$FAILURE" ]]; then
    return 17
  fi
}
''' + source[start:end]
        environment = {'PATH': os.environ['PATH'], 'SELF': '/builder', 'FAILURE': failure}
        if enabled is not None:
            environment['SELENE_STARTUP_DIAGNOSTICS'] = enabled
        if repairs is not None:
            environment['SELENE_RECOVERY_FIXES'] = repairs
        if target_version is not None:
            environment['SELENE_TARGET_KEYMASTER_VERSION'] = target_version
        if layout is not None:
            environment['SELENE_RECOVERY_LAYOUT_FIXES'] = layout
        return subprocess.run(['bash', '-c', program], env=environment,
                              capture_output=True, text=True, timeout=5)

    def test_native_enables_diagnostics_without_accepting_parent_override(self):
        environment = build_environment({'SELENE_STARTUP_DIAGNOSTICS': '0',
                                         'BUILDER_PLAINTEXT_ONLY': '0',
                                         'TWRP_SOURCE_TOKEN': 'private-fixture'},
                                        Path('/builder'), Path('/work'))
        self.assertEqual(environment['SELENE_STARTUP_DIAGNOSTICS'], '1')
        self.assertEqual(environment['BUILDER_PLAINTEXT_ONLY'], '1')
        self.assertNotIn('TWRP_SOURCE_TOKEN', environment)

    def test_unset_or_disabled_mode_preserves_original_patch_sequence(self):
        for enabled in [None, '0']:
            with self.subTest(enabled=enabled):
                result = self.preflight(enabled)
                self.assertEqual(result.returncode, 0, result.stderr)
                commands = result.stdout.splitlines()
                self.assertEqual(len(commands), 6)
                self.assertNotIn('startup-diagnostics', result.stdout)
                self.assertNotIn('vold-keystore-diagnostics', result.stdout)

    def test_enabled_mode_checks_every_patch_before_any_apply(self):
        result = self.preflight('1')
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = result.stdout.splitlines()
        self.assertEqual(len(commands), 12)
        self.assertTrue(all('apply --check ' in command for command in commands[:6]))
        self.assertTrue(all('apply --check ' not in command for command in commands[6:]))
        self.assertEqual(commands[5], '-C system/security apply --check /builder/patches/keystore2-startup-diagnostics.patch')
        self.assertEqual(commands[-1], '-C system/security apply /builder/patches/keystore2-startup-diagnostics.patch')

    def test_diagnostic_precheck_failure_prevents_all_patch_mutations(self):
        failure = '-C system/security apply --check /builder/patches/keystore2-startup-diagnostics.patch'
        result = self.preflight('1', failure)
        self.assertEqual(result.returncode, 17)
        self.assertEqual(len(result.stdout.splitlines()), 6)
        self.assertTrue(all('apply --check ' in command
                            for command in result.stdout.splitlines()))

    def test_diagnostic_apply_failure_stops_before_vold_apply(self):
        failure = '-C bootable/recovery apply /builder/patches/recovery-startup-diagnostics.patch'
        result = self.preflight('1', failure)
        self.assertEqual(result.returncode, 17)
        self.assertEqual(result.stdout.splitlines()[-1], failure)
        self.assertNotIn('-C system/vold apply /builder/', result.stdout)

    def test_native_repairs_check_every_patch_before_any_mutation(self):
        result = self.preflight('1', repairs='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = result.stdout.splitlines()
        self.assertEqual(len(commands), 16)
        self.assertTrue(all('apply --check ' in command for command in commands[:8]))
        self.assertTrue(all('apply --check ' not in command for command in commands[8:]))
        self.assertTrue(commands[6].endswith('/patches/recovery-copylog-errors.patch'))
        self.assertTrue(commands[7].endswith('/patches/vold-key-storage-guard.patch'))

    def test_repair_precheck_failures_prevent_all_mutations(self):
        for project, patch in [('bootable/recovery', 'recovery-copylog-errors.patch'),
                               ('system/vold', 'vold-key-storage-guard.patch')]:
            failure = f'-C {project} apply --check /builder/patches/{patch}'
            with self.subTest(patch=patch):
                result = self.preflight('1', failure, repairs='1')
                self.assertEqual(result.returncode, 17)
                self.assertTrue(all('apply --check ' in command
                                    for command in result.stdout.splitlines()))

    def test_copylog_apply_failure_stops_before_key_storage_apply(self):
        failure = '-C bootable/recovery apply /builder/patches/recovery-copylog-errors.patch'
        result = self.preflight('1', failure, repairs='1')
        self.assertEqual(result.returncode, 17)
        self.assertEqual(result.stdout.splitlines()[-1], failure)
        self.assertNotIn('-C system/vold apply /builder/patches/vold-key-storage-guard.patch',
                         result.stdout)

    def test_target_version_is_prechecked_before_any_mutation(self):
        result = self.preflight('1', repairs='1', target_version='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = result.stdout.splitlines()
        self.assertEqual(len(commands), 18)
        self.assertTrue(all('apply --check ' in c for c in commands[:9]))
        self.assertTrue(commands[8].startswith('-C build/make apply --check '))
        self.assertTrue(commands[-1].startswith('-C build/make apply '))
        failure = commands[8]
        result = self.preflight('1', failure, repairs='1', target_version='1')
        self.assertEqual(result.returncode, 17)
        self.assertTrue(all('apply --check ' in c for c in result.stdout.splitlines()))

    def test_layout_patch_is_prechecked_with_all_native_patches(self):
        result = self.preflight('1', repairs='1', target_version='1', layout='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = result.stdout.splitlines()
        self.assertEqual(len(commands), 20)
        self.assertTrue(all('apply --check ' in c for c in commands[:10]))
        self.assertTrue(commands[9].endswith('/patches/recovery-layout-paths.patch'))
        self.assertEqual(commands[-1], '-C bootable/recovery apply /builder/patches/recovery-layout-paths.patch')
        result = self.preflight('1', commands[9], repairs='1', target_version='1', layout='1')
        self.assertEqual(result.returncode, 17)
        self.assertTrue(all('apply --check ' in c for c in result.stdout.splitlines()))

    def delivery(self, plaintext=None, seal_exit='0'):
        source = (ROOT / 'scripts/build.sh').read_text()
        start = source.index('# Native delivers the existing ready-to-use files;')
        program = '''set -eo pipefail
trace_public_command() { printf 'trace:%s\\n' "$1"; }
python3() { printf 'python:%s\\n' "$*"; return "$SEAL_EXIT"; }
set_stage() { printf 'stage:%s\\n' "$1"; }
''' + source[start:]
        environment = {'PATH': os.environ['PATH'], 'SELF': '/builder',
                       'WORK': '/work', 'SEAL_EXIT': seal_exit}
        if plaintext is not None:
            environment['BUILDER_PLAINTEXT_ONLY'] = plaintext
        return subprocess.run(['bash', '-c', program], env=environment,
                              capture_output=True, text=True, timeout=5)

    def test_native_plaintext_completes_without_invoking_sealer(self):
        result = self.delivery('1', seal_exit='17')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ['stage:complete'])

    def test_unset_or_disabled_plaintext_keeps_existing_docker_sealer(self):
        for enabled in [None, '0']:
            with self.subTest(enabled=enabled):
                result = self.delivery(enabled)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(), [
                    'trace:cms_seal',
                    'python:/builder/scripts/seal_output.py --output /work/output --certificate /builder/delivery-recipient.pem',
                    'stage:complete'])

    def test_existing_sealer_failure_preserves_real_failure(self):
        result = self.delivery(seal_exit='17')
        self.assertEqual(result.returncode, 17)
        self.assertNotIn('stage:complete', result.stdout)


if __name__ == '__main__':
    unittest.main()
