# Requirements: test interrupted stock downloads and safe cross-run checkpoints.
# Ambiguity: local fixtures do not establish success of GitHub dispatch or uploads.
# Research: aria2 INT/exit 7, sparse PAX archives and artifact run provenance.
# Optimization: tiny local data; optional real aria2 uses loopback HTTP only.
# Risks: stale/mixed state, unsafe paths, masked exits and unbounded continuation.
# Validation: restore bytes/holes, exact failure codes and missing/foreign artifacts.
"""Tests for bounded stock-ROM relay, with no device or external ROM transfer."""

import http.server
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    'stock_rom_relay', Path(__file__).resolve().parents[1] / 'scripts/stock_rom_relay.py')
relay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(relay)


class RelayTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {
            'ROM_WORK': str(self.root), 'ROM_URL': 'https://example.test/fixed.tgz',
            'ROM_VERSION': 'fixed', 'GITHUB_RUN_ID': '100', 'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_OUTPUT': str(self.root / 'outputs'),
            'RELAY_SECONDS': '300', 'RELAY_JOB_STARTED': str(time.time()),
            'MAX_RELAY_ROUNDS': '12', 'RESUME_RUN_ID': '',
            'RESUME_ARTIFACT_ID': '', 'RELAY_CHAIN': '',
        }

    def metadata(self, state='paused'):
        data_name = 'rom.tgz' if state == 'complete' else relay.PARTIAL
        return {
            'schema': 1, 'state': state, 'url': self.env['ROM_URL'],
            'rom_version': 'fixed', 'chain': '100', 'round': 1,
            'run_id': '100', 'run_attempt': '1',
            'apparent_bytes': (self.root / data_name).stat().st_size,
        }

    def resume_env(self):
        return dict(self.env, GITHUB_RUN_ID='101', RESUME_RUN_ID='100',
                    RESUME_ARTIFACT_ID='200', RELAY_CHAIN='100')

    def fixture(self, state='paused'):
        data_name = 'rom.tgz' if state == 'complete' else relay.PARTIAL
        with (self.root / data_name).open('wb') as target:
            target.write(b'first')
            target.seek(32 * 1024 ** 2)
            target.write(b'last')
        if state == 'paused':
            (self.root / relay.CONTROL).write_bytes(b'saved piece map')
        (self.root / 'aria2-download.log').write_text('never package this log')
        return relay.pack(self.root, self.metadata(state))

    def test_sparse_checkpoint_round_trip_preserves_bytes_holes_and_control(self):
        archive = self.fixture()
        self.assertLess(archive.stat().st_size, 65536)
        with tarfile.open(archive) as source:
            self.assertEqual(set(source.getnames()), {relay.MANIFEST, relay.PARTIAL, relay.CONTROL})
        destination = self.root / 'restored'
        destination.mkdir()
        saved = relay.restore(archive, destination, self.resume_env(), 'paused')
        data = destination / relay.PARTIAL
        self.assertEqual(saved['chain'], '100')
        self.assertLess(data.stat().st_blocks * 512, 65536)
        self.assertEqual(data.read_bytes(), (self.root / relay.PARTIAL).read_bytes())
        self.assertEqual((destination / relay.CONTROL).read_bytes(), b'saved piece map')
        self.assertFalse(archive.exists())

    def test_incomplete_checkpoint_cannot_be_used_for_extraction(self):
        archive = self.fixture()
        destination = self.root / 'restored'
        destination.mkdir()
        with self.assertRaises(ValueError):
            relay.restore(archive, destination, self.resume_env(), 'complete')
        self.assertEqual(list(destination.iterdir()), [])

    def test_completed_archive_is_accepted_without_control_file(self):
        archive = self.fixture('complete')
        destination = self.root / 'restored'
        destination.mkdir()
        relay.restore(archive, destination, self.resume_env(), 'complete')
        self.assertEqual((destination / 'rom.tgz').read_bytes(), (self.root / 'rom.tgz').read_bytes())

    def test_wrong_source_url_or_chain_is_rejected_before_writes(self):
        archive = self.fixture()
        for key, value in (('ROM_URL', 'https://example.test/other.tgz'),
                           ('RELAY_CHAIN', '999'), ('RESUME_RUN_ID', '999')):
            destination = self.root / key
            destination.mkdir()
            with self.subTest(key=key), self.assertRaises(ValueError):
                relay.restore(archive, destination, dict(self.resume_env(), **{key: value}), 'paused')
            self.assertEqual(list(destination.iterdir()), [])

    def test_checkpoint_links_paths_duplicates_and_missing_files_are_rejected(self):
        for kind in ('link', 'path', 'duplicate', 'missing'):
            archive = self.root / f'{kind}.tar'
            with tarfile.open(archive, 'w') as target:
                if kind == 'link':
                    member = tarfile.TarInfo(relay.PARTIAL)
                    member.type = tarfile.SYMTYPE
                    member.linkname = '/etc/passwd'
                    target.addfile(member)
                elif kind == 'missing':
                    pass
                else:
                    for _ in range(2 if kind == 'duplicate' else 1):
                        member = tarfile.TarInfo(relay.PARTIAL if kind == 'duplicate' else '../outside')
                        member.size = 1
                        target.addfile(member, io.BytesIO(b'x'))
            destination = self.root / kind
            destination.mkdir()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                relay.restore(archive, destination, self.resume_env(), 'paused')
            self.assertEqual(list(destination.iterdir()), [])

    @mock.patch.object(relay.shutil, 'disk_usage', return_value=mock.Mock(free=20 * relay.RESERVE))
    def test_input_pair_and_provenance_reject_fork_or_wrong_artifact(self, disk_usage):
        with self.assertRaises(ValueError):
            relay.validate_inputs(dict(self.env, RESUME_RUN_ID='100'))
        run = {'id': 100, 'head_branch': 'main', 'event': 'push', 'run_attempt': 1,
               'path': '.github/workflows/stock_rom.yml',
               'head_repository': {'full_name': 'owner/repo'}}
        artifact = {'expired': False, 'name': 'stock-rom-relay-100-1', 'workflow_run': {'id': 100}}
        with mock.patch.object(relay, 'github_json', side_effect=[run, artifact]):
            relay.prepare(self.resume_env())
        with mock.patch.object(relay, 'github_json', return_value=dict(run, event='pull_request')):
            with self.assertRaises(ValueError):
                relay.prepare(self.resume_env())
        with mock.patch.object(relay, 'github_json', side_effect=[run, dict(artifact, expired=True)]):
            with self.assertRaises(ValueError):
                relay.prepare(self.resume_env())

    def test_real_download_space_gate_rejects_low_capacity(self):
        with mock.patch.object(relay.shutil, 'disk_usage', return_value=mock.Mock(free=8 * relay.RESERVE)), \
                mock.patch.object(relay, 'github_json') as github:
            with self.assertRaisesRegex(ValueError, '12 GiB'):
                relay.prepare(self.env)
        github.assert_not_called()

    def test_deadline_sends_int_and_waits_for_clean_exit(self):
        process = mock.MagicMock()
        process.__enter__.return_value = process
        process.wait.side_effect = [subprocess.TimeoutExpired('aria2c', 3), 7]
        with mock.patch.object(relay.subprocess, 'Popen', return_value=process):
            self.assertEqual(relay.wait_download(['aria2c'], 3), (7, True))
        process.send_signal.assert_called_once_with(relay.signal.SIGINT)
        process.kill.assert_not_called()

    def test_unclean_shutdown_fails_without_checkpoint_success(self):
        process = mock.MagicMock()
        process.__enter__.return_value = process
        process.wait.side_effect = [subprocess.TimeoutExpired('aria2c', 3),
                                    subprocess.TimeoutExpired('aria2c', 60), -9]
        with mock.patch.object(relay.subprocess, 'Popen', return_value=process):
            with self.assertRaisesRegex(RuntimeError, 'did not stop cleanly'):
                relay.wait_download(['aria2c'], 3)
        process.kill.assert_called_once()

    def test_real_failure_exit_is_preserved_and_no_checkpoint_is_emitted(self):
        with mock.patch.object(relay, 'wait_download', return_value=(6, False)):
            self.assertEqual(relay.download(self.env), 6)
        self.assertFalse((self.root / relay.CHECKPOINT).exists())
        self.assertFalse((self.root / 'rom.tgz').exists())

    def test_release_restore_skips_aria2_and_hands_off_complete_archive(self):
        (self.root / 'rom.tgz').write_bytes(b'saved original ROM')
        with mock.patch.object(relay, 'wait_download') as download:
            self.assertEqual(relay.download(dict(self.env, ROM_RELEASE_TAG='saved-release')), 0)
        download.assert_not_called()
        self.assertIn('state=complete', (self.root / 'outputs').read_text())

    def test_release_source_and_partial_checkpoint_cannot_be_mixed(self):
        with self.assertRaisesRegex(ValueError, 'not both'):
            relay.validate_inputs(dict(self.resume_env(), ROM_RELEASE_TAG='saved-release'))

    def test_metadata_or_summary_display_failure_preserves_download_exit(self):
        with mock.patch.object(relay, 'wait_download', return_value=(6, False)), \
                mock.patch.object(Path, 'stat', side_effect=OSError('unavailable')), \
                mock.patch.dict(os.environ, GITHUB_STEP_SUMMARY=str(self.root)):
            self.assertEqual(relay.download(self.env), 6)

    def test_missing_output_and_nonplanned_interrupt_are_not_success(self):
        with mock.patch.object(relay, 'wait_download', return_value=(0, False)):
            with self.assertRaises(ValueError):
                relay.download(self.env)
        with mock.patch.object(relay, 'wait_download', return_value=(7, False)):
            self.assertEqual(relay.download(self.env), 7)
        self.assertFalse((self.root / relay.CHECKPOINT).exists())

    def test_full_checkpoint_restore_continue_and_complete_flow(self):
        def pause(command, seconds):
            (self.root / relay.PARTIAL).write_bytes(b'already downloaded')
            (self.root / relay.CONTROL).write_bytes(b'piece map')
            return 7, True

        with mock.patch.object(relay, 'wait_download', side_effect=pause):
            self.assertEqual(relay.download(self.env), 0)
        self.assertIn('state=paused', (self.root / 'outputs').read_text())
        next_work = self.root / 'next'
        (next_work / 'incoming').mkdir(parents=True)
        shutil.move(self.root / relay.CHECKPOINT, next_work / 'incoming' / relay.CHECKPOINT)
        resumed = dict(self.resume_env(), ROM_WORK=str(next_work),
                       GITHUB_OUTPUT=str(next_work / 'outputs'))

        def complete(command, seconds):
            self.assertEqual((next_work / relay.PARTIAL).read_bytes(), b'already downloaded')
            self.assertEqual((next_work / relay.CONTROL).read_bytes(), b'piece map')
            (next_work / relay.PARTIAL).write_bytes(b'already downloaded plus rest')
            (next_work / relay.CONTROL).unlink()
            return 0, False

        with mock.patch.object(relay, 'wait_download', side_effect=complete):
            self.assertEqual(relay.download(resumed), 0)
        self.assertIn('state=complete', (next_work / 'outputs').read_text())
        self.assertIn('round=2', (next_work / 'outputs').read_text())

    def test_unchanged_progress_keeps_checkpoint_but_stops_automatic_chain(self):
        archive = self.fixture()
        next_work = self.root / 'next'
        (next_work / 'incoming').mkdir(parents=True)
        shutil.move(archive, next_work / 'incoming' / relay.CHECKPOINT)
        resumed = dict(self.resume_env(), ROM_WORK=str(next_work),
                       GITHUB_OUTPUT=str(next_work / 'outputs'))
        with mock.patch.object(relay, 'wait_download', return_value=(7, True)):
            self.assertEqual(relay.download(resumed), 0)
        self.assertTrue((next_work / relay.CHECKPOINT).is_file())
        self.assertIn('can_continue=false', (next_work / 'outputs').read_text())

    def test_round_limit_keeps_the_last_checkpoint(self):
        def pause(command, seconds):
            (self.root / relay.PARTIAL).write_bytes(b'progress')
            (self.root / relay.CONTROL).write_bytes(b'new map')
            return 7, True

        with mock.patch.object(relay, 'wait_download', side_effect=pause):
            self.assertEqual(relay.download(dict(self.env, MAX_RELAY_ROUNDS='1')), 0)
        self.assertTrue((self.root / relay.CHECKPOINT).is_file())
        self.assertIn('can_continue=false', (self.root / 'outputs').read_text())

    @unittest.skipUnless(shutil.which('aria2c'), 'aria2 binary is not available locally')
    def test_real_aria2_range_resume_across_checkpoint(self):
        data = os.urandom(4 * 1024 ** 2)
        ranges = []

        class Handler(http.server.BaseHTTPRequestHandler):

            def do_GET(self):
                header = self.headers.get('Range')
                start, end = 0, len(data) - 1
                if header:
                    start_text, end_text = header.removeprefix('bytes=').split('-')
                    start = int(start_text)
                    end = int(end_text) if end_text else end
                    ranges.append(start)
                self.send_response(206 if header else 200)
                self.send_header('Content-Length', str(end - start + 1))
                self.send_header('Accept-Ranges', 'bytes')
                if header:
                    self.send_header('Content-Range', f'bytes {start}-{end}/{len(data)}')
                self.end_headers()
                try:
                    self.wfile.write(data[start:end + 1])
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_port}/fixture'
        command = relay.aria2_args(self.root, url)
        command.insert(-1, '--max-overall-download-limit=256K')
        code, stopped = relay.wait_download(command, 2)
        self.assertEqual((code, stopped), (7, True))
        self.assertTrue((self.root / relay.CONTROL).is_file())
        env = dict(self.env, ROM_URL=url)
        meta = dict(self.metadata(), url=url)
        archive = relay.pack(self.root, meta)
        destination = self.root / 'restored'
        destination.mkdir()
        relay.restore(archive, destination, dict(env, **{
            'RESUME_RUN_ID': '100', 'RELAY_CHAIN': '100'}), 'paused')
        ranges.clear()
        self.assertEqual(relay.wait_download(relay.aria2_args(destination, url), 20), (0, False))
        self.assertFalse((destination / relay.CONTROL).exists())
        self.assertTrue(any(offset > 0 for offset in ranges))
        self.assertEqual((destination / relay.PARTIAL).read_bytes(), data)


if __name__ == '__main__':
    unittest.main()
