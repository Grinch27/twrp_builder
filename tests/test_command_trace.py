# Requirements: expose reviewed public build command templates without leaking private parameters.
# Ambiguity: events are shell-entry markers, not individual command exit statuses.
# Research: never parse arbitrary compiler output or private manifest contents.
# Optimization: bounded, append-only event scan during existing telemetry polls.
# Risks: public log disclosure, symlinks, tampering and malformed bytes.
# Validation: approved IDs only, strict timestamps, private text isolation, real child exit.
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_native import PUBLIC_COMMANDS, run_build, safe_command_events


class CommandTraceTests(unittest.TestCase):
    def test_public_trace_drops_private_text_and_only_emits_reviewed_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events'
            path.write_bytes(
                b'2026-10-26T02:00:01Z repo_sync\\n'
                b'2026-10-26T02:00:02Z GH_TOKEN=SECRET_PRIVATE_SOURCE\\n'
                b'2026-10-26T02:00:03Z bootimage_compile\\n'
                b'not-a-date cms_seal\\n')
            values, offset = safe_command_events(path)
            self.assertEqual([event[1] for event in values],
                             ['repo_sync', 'bootimage_compile'])
            self.assertEqual(offset, 4)
            self.assertNotIn('SECRET_PRIVATE_SOURCE', str(values))
            self.assertIn('mka bootimage -j4', str(values))
            self.assertEqual(safe_command_events(path, offset), ([], offset))

    def test_trace_rejects_symlinks_and_oversized_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / 'private'
            outside.write_text('2026-10-26T02:00:00Z cms_seal\\n')
            linked = root / 'events'
            linked.symlink_to(outside)
            self.assertEqual(safe_command_events(linked), ([], 0))
            linked.unlink()
            linked.write_bytes(b'x' * 9000)
            self.assertEqual(safe_command_events(linked), ([], 0))

    def test_native_child_reports_only_approved_commands_and_real_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            builder, work = root / 'builder', root / 'work'
            (builder / 'scripts').mkdir(parents=True)
            work.mkdir()
            (builder / 'scripts/build.sh').write_text(
                '#!/usr/bin/env bash\\n'
                'printf "2026-10-26T02:00:01Z repo_sync\\\\n" > "${BUILD_ROOT}/output/command-trace.log"\\n'
                'printf "2026-10-26T02:00:02Z SECRET_PRIVATE_SOURCE\\\\n" >> "${BUILD_ROOT}/output/command-trace.log"\\n'
                'echo SECRET_PRIVATE_SOURCE\\nexit 7\\n')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = run_build(builder, work, interval=0.01)
            self.assertEqual(code, 7)
            self.assertIn('BUILD_COMMAND', output.getvalue())
            self.assertIn(PUBLIC_COMMANDS['repo_sync'], output.getvalue())
            self.assertNotIn('SECRET_PRIVATE_SOURCE', output.getvalue())
            self.assertIn('SECRET_PRIVATE_SOURCE', (work / 'logs/native.log').read_text())


if __name__ == '__main__':
    unittest.main()
