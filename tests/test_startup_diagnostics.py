# Requirements: Native-only startup traces with all patch checks before mutation.
# Ambiguity: shell fixtures do not prove Android compilation or device behavior.
# Research: preserve crypto configuration and distinguish storage/keystore waits.
# Optimization: execute only the real preflight fragment with a bounded Git stub.
# Risks: partial patching after failed checks or enabling paused Docker diagnostics.
# Validation: disabled mode, precheck failure, apply failure and fixed Native scope.
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_native import build_environment

ROOT = Path(__file__).resolve().parents[1]


class StartupDiagnosticsTests(unittest.TestCase):
    def preflight(self, enabled=None, failure=''):
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
        return subprocess.run(['bash', '-c', program], env=environment,
                              capture_output=True, text=True, timeout=5)

    def test_native_enables_diagnostics_without_accepting_parent_override(self):
        environment = build_environment({'SELENE_STARTUP_DIAGNOSTICS': '0',
                                         'TWRP_SOURCE_TOKEN': 'private-fixture'},
                                        Path('/builder'), Path('/work'))
        self.assertEqual(environment['SELENE_STARTUP_DIAGNOSTICS'], '1')
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
        self.assertEqual(len(commands), 10)
        self.assertTrue(all('apply --check ' in command for command in commands[:5]))
        self.assertTrue(all('apply --check ' not in command for command in commands[5:]))
        self.assertEqual(commands[4], '-C system/vold apply --check /builder/patches/vold-keystore-diagnostics.patch')
        self.assertEqual(commands[-1], '-C system/vold apply /builder/patches/vold-keystore-diagnostics.patch')

    def test_diagnostic_precheck_failure_prevents_all_patch_mutations(self):
        failure = '-C system/vold apply --check /builder/patches/vold-keystore-diagnostics.patch'
        result = self.preflight('1', failure)
        self.assertEqual(result.returncode, 17)
        self.assertEqual(len(result.stdout.splitlines()), 5)
        self.assertTrue(all('apply --check ' in command
                            for command in result.stdout.splitlines()))

    def test_diagnostic_apply_failure_stops_before_vold_apply(self):
        failure = '-C bootable/recovery apply /builder/patches/recovery-startup-diagnostics.patch'
        result = self.preflight('1', failure)
        self.assertEqual(result.returncode, 17)
        self.assertEqual(result.stdout.splitlines()[-1], failure)
        self.assertNotIn('-C system/vold apply /builder/', result.stdout)


if __name__ == '__main__':
    unittest.main()
