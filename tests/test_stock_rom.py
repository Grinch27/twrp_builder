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
from pathlib import Path
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
