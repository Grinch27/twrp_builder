# Requirements: generated Android boot-v2/cpio fixtures, without device data.
# Ambiguity: static acceptance is independent of device compatibility.
# Research: real TWRP image and device tests remain outstanding.
# Optimization: tiny synthetic payloads and no subprocess decompression.
# Risks: malformed headers, bad stock identity and unsafe cpio paths.
# Validation: positive fixture plus independently corrupted failure cases.
import gzip
from pathlib import Path
import stat
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import verify_boot as boot

KERNEL = b'kernel-fixture'
DTB = b'dtb-fixture'
FSTAB = b'fstab-fixture\n'


def cpio(items):
    result = bytearray()
    for name, data, mode in [*items, ('TRAILER!!!', b'', 0)]:
        encoded = name.encode() + b'\0'
        fields = [0, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(encoded), 0]
        result += b'070701' + ''.join(f'{v:08x}' for v in fields).encode() + encoded
        result += b'\0' * (-len(result) % 4)
        result += data
        result += b'\0' * (-len(result) % 4)
    return bytes(result)


def image(items=None):
    if items is None:
        items = [('init', b'/system/bin/init', stat.S_IFLNK | 0o777),
                 ('system/bin/recovery', b'\x7fELFfixture', stat.S_IFREG | 0o755),
                 ('system/etc/recovery.fstab', FSTAB, stat.S_IFREG | 0o644),
                 ('first_stage_ramdisk/fstab.mt6768', FSTAB, stat.S_IFREG | 0o644),
                 ('vendor/firmware/novatek_ts_fw.bin', b'touch-fw', stat.S_IFREG | 0o644)]
    ramdisk = gzip.compress(cpio(items))
    header = bytearray(2048)
    header[:8] = b'ANDROID!'
    struct.pack_into('<10I', header, 8, len(KERNEL), 0x40080000, len(ramdisk),
                     0x47c80000, 0, 0, 0x4BC80000, 2048, 2, (2023 - 2000) << 4 | 12)
    cmdline = b'bootopt=64S3,32N2,64N2'
    header[64:64 + len(cmdline)] = cmdline
    struct.pack_into('<I', header, 1644, 1660)
    struct.pack_into('<IQ', header, 1648, len(DTB), 0x4BC80000)
    result = bytes(header)
    for data in [KERNEL, ramdisk, DTB]:
        result += data + b'\0' * (-len(data) % 2048)
    return result + b'AVBf' + b'\0' * 60


class BootTests(unittest.TestCase):
    def test_valid_static_image_keeps_device_tests_unverified(self):
        report = boot.verify(image(), KERNEL, DTB, FSTAB)
        self.assertEqual(report['static_validation'], 'PASS')
        self.assertEqual(report['device_boot'], 'NOT_TESTED')
        self.assertEqual(report['fbe_decryption'], 'NOT_TESTED')
        self.assertEqual(report['safe_to_flash'], 'NOT_ESTABLISHED')

    def test_wrong_kernel_and_dtb(self):
        for kernel, dtb in [(b'wrong', DTB), (KERNEL, b'wrong')]:
            with self.subTest(kernel=kernel, dtb=dtb), self.assertRaises(ValueError):
                boot.verify(image(), kernel, dtb, FSTAB)

    def test_wrong_fstab(self):
        with self.assertRaises(ValueError):
            boot.verify(image(), KERNEL, DTB, b'wrong')

    def test_header_corruption(self):
        for offset, value in [(0, 0), (8, 0), (12, 0), (16, 0), (36, 4096), (40, 3),
                              (44, 0), (1632, 1), (1644, 1), (1648, 0xFFFFFFFF)]:
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                data = bytearray(image())
                struct.pack_into('<I', data, offset, value)
                boot.verify(bytes(data), KERNEL, DTB, FSTAB)

    def test_image_limit_and_truncation(self):
        data = image()
        for broken in [data[:10], data[:-64], data[:4096]]:
            with self.subTest(length=len(broken)), self.assertRaises(ValueError):
                boot.verify(broken, KERNEL, DTB, FSTAB)
        with patch.object(boot, 'MAX_IMAGE', len(data) - 1), self.assertRaises(ValueError):
            boot.verify(data, KERNEL, DTB, FSTAB)

    def test_missing_recovery_or_firmware(self):
        for items in [[], [('system/bin/recovery', b'\x7fELF', stat.S_IFREG | 0o755)]]:
            with self.assertRaises(ValueError):
                boot.verify(image(items), KERNEL, DTB, FSTAB)

    def test_cpio_traversal_and_duplicate_names(self):
        for items in [[('../outside', b'x', stat.S_IFREG)],
                      [('file', b'1', stat.S_IFREG), ('file', b'2', stat.S_IFREG)]]:
            with self.assertRaises(ValueError):
                boot.cpio_entries(cpio(items))

    def test_cpio_truncation_and_decompression_limit(self):
        archive = cpio([('file', b'content', stat.S_IFREG)])
        with self.assertRaises(ValueError):
            boot.cpio_entries(archive[:-120])
        with patch.object(boot, 'MAX_RAMDISK', 16), self.assertRaises(ValueError):
            boot.ramdisk_files(gzip.compress(archive))
        with self.assertRaises(ValueError):
            boot.ramdisk_files(b'unexpected compression')


if __name__ == '__main__':
    unittest.main()
