# Requirements: exercise official-ROM extraction with tiny synthetic tarballs only.
# Ambiguity: the real package layout is deliberately not represented as verified.
# Research: archive path/link boundaries, part naming and fail-closed extraction.
# Optimization: small data and an injected part size avoid real ROM transfers.
# Risks: overwrites, omitted payloads, mixed helper files and truncated archives.
# Validation: exact synthetic bytes, manifest coverage and no executable invocation.
"""Tests for stock payload extraction, without device, network or credentials."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    'stock_rom', Path(__file__).resolve().parents[1] / 'scripts/stock_rom.py')
stock_rom = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stock_rom)


class StockRomTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, entries):
        path = self.root / 'rom.tgz'
        with tarfile.open(path, 'w:gz') as target:
            for name, data in entries:
                if isinstance(name, tarfile.TarInfo):
                    target.addfile(name, io.BytesIO(data) if data else None)
                else:
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    target.addfile(info, io.BytesIO(data))
        return path

    def extract(self, entries, **kwargs):
        path = self.archive(entries)
        with contextlib.redirect_stdout(io.StringIO()):
            return stock_rom.extract_rom(path, self.root / 'output', **kwargs)

    def test_images_bin_and_companion_files_are_complete_and_scripts_ignored(self):
        payloads = {
            'boot.img': b'boot', 'preloader.bin': b'loader',
            'super.img': b'0123456789', 'scatter.txt': b'map',
            'misc.partial': b'kept',
        }
        entries = [(f'./rom/images/{name}', data) for name, data in payloads.items()]
        entries += [('rom/flash_all.sh', b'exit 99'),
                    ('rom/images/helper.bat', b'not an image')]
        manifest = self.extract(entries, part_bytes=4)
        self.assertEqual(set(payloads), {p['name'] for p in manifest['payloads']})
        assets = self.root / 'output/assets'
        for payload in manifest['payloads']:
            actual = b''.join((assets / a['name']).read_bytes() for a in payload['assets'])
            self.assertEqual(actual, payloads[payload['name']])
            for part in payload['assets']:
                self.assertEqual((assets / part['name']).stat().st_size, part['bytes'])
        self.assertFalse((assets / 'helper.bat').exists())
        self.assertFalse((assets / 'flash_all.sh').exists())
        self.assertFalse(manifest['is_device_backup'])
        self.assertEqual(manifest['device_slot_correspondence'], 'NOT_VERIFIED')
        saved = json.loads((assets / 'stock-rom-manifest.json').read_text())
        self.assertEqual(manifest, saved)
        self.assertIn('super.img.part0001 super.img.part0002 super.img.part0003',
                      (self.root / 'output/release-notes.md').read_text())
        self.assertEqual(list((self.root / 'output/partial').iterdir()), [])

    def test_missing_boot_is_not_a_successful_stock_package(self):
        with self.assertRaisesRegex(ValueError, 'boot.img'):
            self.extract([('rom/images/super.img', b'data')])
        self.assertFalse((self.root / 'output').exists())

    def test_raw_backup_survives_subsequent_payload_inspection_failure(self):
        archive = self.archive([('rom/no-images.txt', b'no boot')])
        saved = self.root / 'saved'
        original = stock_rom.prepare_original_rom(archive, saved, part_bytes=64)
        with self.assertRaisesRegex(ValueError, 'boot.img'):
            stock_rom.extract_rom(archive, self.root / 'output', include_original=False)
        self.assertEqual(b''.join((saved / 'assets' / p['name']).read_bytes()
                                 for p in original['assets']), archive.read_bytes())
        self.assertTrue((saved / 'assets/original-rom-manifest.json').is_file())

    def test_payload_only_does_not_copy_the_already_saved_original(self):
        archive = self.archive([('rom/images/boot.img', b'boot')])
        manifest = stock_rom.extract_rom(archive, self.root / 'output', include_original=False)
        self.assertTrue(manifest['original_rom']['assets'])
        self.assertFalse(any((self.root / 'output/assets' / p['name']).exists()
                             for p in manifest['original_rom']['assets']))

    def test_known_da_is_in_inventory_but_not_treated_as_partition(self):
        root = f'selene_images_{stock_rom.ROM_VERSION}_13.0'
        manifest = self.extract([(f'{root}/images/boot.img', b'boot'),
                                 (f'{root}/MTK_AllInOne_DA_mt6768.bin', b'da'),
                                 (f'{root}/MTK_AllInOne_DA.bin', b'da2')])
        self.assertEqual([p['name'] for p in manifest['payloads']], ['boot.img'])
        inventory = json.loads((self.root / 'output/assets/archive-inventory.json').read_text())
        self.assertEqual(inventory[-1]['role'], 'download-agent-companion')
        self.assertEqual(inventory[-2]['role'], 'download-agent-companion')

    def test_da_exception_does_not_allow_links_or_other_outside_bins(self):
        root = f'selene_images_{stock_rom.ROM_VERSION}_13.0'
        for name in (f'{root}/other.bin', f'{root}/MTK_AllInOne_DA_mt6768.bin',
                     f'{root}/MTK_AllInOne_DA.bin', f'other/MTK_AllInOne_DA.bin'):
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE
            info.linkname = '/etc/passwd'
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.extract([(f'{root}/images/boot.img', b'boot'), (info, b'')])

    def test_both_da_companions_must_be_nonempty_regular_files(self):
        root = f'selene_images_{stock_rom.ROM_VERSION}_13.0'
        for name in stock_rom.DA_NAMES:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'companion'):
                self.extract([(f'{root}/images/boot.img', b'boot'), (f'{root}/{name}', b'')])

    def test_auto_release_search_prefers_newest_completed_marker_including_drafts(self):
        prefix = f'selene-stock-{stock_rom.ROM_VERSION}'
        marker = {'name': 'original-rom-manifest.json', 'size': 784, 'state': 'uploaded'}
        pages = [[{'id': 3, 'tag_name': prefix + '-300-1', 'assets': []},
                  {'id': 4, 'tag_name': 'unrelated', 'assets': [marker]}],
                 [{'id': 1, 'tag_name': prefix + '-100-1', 'assets': [marker]},
                  {'id': 2, 'tag_name': prefix + '-200-1', 'draft': True, 'assets': [marker]}]]
        with mock.patch.object(stock_rom.subprocess, 'check_output', return_value=json.dumps(pages)) as gh:
            self.assertEqual(stock_rom.find_original_release('owner/repo'), prefix + '-200-1')
            self.assertIn('--paginate', gh.call_args.args[0])

    def test_auto_release_without_backup_allows_upstream_but_api_errors_do_not(self):
        with mock.patch.dict(os.environ, GITHUB_REPOSITORY='owner/repo'), \
                mock.patch.object(stock_rom.subprocess, 'check_output', return_value='[[]]'):
            self.assertIsNone(stock_rom.restore_original_release('auto', self.root / 'rom.tgz'))
        with mock.patch.object(stock_rom.subprocess, 'check_output', side_effect=RuntimeError('API failed')):
            with self.assertRaisesRegex(RuntimeError, 'API failed'):
                stock_rom.find_original_release('owner/repo')

    def test_release_restores_exact_rom_and_rejects_missing_or_foreign_parts(self):
        archive = self.archive([('rom/images/boot.img', b'boot')])
        saved = self.root / 'saved'
        stock_rom.prepare_original_rom(archive, saved, part_bytes=64)
        assets = saved / 'assets'
        entries = [{'name': p.name, 'size': p.stat().st_size} for p in assets.iterdir()]
        tag = f'selene-stock-{stock_rom.ROM_VERSION}-123-1'

        def download(command, **kwargs):
            name = command[command.index('--pattern') + 1]
            destination = Path(command[command.index('--dir') + 1])
            shutil.copyfile(assets / name, destination / name)

        with mock.patch.dict(os.environ, GITHUB_REPOSITORY='owner/repo'), \
                mock.patch.object(stock_rom, 'PART_BYTES', 64), \
                mock.patch.object(stock_rom.subprocess, 'run', side_effect=download), \
                mock.patch.object(stock_rom.subprocess, 'check_output', return_value=json.dumps({'assets': entries})):
            restored = self.root / 'restored.tgz'
            stock_rom.restore_original_release(tag, restored)
            self.assertEqual(restored.read_bytes(), archive.read_bytes())
            with mock.patch.object(stock_rom, 'find_original_release', return_value=tag):
                restored_auto = self.root / 'auto.tgz'
                self.assertEqual(stock_rom.restore_original_release('auto', restored_auto), tag)
                self.assertEqual(restored_auto.read_bytes(), archive.read_bytes())
            with mock.patch.object(stock_rom.subprocess, 'check_output',
                                   return_value=json.dumps({'assets': entries[:-1]})):
                with self.assertRaises(ValueError):
                    stock_rom.restore_original_release(tag, self.root / 'missing.tgz')
            metadata = json.loads((assets / 'original-rom-manifest.json').read_text())
            metadata['source_url'] = 'https://example.test/other.tgz'
            (assets / 'original-rom-manifest.json').write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, 'fixed ROM'):
                stock_rom.restore_original_release(tag, self.root / 'foreign.tgz')

    def test_original_rom_parts_reassemble_to_exact_downloaded_archive(self):
        manifest = self.extract([('rom/images/boot.img', b'boot')], part_bytes=64)
        original = manifest['original_rom']
        self.assertEqual(original['name'], stock_rom.ROM_URL.rsplit('/', 1)[-1])
        restored = b''.join((self.root / 'output/assets' / part['name']).read_bytes()
                            for part in original['assets'])
        self.assertEqual(restored, (self.root / 'rom.tgz').read_bytes())
        self.assertTrue(all(part['bytes'] <= 64 for part in original['assets']))
        self.assertIn('cat -- ' + ' '.join(p['name'] for p in original['assets']),
                      (self.root / 'output/release-notes.md').read_text())

    def test_small_original_rom_is_published_without_splitting(self):
        manifest = self.extract([('rom/images/boot.img', b'boot')])
        original = manifest['original_rom']
        self.assertEqual(len(original['assets']), 1)
        self.assertEqual((self.root / 'output/assets' / original['name']).read_bytes(),
                         (self.root / 'rom.tgz').read_bytes())

    def test_original_rom_asset_name_cannot_collide_with_a_payload(self):
        name = stock_rom.ROM_URL.rsplit('/', 1)[-1]
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            self.extract([('rom/images/boot.img', b'boot'), (f'rom/images/{name}', b'x')])

    def test_space_budget_includes_original_rom_release_copy(self):
        archive = self.archive([('rom/images/boot.img', b'boot')])
        free = stock_rom.RESERVE_BYTES + 4 + archive.stat().st_size - 1
        with mock.patch.object(stock_rom.shutil, 'disk_usage', return_value=mock.Mock(free=free)):
            with self.assertRaisesRegex(OSError, 'Insufficient'):
                stock_rom.extract_rom(archive, self.root / 'output')
        self.assertFalse((self.root / 'output').exists())

    def test_unsafe_paths_are_rejected_before_output(self):
        for name in ('/images/boot.img', '../images/boot.img',
                     'rom/images/../boot.img', 'rom/images/a\\boot.img',
                     'rom/images/boot\n.img', 'rom/images/boot.img.'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.extract([(name, b'data')])
        self.assertFalse((self.root / 'output').exists())

    def test_links_and_special_files_cannot_be_payloads(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE):
            info = tarfile.TarInfo('rom/images/boot.img')
            info.type = kind
            info.linkname = '/etc/passwd'
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'Non-regular'):
                self.extract([(info, b'')])
        root_link = tarfile.TarInfo('rom/images')
        root_link.type = tarfile.SYMTYPE
        root_link.linkname = '/tmp'
        with self.assertRaisesRegex(ValueError, 'Non-regular images directory'):
            self.extract([(root_link, b''), ('rom/images/boot.img', b'a')])

    def test_duplicate_flattened_names_and_multiple_roots_fail(self):
        cases = [
            [('rom/images/boot.img', b'a'), ('rom/images/sub/boot.img', b'b')],
            [('rom/images/boot.img', b'a'), ('other/images/super.img', b'b')],
            [('rom/images/boot.img', b'a'), ('rom/images/BOOT.IMG', b'b')],
        ]
        for entries in cases:
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                self.extract(entries)

    def test_unexpected_image_outside_images_fails_instead_of_omitting_it(self):
        with self.assertRaisesRegex(ValueError, 'outside images'):
            self.extract([('rom/images/boot.img', b'a'), ('rom/other/tee.img', b'b')])

    def test_empty_images_fail(self):
        with self.assertRaisesRegex(ValueError, 'Empty'):
            self.extract([('rom/images/boot.img', b'')])

    def test_asset_collisions_are_rejected_before_output(self):
        cases = [
            [('rom/images/boot.img', b'abcde'), ('rom/images/boot.img.part0001', b'x')],
            [('rom/images/boot.img', b'a'), ('rom/images/stock-rom-manifest.json', b'x')],
        ]
        for entries in cases:
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                self.extract(entries, part_bytes=4)
        self.assertFalse((self.root / 'output').exists())

    def test_low_disk_space_does_not_write_payloads(self):
        disk = mock.Mock(free=0)
        with mock.patch.object(stock_rom.shutil, 'disk_usage', return_value=disk):
            with self.assertRaisesRegex(OSError, 'Insufficient'):
                self.extract([('rom/images/boot.img', b'a')])
        self.assertFalse((self.root / 'output').exists())

    def test_existing_output_is_never_overwritten(self):
        out = self.root / 'output'
        out.mkdir()
        sentinel = out / 'keep'
        sentinel.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):
            self.extract([('rom/images/boot.img', b'a')])
        self.assertEqual(sentinel.read_bytes(), b'keep')

    def test_truncated_copy_raises_and_does_not_claim_completion(self):
        with self.assertRaises(EOFError):
            stock_rom.copy_exact(io.BytesIO(b'ab'), self.root / 'incomplete', 3)

    def test_asset_limit_is_checked_before_allocating_a_large_plan(self):
        with self.assertRaisesRegex(ValueError, '1000-asset'):
            stock_rom.plan_assets([{'name': 'super.img', 'bytes': 10 ** 30}], 4)


if __name__ == '__main__':
    unittest.main()
