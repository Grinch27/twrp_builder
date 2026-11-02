# Requirements: verify fixed Native inputs, credential separation and real child exits.
# Ambiguity: fixture execution does not prove an Android build or host isolation.
# Research: execute real subprocesses and evaluate synthetic BoardConfig with Make.
# Optimization: minimal temporary builder and short status polling.
# Risks: inherited credentials, overwritten overlays or unintended fastbootd changes.
# Validation: environment, overlay order, normal boot versus fastbootd, exits and logs.
import contextlib
import io
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_native import build_environment, run_build, safe_command_events


class NativeTests(unittest.TestCase):
    def normal_boot_overlay(self, native=False, enabled=None, fastbootd='true',
                            config_kind='regular'):
        source = (Path(__file__).resolve().parents[1] / 'scripts/build.sh').read_text()
        start = source.index('trace_public_command overlay_copy\n')
        end = source.index('trace_public_command stock_prebuilts_copy\n', start)
        fragment = source[start:end]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / 'isolated work'
            checkout = work / 'android'
            relative = Path('device/xiaomi/selene/BoardConfig.mk')
            overlay = work / 'inputs/overlay' / relative
            target = checkout / relative
            overlay.parent.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            # Deliberately no trailing newline: the appended assignment must still parse.
            original = ('TW_NO_FASTBOOT_BOOT := false\n'
                        f'TW_INCLUDE_FASTBOOTD := {fastbootd}\n'
                        'TW_INCLUDE_CRYPTO := true\n'
                        'SYNTHETIC_ORIGIN := overlay').encode()
            outside = root / 'unrelated.mk'
            outside.write_bytes(b'UNRELATED := unchanged\n')
            if config_kind == 'regular':
                overlay.write_bytes(original)
                target.write_bytes(b'SYNTHETIC_ORIGIN := checkout\n')
            elif config_kind == 'symlink':
                overlay.symlink_to(outside)
            elif config_kind != 'missing':
                self.fail('unsupported synthetic BoardConfig fixture')
            parent = {'PATH': os.defpath}
            if enabled is not None:
                parent['SELENE_NORMAL_BOOT'] = enabled
            environment = (build_environment(parent, root / 'builder', work)
                           if native else parent)
            environment['WORK'] = str(work)
            program = (
                'set -euo pipefail\n'
                'trace_public_command() {\n'
                '  printf "2026-11-02T00:00:00Z %s\\n" "$1" >> "${WORK}/trace.log"\n'
                '}\n' + fragment + 'make --no-print-directory -s -f - show\n')
            makefile = (
                'include device/xiaomi/selene/BoardConfig.mk\n'
                '.PHONY: show\nshow:\n'
                '\t@printf "%s\\n" "$(TW_NO_FASTBOOT_BOOT)" "$(TW_INCLUDE_FASTBOOTD)" '
                '"$(TW_INCLUDE_CRYPTO)" "$(SYNTHETIC_ORIGIN)"\n')
            result = subprocess.run(['bash', '-c', program], cwd=checkout,
                                    env=environment, input=makefile,
                                    capture_output=True, text=True, timeout=10)
            trace = work / 'trace.log'
            events, _ = safe_command_events(trace)
            return {
                'status': result.returncode, 'stderr': result.stderr,
                'make_values': result.stdout.splitlines(),
                'target_bytes': target.read_bytes() if target.is_file() else None,
                'target_is_symlink': target.is_symlink(),
                'overlay_bytes': overlay.read_bytes() if overlay.is_file() else None,
                'original': original, 'outside_bytes': outside.read_bytes(),
                'public_events': [event[1] for event in events],
            }

    def test_native_normal_boot_overrides_parent_and_preserves_fastbootd_and_crypto(self):
        for enabled in (None, '0', 'false', ''):
            for fastbootd in ('true', 'false'):
                with self.subTest(parent_value=enabled, fastbootd=fastbootd):
                    result = self.normal_boot_overlay(native=True, enabled=enabled,
                                                      fastbootd=fastbootd)
                    self.assertEqual(result['status'], 0, result['stderr'])
                    self.assertEqual(result['make_values'], ['true', fastbootd, 'true', 'overlay'])
                    self.assertTrue(result['target_bytes'].startswith(result['original']))
                    self.assertEqual(result['overlay_bytes'], result['original'])
                    self.assertEqual(result['public_events'], ['overlay_copy', 'normal_boot_overlay'])

    def test_non_native_unset_or_disabled_normal_boot_preserves_overlay_bytes(self):
        for enabled in (None, '0'):
            with self.subTest(enabled=enabled):
                result = self.normal_boot_overlay(enabled=enabled)
                self.assertEqual(result['status'], 0, result['stderr'])
                self.assertEqual(result['make_values'], ['false', 'true', 'true', 'overlay'])
                self.assertEqual(result['target_bytes'], result['original'])
                self.assertEqual(result['overlay_bytes'], result['original'])
                self.assertEqual(result['public_events'], ['overlay_copy'])

    def test_normal_boot_rejects_missing_or_symlinked_board_config(self):
        for config_kind in ('missing', 'symlink'):
            with self.subTest(config_kind=config_kind):
                result = self.normal_boot_overlay(native=True, config_kind=config_kind)
                self.assertNotEqual(result['status'], 0)
                self.assertEqual(result['make_values'], [])
                self.assertEqual(result['public_events'], ['overlay_copy'])
                self.assertEqual(result['outside_bytes'], b'UNRELATED := unchanged\n')
                self.assertEqual(result['target_is_symlink'], config_kind == 'symlink')
                if config_kind == 'missing':
                    self.assertIsNone(result['target_bytes'])

    def test_normal_boot_overlay_precedes_android_configuration_and_compilation(self):
        source = (Path(__file__).resolve().parents[1] / 'scripts/build.sh').read_text()
        overlay = source.index('cp -a "${WORK}/inputs/overlay/." "${WORK}/android/"\n')
        guard = source.index('if [[ "${SELENE_NORMAL_BOOT:-0}" == 1 ]]; then\n')
        configured = source.index('trace_public_command envsetup_lunch\n')
        compile_step = source.index('trace_public_command bootimage_compile\n')
        self.assertLess(overlay, guard)
        self.assertLess(guard, configured)
        self.assertLess(configured, compile_step)

    def test_public_native_outputs_contain_only_boot_img(self):
        source = (Path(__file__).resolve().parents[1] /
                  '.github/workflows/twrp_native.yml').read_text()
        upload = source.split('      - name: Upload plaintext boot image\n', 1)[1].split(
            '      - name: Publish an explicitly approved prerelease\n', 1)[0]
        self.assertIn('path: ${{ env.BUILD_ROOT }}/output/boot.img', upload)
        self.assertIn('if-no-files-found: error', upload)
        self.assertNotIn('static-validation.json', upload)
        self.assertNotIn('SHA256SUMS', upload)
        self.assertNotIn('sealed', upload)
        release = source.split('      - name: Publish an explicitly approved prerelease\n', 1)[1].split(
            '      - name: Record validation boundary\n', 1)[0]
        self.assertIn('"${BUILD_ROOT}/output/boot.img"', release)
        self.assertNotIn('static-validation.json', release)
        self.assertNotIn('SHA256SUMS', release)
        self.assertNotIn('sealed', release)

    def test_compile_child_uses_available_cpus_plus_one_verbose_ninja_and_real_exit(self):
        source = (Path(__file__).resolve().parents[1] / 'scripts/build.sh').read_text()
        child = re.search(r"160m bash -c '(.*?)' >", source, re.S).group(1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'build').mkdir()
            for cpus in [1, 4, 8]:
                (root / 'build/envsetup.sh').write_text(
                    'nproc() { printf "%s\\n" ' + str(cpus) + '; }\n'
                    'lunch() { [[ "$1" == twrp_selene-eng ]]; }\n'
                    'mka() { [[ "$1" == bootimage && "$2" == -j'
                    + str(cpus + 1) + ' && "$NINJA_ARGS" == -v ]] || return 99; return 7; }\n')
                result = subprocess.run(['bash', '-c', child], cwd=root,
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 7)

    def test_child_environment_omits_all_ci_and_unrelated_values(self):
        parent = {'PATH': '/usr/bin:/bin', 'HOME': '/unchanged', 'LANG': 'C.UTF-8',
                  'GH_TOKEN': 'secret', 'GITHUB_TOKEN': 'secret', 'TWRP_SOURCE_TOKEN': 'secret',
                  'ACTIONS_RUNTIME_TOKEN': 'secret', 'GITHUB_ENV': '/private',
                  'UNRELATED_SECRET': 'secret', 'JAVA_HOME': '/host-java', 'LD_PRELOAD': '/private',
                  'SELENE_STOCK_TEE_CLIENT': '0', 'SELENE_NORMAL_BOOT': '0',
                  'SELENE_RECOVERY_FIXES': '0'}
        result = build_environment(parent, Path('/builder'), Path('/work'))
        self.assertEqual(result, {'PATH': '/usr/bin:/bin', 'HOME': '/unchanged', 'LANG': 'C.UTF-8',
                                 'BUILDER_SELF': '/builder', 'BUILD_ROOT': '/work',
                                 'GIT_TERMINAL_PROMPT': '0', 'SELENE_STARTUP_DIAGNOSTICS': '1',
                                 'BUILDER_PLAINTEXT_ONLY': '1', 'SELENE_STOCK_TEE_CLIENT': '1',
                                 'SELENE_NORMAL_BOOT': '1', 'SELENE_RECOVERY_FIXES': '1'})

    def test_child_gets_only_valid_public_builder_commit_metadata(self):
        result = build_environment({'GITHUB_SHA': 'a' * 40, 'GH_TOKEN': 'secret'},
                                   Path('/builder'), Path('/work'))
        self.assertEqual(result['GITHUB_SHA'], 'a' * 40)
        self.assertNotIn('GH_TOKEN', result)
        self.assertNotIn('GITHUB_SHA', build_environment({'GITHUB_SHA': 'private text'},
                                                       Path('/builder'), Path('/work')))

    def test_real_failure_is_returned_without_printing_private_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            builder, work = root / 'builder', root / 'work'
            (builder / 'scripts').mkdir(parents=True)
            work.mkdir()
            (builder / 'scripts/build.sh').write_text('''#!/usr/bin/env bash
test -z "${GH_TOKEN:-}${GITHUB_TOKEN:-}${TWRP_SOURCE_TOKEN:-}${ACTIONS_RUNTIME_TOKEN:-}" || exit 99
printf 'private fixture compiler diagnostics\\n'
printf '{"stage":"compile","exit_code":7}\\n' > "${BUILD_ROOT}/output/status.json"
exit 7
''')
            output, reports = io.StringIO(), []
            with patch.dict(os.environ, {'GH_TOKEN': 'secret', 'GITHUB_TOKEN': 'secret',
                                        'TWRP_SOURCE_TOKEN': 'secret', 'ACTIONS_RUNTIME_TOKEN': 'secret'}):
                with contextlib.redirect_stdout(output):
                    status = run_build(builder, work, checkpoint=lambda: reports.append(True), interval=0.01)
            self.assertEqual(status, 7)
            self.assertTrue(reports)
            self.assertNotIn('private fixture', output.getvalue())
            self.assertIn('private fixture', (work / 'logs/native.log').read_text())
            self.assertEqual((work / 'logs/native.log').stat().st_mode & 0o777, 0o600)

    def test_existing_log_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / 'logs').mkdir()
            (work / 'logs/native.log').write_text('keep')
            with self.assertRaises(FileExistsError):
                run_build(work, work)
            self.assertEqual((work / 'logs/native.log').read_text(), 'keep')

    def test_cancellation_terminates_the_build_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            builder, work = root / 'builder', root / 'work'
            (builder / 'scripts').mkdir(parents=True)
            work.mkdir()
            (builder / 'scripts/build.sh').write_text('''#!/usr/bin/env bash
printf '%s' "$$" > "${BUILD_ROOT}/child.pid"
trap 'exit 143' TERM
sleep 60 &
wait
''')
            program = '''import sys
from run_native import Interrupted, run_build
try:
    sys.exit(run_build(sys.argv[1], sys.argv[2], interval=0.01))
except Interrupted as error:
    sys.exit(error.status)
'''
            environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'scripts'))
            process = subprocess.Popen([sys.executable, '-c', program, str(builder), str(work)],
                                       env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 5
                while not (work / 'child.pid').exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue((work / 'child.pid').exists())
                child = int((work / 'child.pid').read_text())
                process.send_signal(signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 143, stderr.decode())
                with self.assertRaises(ProcessLookupError):
                    os.kill(child, 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)
