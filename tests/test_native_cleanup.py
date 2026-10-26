# Requirements: exercise only isolated test sessions and synthetic proc records.
# Ambiguity: local tests cannot bound GitHub's built-in Complete job phase.
# Research: a dead shell does not imply its process-group children have exited.
# Optimization: short TERM grace and fixed local fixtures, no network or Android.
# Risks: unrelated process termination, PID reuse, symlinked records and hangs.
# Validation: real stubborn children, stale identities, refusal and finite budgets.
from pathlib import Path
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_cleanup import cleanup_group, cleanup_work, live_members, process_info, remember_group
from run_native import stop_group


class NativeCleanupTests(unittest.TestCase):
    def test_stop_group_kills_child_even_when_leader_exits_on_term(self):
        with tempfile.TemporaryDirectory() as temporary:
            ready = Path(temporary) / 'ready'
            program = ('import os,signal,sys,time\n'
                       'pid=os.fork()\n'
                       'if pid == 0:\n'
                       ' signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
                       ' open(sys.argv[1],"w").write(str(os.getpid()))\n'
                       ' while True: time.sleep(1)\n'
                       'signal.signal(signal.SIGTERM,lambda *args: sys.exit(0))\n'
                       'while True: time.sleep(1)\n')
            process = subprocess.Popen([sys.executable, '-c', program, str(ready)],
                                       start_new_session=True)
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(ready.exists())
                child = int(ready.read_text())
                if process_info(child) is None:
                    self.skipTest('executor proc namespace does not expose the real child PID')
                stop_group(process)
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    info = process_info(child)
                    if info is None or info['state'] in {'Z', 'X'}:
                        break
                    time.sleep(0.01)
                else:
                    self.fail('TERM-resistant child survived group cleanup')
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)

    def test_recorded_real_session_cleanup_and_stale_pid_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'output').mkdir()
            process = subprocess.Popen([sys.executable, '-c',
                                        'import time; time.sleep(30)'], start_new_session=True)
            try:
                if process_info(process.pid) is None:
                    self.skipTest('executor proc namespace does not expose the real child PID')
                remember_group(root, process.pid)
                info = process_info(process.pid)
                self.assertEqual((root / 'output/native-session.json').stat().st_mode & 0o777, 0o600)
                with self.assertRaises(ValueError):
                    cleanup_group(process.pid, info['start'] + 1, timeout=0.1)
                self.assertIsNone(process.poll())
                self.assertTrue(cleanup_work(root))
                process.wait(timeout=5)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)

    def test_dead_leader_still_receives_group_kill_for_living_descendants(self):
        from unittest.mock import Mock
        process = Mock(pid=123456)
        process.wait.return_value = 0
        with patch('run_native.os.killpg') as kill:
            stop_group(process)
        self.assertEqual([call.args for call in kill.call_args_list],
                         [(123456, signal.SIGTERM), (123456, signal.SIGKILL)])

    def test_unresponsive_members_exhaust_budget_without_unbounded_wait(self):
        started = time.monotonic()
        with patch('native_cleanup.live_members', return_value=[123456]), \
                patch('native_cleanup.os.killpg') as kill:
            self.assertFalse(cleanup_group(123456, 1, timeout=0.05, grace=0))
        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual([call.args[1] for call in kill.call_args_list],
                         [signal.SIGTERM, signal.SIGKILL])
        with self.assertRaises(ValueError):
            cleanup_group(os.getpgrp(), 1, timeout=0)

    def test_missing_record_and_symlink_cannot_target_external_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'output').mkdir()
            self.assertTrue(cleanup_work(root))
            target = root / 'outside'
            target.write_text('{"group":123456,"start":1}')
            (root / 'output/native-session.json').symlink_to(target)
            with patch('native_cleanup.os.killpg') as kill:
                with self.assertRaises(OSError):
                    cleanup_work(root)
                kill.assert_not_called()
