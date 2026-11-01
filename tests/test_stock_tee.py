# Requirements: Native stock-client copy and actual workflow change classification.
# Ambiguity: host fixtures cannot prove a device boot or FBE operation.
# Research: replacing the client must follow overlays and reach final image checks.
# Optimization: execute only the affected Shell fragments with public fixtures.
# Risks: stale same-sized client, ignored copy failure or missed binary-only push.
# Validation: enabled/default/missing inputs and Native-only path classification.
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLIENT = 'public-prebuilts/selene-stock-v14/libTEECommon.so'
TARGET = 'device/xiaomi/selene/recovery/root/vendor/lib64/libTEECommon.so'


class StockTeeTests(unittest.TestCase):
    def run_copy(self, enabled=None, missing=False):
        source = (ROOT / 'scripts/build.sh').read_text()
        fragment = 'tee_common_args=()\n' + source.split('tee_common_args=()\n', 1)[1].split(
            'set_stage public_resources\n', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            builder = root / 'builder input'
            client = builder / CLIENT
            client.parent.mkdir(parents=True)
            if not missing:
                client.write_bytes((ROOT / CLIENT).read_bytes())
            target = root / TARGET
            target.parent.mkdir(parents=True)
            target.write_bytes(b'old overlay client')
            environment = {'PATH': os.defpath, 'SELF': str(builder)}
            if enabled is not None:
                environment['SELENE_STOCK_TEE_CLIENT'] = enabled
            program = ('set -euo pipefail\ntrace_public_command() { :; }\n' + fragment
                       + 'for arg in "${tee_common_args[@]}"; do printf "%s\\0" "$arg"; done\n')
            result = subprocess.run(['bash', '-c', program], cwd=root, env=environment,
                                    capture_output=True, timeout=10)
            args = result.stdout.split(b'\0')[:-1]
            return result.returncode, target.read_bytes(), args, target.stat().st_mode & 0o777

    def test_native_copy_replaces_overlay_and_passes_reference_to_verifier(self):
        status, payload, args, mode = self.run_copy('1')
        self.assertEqual(status, 0)
        self.assertEqual(payload, (ROOT / CLIENT).read_bytes())
        self.assertEqual(mode, 0o644)
        self.assertEqual(args[0], b'--tee-common')
        self.assertTrue(args[1].endswith(CLIENT.encode()))
        source = (ROOT / 'scripts/build.sh').read_text()
        self.assertLess(source.index('trace_public_command overlay_copy\n'),
                        source.index('tee_common_args=()\n'))
        verifier = source.split('trace_public_command boot_static_verify\n', 1)[1].split(
            'trace_public_command boot_copy\n', 1)[0]
        self.assertIn('"${tee_common_args[@]}"', verifier)

    def test_default_and_disabled_routes_keep_existing_client(self):
        for enabled in (None, '0'):
            with self.subTest(enabled=enabled):
                status, payload, args, _ = self.run_copy(enabled)
                self.assertEqual(status, 0)
                self.assertEqual(payload, b'old overlay client')
                self.assertEqual(args, [])

    def test_missing_public_client_fails_before_build(self):
        status, payload, args, _ = self.run_copy('1', missing=True)
        self.assertNotEqual(status, 0)
        self.assertEqual(payload, b'old overlay client')
        self.assertEqual(args, [])

    def test_actual_native_classifier_includes_binary_but_not_its_documentation(self):
        source = (ROOT / '.github/workflows/twrp_native.yml').read_text()
        fragment = source.split('        id: native-changes\n', 1)[1].split(
            '        run: |\n', 1)[1].split('      - name:', 1)[0]
        fragment = textwrap.dedent(fragment)
        triggers = source.split('  workflow_dispatch:\n', 1)[0]
        self.assertEqual(triggers.count("- '" + CLIENT + "'"), 2)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'git').write_text(
                '#!/bin/bash\ncase "$1" in\n'
                '  fetch) exit 0 ;;\n'
                '  diff) cat "$FIXTURE_DIFF" ;;\n'
                '  *) exit 99 ;;\nesac\n')
            (root / 'git').chmod(0o755)
            paths = root / 'paths'
            output = root / 'output'
            environment = {'PATH': str(root) + ':' + os.defpath,
                           'BEFORE_SHA': 'a' * 40, 'GITHUB_SHA': 'b' * 40,
                           'GITHUB_OUTPUT': str(output), 'RUNNER_TEMP': str(root),
                           'FIXTURE_DIFF': str(paths)}
            cases = [([CLIENT], True),
                     (['public-prebuilts/selene-stock-v14/README.md'], False),
                     (['tests/test_stock_tee.py'], False),
                     (['scripts/stock_rom.py'], False),
                     (['scripts/run_native.py'], True)]
            for changed, required in cases:
                with self.subTest(changed=changed):
                    paths.write_bytes(b''.join(path.encode() + b'\0' for path in changed))
                    output.write_text('')
                    result = subprocess.run(['bash', '-c', fragment], env=environment,
                                            capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr.decode())
                    self.assertEqual(output.read_text(),
                                     f'build_required={str(required).lower()}\n')


if __name__ == '__main__':
    unittest.main()
