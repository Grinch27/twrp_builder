# Requirements: complete stock-derived assets with bounded, read-only format handling.
# Ambiguity: synthetic filesystems cannot establish vendor runtime/FBE compatibility.
# Research: AOSP sparse/liblp/boot/APEX and ext4 data paths exercised together.
# Optimization: tiny generated images; optional mke2fs only for integration fixtures.
# Risks: traversal, cycles, truncation, collisions, mixed TEE/Android libraries and partial output.
# Validation: boundary rejection, byte reassembly, inventories, closure and publication order.
import gzip
import io
import json
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from stock_rom import ROM_URL, ROM_VERSION
from stock_rom_formats import Bytes, Ext4, Logical, Parts, Sparse, checked_path, elf_info, lp_metadata
from stock_rom_analysis import Analysis, SplitWriter, cpio, expand_gzip, soter_modules, index_bundle
from test_boot import cpio as make_cpio, image as make_boot

ROOT = Path(__file__).resolve().parents[1]


def elf(needed=(), bits=64):
    data = bytearray(1024)
    data[:7] = b'\x7fELF' + bytes((2 if bits == 64 else 1, 1, 1))
    struct.pack_into('<HHI', data, 16, 3, 183 if bits == 64 else 40, 1)
    if bits == 64:
        struct.pack_into('<Q', data, 32, 64)
        struct.pack_into('<HHHHHH', data, 52, 64, 56, 2, 64, 0, 0)
        struct.pack_into('<II6Q', data, 64, 1, 4, 0, 0x1000, 0, len(data), len(data), 4096)
        stride, dynamic = 16, 256
        struct.pack_into('<II6Q', data, 120, 2, 4, dynamic, 0x1100, 0, (len(needed) + 3) * stride, 0, 8)
    else:
        struct.pack_into('<I', data, 28, 52)
        struct.pack_into('<HHHHHH', data, 40, 52, 32, 2, 40, 0, 0)
        struct.pack_into('<8I', data, 52, 1, 0, 0x1000, 0, len(data), len(data), 4, 4096)
        stride, dynamic = 8, 256
        struct.pack_into('<8I', data, 84, 2, dynamic, 0x1100, 0, (len(needed) + 3) * stride, 0, 4, 4)
    strings = b'\0' + b''.join(name.encode() + b'\0' for name in needed)
    data[512:512 + len(strings)] = strings
    values = [(5, 0x1200), (10, len(strings))]
    offset = 1
    for name in needed:
        values.append((1, offset))
        offset += len(name) + 1
    values.append((0, 0))
    for index, pair in enumerate(values):
        struct.pack_into('<qQ' if bits == 64 else '<iI', data, dynamic + index * stride, *pair)
    return bytes(data)


def soter(modules):
    total = (len(modules) + 1) * 4096
    data = bytearray(total)
    struct.pack_into('<4I', data, 20, len(modules), 88, total, 4096)
    name_offset = 88 + 16 * len(modules)
    for index, (name, body) in enumerate(modules):
        start = (index + 1) * 4096
        struct.pack_into('<4I', data, 88 + index * 16, start, start + len(body), name_offset, 0)
        encoded = name.encode() + b'\0'
        data[name_offset:name_offset + len(encoded)] = encoded
        name_offset += len(encoded)
        data[start:start + len(body)] = body
    return b'MTK-container-prefix' + gzip.compress(bytes(data), mtime=0) + b'MTK-trailer'


def super_image(partitions, slots=2):
    base, maximum = 65536, 4096
    total = base + sum(len(body) for _, body in partitions)
    result = bytearray(total)
    struct.pack_into('<II', result, 4096, 0x616c4467, 52)
    struct.pack_into('<III', result, 4096 + 40, maximum, slots, 4096)
    ptable, etable, offset = bytearray(), bytearray(), base
    extent_count = 0
    for name, body in partitions:
        count = 1 if body else 0
        ptable += struct.pack('<36s4I', name.encode(), 1, extent_count, count, 0)
        if body:
            etable += struct.pack('<QIQI', len(body) // 512, 0, offset // 512, 0)
            result[offset:offset + len(body)] = body
            offset += len(body)
            extent_count += 1
    groups = struct.pack('<36sIQ', b'main', 0, 0)
    devices = struct.pack('<QIIQ36sI', base // 512, 4096, 0, total, b'super', 0)
    tables = ptable + etable + groups + devices
    h = bytearray(128)
    struct.pack_into('<IHHI', h, 0, 0x414c5030, 10, 0, 128)
    struct.pack_into('<I', h, 44, len(tables))
    start = 0
    for n, stride, data in ((len(partitions), 52, ptable), (extent_count, 24, etable),
                            (1, 48, groups), (1, 64, devices)):
        struct.pack_into('<III', h, 80 + (0 if stride == 52 else 12 if stride == 24 else 24 if stride == 48 else 36), start, n, stride)
        start += len(data)
    for slot in range(slots):
        pos = 12288 + slot * maximum
        result[pos:pos + len(h) + len(tables)] = h + tables
    return bytes(result)


class StockFormatTests(unittest.TestCase):
    def test_parts_read_across_boundaries_and_reject_truncation_or_links(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'a').write_bytes(b'abcd')
            (p / 'b').write_bytes(b'efgh')
            reader = Parts([p / 'a', p / 'b'])
            self.assertEqual(reader.read(2, 5), b'cdefg')
            with self.assertRaises(ValueError):
                reader.read(7, 2)
            (p / 'link').symlink_to(p / 'a')
            with self.assertRaises(ValueError):
                Parts([p / 'link'])

    def test_sparse_raw_fill_zero_and_malformed_chunk(self):
        chunks = [struct.pack('<HHII', 0xcac1, 0, 1, 524) + b'A' * 512,
                  struct.pack('<HHII', 0xcac2, 0, 1, 16) + b'BCDE',
                  struct.pack('<HHII', 0xcac3, 0, 1, 12),
                  struct.pack('<HHII', 0xcac4, 0, 0, 16) + bytes(4)]
        data = struct.pack('<I4H4I', 0xed26ff3a, 1, 0, 28, 12, 512, 3, 4, 0) + b''.join(chunks)
        reader = Sparse(Bytes(data))
        self.assertEqual(reader.read(509, 10), b'AAA' + b'BCDEBCD')
        self.assertEqual(reader.read(1024, 512), bytes(512))
        for bad in (data[:-1], data + b'junk', data[:28] + struct.pack('<HHII', 0x1234, 0, 1, 12) + data[40:]):
            with self.subTest(size=len(bad)), self.assertRaises(ValueError):
                Sparse(Bytes(bad))

    def test_liblp_mapping_retains_empty_and_nonempty_b_slots(self):
        raw = super_image([('system_a', b'A' * 4096), ('system_b', b'B' * 4096), ('vendor_b', b'')])
        metadata = lp_metadata(Bytes(raw))
        self.assertEqual([p['bytes'] for p in metadata['partitions']], [4096, 4096, 0])
        self.assertEqual(lp_metadata(Bytes(raw), 1)['partitions'], metadata['partitions'])
        self.assertEqual(Logical(Bytes(raw), metadata['partitions'][1]['extents']).read(0, 4), b'BBBB')
        with self.assertRaises(ValueError):
            lp_metadata(Bytes(raw), 2)
        bad = bytearray(raw)
        struct.pack_into('<I', bad, 12288 + 92 + 4, 1000000)
        with self.assertRaises(ValueError):
            lp_metadata(Bytes(bad))

    def test_paths_cpio_metadata_and_truncated_gzip(self):
        for name in ('../escape', '/absolute', 'a//b', 'a/./b', 'a\\b', 'a\x00b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                checked_path(name)
        raw = make_cpio([('relative', b'../outside', stat.S_IFLNK | 0o777),
                         ('file', b'contents', stat.S_IFREG | 0o640)])
        records = cpio(raw)
        self.assertEqual(records[0]['_data'], b'../outside')
        self.assertEqual(records[1]['mode'] & 0o777, 0o640)
        with self.assertRaises(ValueError):
            cpio(make_cpio([('../escape', b'x', stat.S_IFREG)]))
        with self.assertRaises(ValueError):
            cpio(raw[:-200])
        with self.assertRaises(ValueError):
            expand_gzip(gzip.compress(b'A' * 1000), 999)
        with self.assertRaises(ValueError):
            expand_gzip(gzip.compress(b'abc')[:-2], 1000)

    def test_cpio_hardlinks_retain_payload_for_each_name(self):
        data = bytearray(make_cpio([('a', b'body', stat.S_IFREG | 0o644),
                                    ('b', b'', stat.S_IFREG | 0o644)]))
        offset = 0
        for _ in range(2):
            namesize = int(data[offset + 94:offset + 102], 16)
            size = int(data[offset + 54:offset + 62], 16)
            data[offset + 6:offset + 14] = b'00000001'
            data[offset + 38:offset + 46] = b'00000002'
            body = (offset + 110 + namesize + 3) // 4 * 4
            offset = (body + size + 3) // 4 * 4
        records = cpio(bytes(data))
        self.assertEqual([r['_data'] for r in records], [b'body', b'body'])
        self.assertEqual(records[1]['cpio_record_bytes'], 0)

    def test_soter_uses_table_names_offsets_and_rejects_corrupt_records(self):
        tee = soter([('ree_agent', elf()), ('arm-v8-mtk-plat.cfg', b'-- config\n')])
        metadata, expanded = soter_modules(tee)
        self.assertEqual(len(metadata['modules']), 2)
        self.assertEqual(metadata['modules'][1]['_data'], b'-- config\n')
        self.assertEqual(expanded[metadata['modules'][0]['offset']:][:4], b'\x7fELF')
        bad = bytearray(expanded)
        struct.pack_into('<I', bad, 88 + 4, len(expanded) + 1)
        with self.assertRaises(ValueError):
            soter_modules(gzip.compress(bad))

    def test_elf_needed_for_both_abis_and_invalid_dynamic_strings(self):
        for bits in (32, 64):
            info = elf_info(Bytes(elf(('liba.so', 'libb.so'), bits)))
            self.assertEqual(info['bits'], bits)
            self.assertEqual(info['needed'], ['liba.so', 'libb.so'])
            self.assertEqual(info['dynamic_symbols'], 'no-section-table')
        data = bytearray(elf(('liba.so',)))
        struct.pack_into('<Q', data, 256 + 2 * 16 + 8, 50000)
        with self.assertRaises(ValueError):
            elf_info(Bytes(data))
        self.assertIsNone(elf_info(Bytes(b'opaque TA envelope')))

    def test_elf_dynamic_symbol_import_strength_and_exports(self):
        data = bytearray(elf()) + bytearray(192)
        struct.pack_into('<Q', data, 40, 1024)
        struct.pack_into('<HH', data, 58, 64, 3)
        names = b'\0strong_import\0weak_import\0exported_api\0'
        data[800:800 + len(names)] = names
        struct.pack_into('<II4QII2Q', data, 1024 + 64, 0, 11, 0, 0, 600, 96, 2, 0, 8, 24)
        struct.pack_into('<II4QII2Q', data, 1024 + 128, 0, 3, 0, 0, 800, len(names), 0, 0, 1, 0)
        for index, (name, binding, section) in enumerate(((1, 1, 0), (15, 2, 0), (27, 1, 1)), 1):
            struct.pack_into('<IBBHQQ', data, 600 + index * 24, name, binding << 4 | 2, 0, section, 0, 0)
        info = elf_info(Bytes(bytes(data)))
        self.assertEqual(info['imports'], {'strong': ['strong_import'], 'weak': ['weak_import']})
        self.assertEqual(info['exports'], ['exported_api'])

    def test_split_writer_exact_reassembly_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'assets').mkdir()
            (p / 'partial').mkdir()
            used = set()
            writer = SplitWriter(p, 'logical.img', used, part_bytes=4)
            writer.write(b'abc')
            writer.write(b'defghij')
            info = writer.finish()
            self.assertEqual([a['bytes'] for a in info['assets']], [4, 4, 2])
            self.assertEqual(b''.join((p / 'assets' / a['name']).read_bytes() for a in info['assets']), b'abcdefghij')
            with self.assertRaises(ValueError):
                SplitWriter(p, 'logical.img', used, part_bytes=4).write(b'x')

    def test_zip_reads_only_exact_member_and_rejects_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as z:
                z.writestr('../outside', b'bad')
                z.writestr('apex_payload.img', b'good')
            with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as z:
                Analysis.zip_member(z, 'apex_payload.img', p / 'payload')
            self.assertEqual((p / 'payload').read_bytes(), b'good')
            self.assertEqual(sorted(x.name for x in p.iterdir()), ['payload'])
            with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as z, self.assertRaises(ValueError):
                Analysis.zip_member(z, 'missing', p / 'missing')

    def test_total_asset_limit_accepts_1000_and_refuses_1001(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'assets').mkdir()
            (p / 'partial').mkdir()
            used = {f'existing-{i}' for i in range(999)}
            writer = SplitWriter(p, 'last.img', used)
            writer.write(b'x')
            writer.finish()
            self.assertEqual(len(used), 1000)
            with self.assertRaisesRegex(ValueError, 'limit'):
                SplitWriter(p, 'excess.img', used).write(b'x')

    def test_stock_workflow_publishes_only_after_analysis_and_keeps_triggers(self):
        source = (ROOT / '.github/workflows/stock_rom.yml').read_text()
        self.assertEqual(source.count("paths: ['.github/workflows/stock_rom.yml']"), 2)
        backup = source.index('gh release upload "${tag}" "${ROM_WORK}/original/assets/original-rom-manifest.json"')
        analysis = source.index('/usr/bin/python3 scripts/stock_rom_analysis.py ')
        publish = source.index('--draft=false --latest=false')
        self.assertLess(backup, analysis)
        self.assertLess(analysis, source.index('gh release upload "${tag}" "${ROM_WORK}/analysis/assets/"*'))
        self.assertLess(analysis, publish)

    def test_light_index_keeps_configs_and_tee_but_omits_android_binaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ('assets', 'partial', 'bundle/files/vendor_a/lib64', 'bundle/tee/modules', 'bundle/boot'):
                (root / folder).mkdir(parents=True, exist_ok=True)
            samples = {'files/vendor_a/lib64/libTEECommon.so': elf(),
                       'files/vendor_a/build.prop': b'ro.build.version.release=13\n',
                       'tee/modules/000-ree_agent': elf(), 'boot/kernel.bin': b'kernel',
                       'selected-files.json': b'[]'}
            for path, data in samples.items():
                (root / 'bundle' / path).write_bytes(data)
            item = index_bundle(root, set())
            with tarfile.open(root / 'assets' / item['name']) as archive:
                self.assertEqual(set(archive.getnames()), {'files/vendor_a/build.prop',
                                                         'tee/modules/000-ree_agent', 'selected-files.json'})


@unittest.skipUnless(shutil.which('mke2fs'), 'mke2fs missing; generated ext4 integration unavailable')
class StockAnalysisIntegrationTests(unittest.TestCase):
    def filesystem(self, root, name, files):
        tree = root / (name + '-tree')
        tree.mkdir()
        for path, body in files.items():
            target = tree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(body, tuple):
                target.symlink_to(body[1])
            else:
                target.write_bytes(body)
        (tree / 'link').symlink_to('../outside')
        target = root / (name + '.img')
        subprocess.run(['mke2fs', '-q', '-t', 'ext4', '-F', '-b', '4096', '-I', '256',
                        '-O', '^has_journal,^metadata_csum,^64bit', '-d', str(tree), str(target), '1024'],
                       check=True, capture_output=True, timeout=30)
        return target.read_bytes()

    def inputs(self, root):
        apex_payload = self.filesystem(root, 'apex', {'apex_manifest.json': b'{"name":"com.synthetic.runtime"}',
                                                    'lib64/libruntime.so': elf()})
        apex = io.BytesIO()
        with zipfile.ZipFile(apex, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('apex_payload.img', apex_payload)
        capex = io.BytesIO()
        with zipfile.ZipFile(capex, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('original_apex', apex.getvalue())
        system = self.filesystem(root, 'system', {'system/build.prop': b'ro.build.version.release=13\n',
                                                'system/bin/vold': elf(('libtest.so',)),
                                                'system/lib64/libtest.so': ('link', 'libtest.real.so'),
                                                'system/lib64/libtest.real.so': elf(),
                                                'system/apex/synthetic.apex': apex.getvalue(),
                                                'system/apex/synthetic.capex': capex.getvalue(),
                                                'empty': b'', 'nested/file': b'payload'})
        vendor = self.filesystem(root, 'vendor', {
            'build.prop': b'ro.vendor.build.security_patch=2023-12-01\n',
            'etc/init/microtrust.rc': b'on post-fs\n    start teei_daemon\nservice teei_daemon /vendor/bin/teei_daemon\n    user root\n',
            'etc/vintf/manifest.xml': b'<manifest><hal><name>android.hardware.keymaster</name></hal></manifest>',
            'bin/hw/android.hardware.keymaster@4.1-service.beanpod': elf(('libTEECommon.so',)),
            'lib64/libTEECommon.so': elf(),
            'thh/ta/c09c9c5daa504b78b0e46eda61556c3a.ta': b'opaque TA envelope'})
        output = root / 'payload'
        assets = output / 'assets'
        assets.mkdir(parents=True)
        data = {'boot.img': make_boot(), 'super.img': super_image([('system_a', system), ('system_b', b''), ('vendor_a', vendor)]),
                'tee.img': soter([('ree_agent', elf(('libTEECommon.so',))),
                                  ('arm-v8-mtk-plat.cfg', b'-- config\n'),
                                  ('libTEECommon.so', elf())])}
        planned = []
        for name, body in data.items():
            (assets / name).write_bytes(body)
            planned.append({'name': name, 'path': 'images/' + name, 'bytes': len(body),
                            'assets': [{'name': name, 'bytes': len(body)}]})
        (assets / 'stock-rom-manifest.json').write_text(json.dumps({
            'source_url': ROM_URL, 'rom_version': ROM_VERSION, 'device': 'selene',
            'original_rom': {'assets': []}, 'payloads': planned}))
        (output / 'release-notes.md').write_text('Original ROM retained.\n')
        return output

    def test_end_to_end_complete_assets_and_originals_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.inputs(root)
            original = {p.name: p.read_bytes() for p in (payload / 'assets').iterdir()}
            output = root / 'analysis'
            with patch('stock_rom_analysis.shutil.disk_usage', return_value=shutil._ntuple_diskusage(10**12, 0, 10**12)):
                report = Analysis(payload, output).run()
            self.assertEqual(report['status'], 'COMPLETE_OFFLINE_EXTRACTION')
            self.assertEqual(report['tee_module_count'], 3)
            self.assertEqual(len(report['apex_packages']), 2)
            self.assertEqual(report['super']['partitions'][1]['status'], 'empty-no-image')
            self.assertFalse((output / 'assets/logical-system_b.img').exists())
            with tarfile.open(output / 'assets/stock-files-system_a.tar.gz') as archive:
                self.assertTrue(all(member.isfile() for member in archive))
                metadata = json.load(archive.extractfile('filesystem.json'))
                self.assertEqual(archive.extractfile('files/nested/file').read(), b'payload')
                link = next(item for item in metadata['entries'] if item['path'] == 'link')
                self.assertEqual(link['link_target'], '../outside')
            dependency = json.loads((output / 'bundle/elf/dependencies.json').read_text())
            edge = next(e for e in dependency['edges'] if e['needed'] == 'libTEECommon.so' and e['domain'] == 'android')
            self.assertEqual(edge['candidate_files'], ['vendor_a/lib64/libTEECommon.so'])
            self.assertEqual(edge['domain'], 'android')
            secure = next(e for e in dependency['edges'] if e['needed'] == 'libTEECommon.so' and e['domain'] == 'tee')
            self.assertEqual(secure['candidate_files'], ['tee/modules/002-libTEECommon.so'])
            self.assertEqual(dependency['within_image_aliases']['system_a/system/lib64/libtest.so'],
                             'system_a/system/lib64/libtest.real.so')
            for p in (payload / 'assets').iterdir():
                self.assertEqual(p.read_bytes(), original[p.name])
            self.assertFalse((root / 'outside').exists())
            with self.assertRaises(ValueError):
                Analysis(payload, output)

    def test_insufficient_space_never_emits_completion_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.inputs(root)
            output = root / 'analysis'
            with patch('stock_rom_analysis.shutil.disk_usage', return_value=shutil._ntuple_diskusage(0, 0, 0)):
                with self.assertRaisesRegex(ValueError, 'disk space'):
                    Analysis(payload, output).run()
            self.assertFalse((output / 'assets/stock-analysis.json').exists())

    def test_unexpected_attachment_prevents_completion_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.inputs(root)
            output = root / 'analysis'
            analysis = Analysis(payload, output)
            (output / 'assets/unexpected.bin').write_bytes(b'not declared')
            with patch('stock_rom_analysis.shutil.disk_usage', return_value=shutil._ntuple_diskusage(10**12, 0, 10**12)):
                with self.assertRaisesRegex(ValueError, 'unexpected'):
                    analysis.run()
            self.assertFalse((output / 'assets/stock-analysis.json').exists())


if __name__ == '__main__':
    unittest.main()
