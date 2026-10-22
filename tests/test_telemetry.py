# Requirements: synthetic logs and local fixtures; no private source or network.
# Ambiguity: numeric progress does not prove build completion or device behavior.
# Research: reject arbitrary text, counters, booleans and nonfinite values.
# Optimization: bounded fixtures and short real subprocess heartbeat tests.
# Risks: leaking log excerpts or allowing reporting failures to change build status.
# Validation: privacy, stage clocks, bounded parsing, final records and live output.
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_telemetry import (memory_mib, progress_counts, sample, sanitize_metrics,
                             set_stage)
from report_progress import record, render_summary
from run_native import run_build
import report_progress


class TelemetryTests(unittest.TestCase):
    def test_repo_cr_ansi_progress_returns_only_numeric_metadata(self):
        text = ('secret credential\r\x1b[32mFetching: 25% (1/4) private-url\x1b[0m'
                '\rChecking out: 75% (3/4) private-source')
        value = progress_counts(text, 'source_sync')
        self.assertEqual(value, {'kind': 'checkout', 'completed': 3, 'total': 4, 'percent': 75.0})
        self.assertNotIn('private', json.dumps(value))
        self.assertNotIn('secret', json.dumps(value))

    def test_ninja_progress_is_latest_batch_and_does_not_return_command(self):
        value = progress_counts('[100% 4/4] secret-command\n[  1% 2/200] private-file', 'compile')
        self.assertEqual(value, {'kind': 'ninja', 'completed': 2, 'total': 200, 'percent': 1.0})
        self.assertIsNone(progress_counts('arbitrary secret text 3/4', 'compile'))

    def test_invalid_progress_counters_and_kinds_are_omitted(self):
        for value in [
            {'kind': 'ninja', 'completed': 5, 'total': 4},
            {'kind': 'ninja', 'completed': 0, 'total': 0},
            {'kind': 'fetch', 'completed': 1, 'total': 10001},
            {'kind': 'secret', 'completed': 1, 'total': 4},
            {'kind': [], 'completed': 1, 'total': 4},
            {'kind': 'ninja', 'completed': True, 'total': 4},
        ]:
            with self.subTest(value=value):
                self.assertNotIn('progress', sanitize_metrics({'progress': value}))

    def test_unknown_secret_and_nonfinite_metric_values_are_dropped(self):
        value = sanitize_metrics({'secret': 'credential', 'elapsed_seconds': 8,
                                  'disk_free_mib': 'private', 'load_1m': float('nan'),
                                  'log_bytes': 10**1000, 'swap_free_mib': True,
                                  'stage_seconds': {'compile': 7.5, 'private-path': 8}})
        self.assertEqual(value, {'elapsed_seconds': 8, 'stage_seconds': {'compile': 7.5}})

    def test_phase_clock_records_actual_transitions_and_final_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            (work / 'output').mkdir()
            set_stage(work, 'source_sync', now=100)
            set_stage(work, 'compile', now=125)
            set_stage(work, 'compile', exit_code=7, now=140)
            self.assertEqual(json.loads((work / 'output/stage-timings.json').read_text()),
                             {'source_sync': 25, 'compile': 15})
            self.assertEqual(json.loads((work / 'output/status.json').read_text())['exit_code'], 7)
            self.assertEqual((work / 'output/status.json').stat().st_mode & 0o777, 0o600)

    def test_sample_reads_only_bounded_tail_and_does_not_echo_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            (work / 'output').mkdir()
            (work / 'logs').mkdir()
            set_stage(work, 'compile', now=100)
            (work / 'logs/compile.log').write_text('private secret\n' * 40000 + '[20% 2/10] private-command\n')
            stage, value = sample(work, 95, now=110)
            self.assertEqual(stage, 'compile')
            self.assertEqual(value['progress']['completed'], 2)
            self.assertEqual(value['stage_elapsed_seconds'], 10)
            self.assertNotIn('private', json.dumps(value))
            self.assertGreater(value['log_bytes'], 256 * 1024)

    def test_sample_ignores_symlinked_log_and_malformed_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            (work / 'output').mkdir()
            (work / 'logs').mkdir()
            (work / 'output/status.json').write_text('{"stage": ["private"]}')
            outside = work / 'secret'
            outside.write_text('secret')
            (work / 'logs/native.log').symlink_to(outside)
            stage, value = sample(work, 1, now=2)
            self.assertEqual(stage, 'initialization')
            self.assertNotIn('log_bytes', value)

    def test_memory_parser_never_exports_unknown_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'meminfo'
            path.write_text('MemAvailable: 4096 kB\nSwapFree: 1024 kB\nToken: secret\n')
            self.assertEqual(memory_mib(path), {'memory_available_mib': 4, 'swap_free_mib': 1})

    def test_safe_metrics_and_source_categories_reach_task_summary(self):
        value = record({'stage': 'compile', 'exit_code': 1}, 42, 'a' * 40,
                       metrics={'elapsed_seconds': 6, 'secret': 'never-display',
                                'stage_seconds': {'compile': 4}},
                       source_summary={'categories': ['NETWORK_FAILURE', 'never-display'],
                                       'http_statuses': ['503', 'secret'], 'raw': 'never-display'})
        summary = render_summary(value)
        self.assertIn('compile | 4', summary)
        self.assertIn('NETWORK_FAILURE', summary)
        self.assertIn('503', summary)
        self.assertNotIn('never-display', summary)
        self.assertNotIn('never-display', json.dumps(value))

    def test_real_child_emits_heartbeats_without_leaking_private_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            builder, work = root / 'builder', root / 'work'
            (builder / 'scripts').mkdir(parents=True)
            work.mkdir()
            (builder / 'scripts/build.sh').write_text('''#!/usr/bin/env bash
printf '{"stage":"compile"}' > "${BUILD_ROOT}/output/status.json"
printf '[25%% 1/4] private compiler command with secret\\n' > "${BUILD_ROOT}/logs/compile.log"
sleep 0.15
exit 7
''')
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = run_build(builder, work, interval=0.01, heartbeat=0.03)
            records = [json.loads(line.removeprefix('BUILD_METRICS '))
                       for line in stdout.getvalue().splitlines() if line.startswith('BUILD_METRICS ')]
            self.assertGreaterEqual(len(records), 2)
            self.assertTrue(any(row.get('progress', {}).get('completed') == 1 for row in records))
            self.assertEqual(status, 7)
            self.assertNotIn('private compiler', stdout.getvalue())
            self.assertNotIn('secret', stdout.getvalue())

    def test_telemetry_io_failure_does_not_replace_child_exit_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            builder, work = root / 'builder', root / 'work'
            (builder / 'scripts').mkdir(parents=True)
            work.mkdir()
            (builder / 'scripts/build.sh').write_text('exit 7\n')
            with patch('run_native.sample', side_effect=OSError('secret internal message')):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(run_build(builder, work, interval=0.01), 7)
            self.assertNotIn('secret internal message', output.getvalue())

    def test_console_and_summary_survive_progress_api_unavailability(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'output').mkdir()
            (root / 'output/status.json').write_text('{"stage":"compile","exit_code":7}')
            (root / 'output/telemetry.json').write_text(
                '{"elapsed_seconds":9,"secret":"never-display","stage_seconds":{"compile":8}}')
            summary = root / 'summary.md'
            environment = {'GITHUB_RUN_ID': '42', 'GITHUB_SHA': 'a' * 40,
                           'GITHUB_REPOSITORY': 'synthetic/repository',
                           'GH_TOKEN': 'private-token', 'GITHUB_STEP_SUMMARY': str(summary)}
            output = io.StringIO()
            with patch.dict(os.environ, environment), \
                    patch.object(sys, 'argv', ['report_progress.py', '--work', str(root)]), \
                    patch('report_progress.Client', side_effect=OSError('private API response')):
                with contextlib.redirect_stdout(output), self.assertRaises(OSError):
                    report_progress.main()
            self.assertIn('BUILD_DIAGNOSTICS', output.getvalue())
            self.assertIn('compile | 8', summary.read_text())
            for text in (output.getvalue(), summary.read_text()):
                self.assertNotIn('private-token', text)
                self.assertNotIn('private API response', text)
                self.assertNotIn('never-display', text)
