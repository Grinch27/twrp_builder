# Requirements: verify native credential separation and actual child failure status.
# Ambiguity: fixture execution does not prove an Android build or host isolation.
# Research: exercise a real subprocess with a private log and no network access.
# Optimization: minimal temporary builder and short status polling.
# Risks: accidental token inheritance or publishing raw compiler diagnostics.
# Validation: allowlist, preserved HOME, exit propagation and exclusive logs.
import contextlib
import io
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_native import build_environment, run_build


class NativeTests(unittest.TestCase):
    def test_child_environment_omits_all_ci_and_unrelated_values(self):
        parent = {'PATH': '/usr/bin:/bin', 'HOME': '/unchanged', 'LANG': 'C.UTF-8',
                  'GH_TOKEN': 'secret', 'GITHUB_TOKEN': 'secret', 'TWRP_SOURCE_TOKEN': 'secret',
                  'ACTIONS_RUNTIME_TOKEN': 'secret', 'GITHUB_ENV': '/private',
                  'UNRELATED_SECRET': 'secret', 'JAVA_HOME': '/host-java', 'LD_PRELOAD': '/private'}
        result = build_environment(parent, Path('/builder'), Path('/work'))
        self.assertEqual(result, {'PATH': '/usr/bin:/bin', 'HOME': '/unchanged', 'LANG': 'C.UTF-8',
                                 'BUILDER_SELF': '/builder', 'BUILD_ROOT': '/work',
                                 'GIT_TERMINAL_PROMPT': '0'})

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
