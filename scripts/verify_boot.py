#!/usr/bin/env python3
# Requirements: a new selene boot image, with the reviewed stock kernel and DTB.
# Ambiguity: static validation cannot prove device startup or FBE compatibility.
# Research: device tests need separate approval and current backup evidence.
# Optimization: read the bounded boot image once; never extract ramdisk paths.
# Risks: malformed offsets, decompression expansion, wrong stock inputs.
# Validation: header v2, 64 MiB limit, payload identities, TWRP/fstab/firmware.
"""Validate a selene recovery-as-boot image without accessing a device."""

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import sys

from source_inputs import relative_path

MAX_IMAGE = 67108864
MAX_RAMDISK = 128 * 1024**2


def align(value, page):
    return (value + page - 1) // page * page


def cpio_entries(data):
    entries, offset = {}, 0
    while offset + 110 <= len(data):
        header = data[offset:offset + 110]
        if header[:6] not in (b"070701", b"070702"):
            raise ValueError("unsupported ramdisk cpio format")
        fields = [int(header[6 + n * 8:14 + n * 8], 16) for n in range(13)]
        mode, size, namesize = fields[1], fields[6], fields[11]
        start = offset + 110
        if not 1 <= namesize <= 4096 or start + namesize > len(data):
            raise ValueError("truncated ramdisk filename")
        raw_name = data[start:start + namesize]
        if not raw_name.endswith(b"\0"):
            raise ValueError("unterminated ramdisk filename")
        name = raw_name[:-1].decode("utf-8")
        body = align(start + namesize, 4)
        if body + size > len(data):
            raise ValueError("truncated ramdisk entry")
        if name == "TRAILER!!!":
            return entries
        # Android mkbootfs can include the archive root as a directory entry.
        if name != ".":
            if name.startswith("./"):
                name = name[2:]
            relative_path(name)
            if name in entries:
                raise ValueError("duplicate ramdisk entry")
            entries[name] = (mode, data[body:body + size])
        offset = align(body + size, 4)
    raise ValueError("ramdisk has no cpio trailer")


def ramdisk_files(data):
    if not data.startswith(b"\x1f\x8b"):
        raise ValueError("expected gzip ramdisk; review any compression change explicitly")
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
        expanded = stream.read(MAX_RAMDISK + 1)
    if len(expanded) > MAX_RAMDISK:
        raise ValueError("ramdisk exceeds decompression limit")
    return cpio_entries(expanded)


def verify(data, kernel, dtb, fstab):
    if not 1660 <= len(data) <= MAX_IMAGE or data[:8] != b"ANDROID!":
        raise ValueError("invalid boot image magic or size")
    values = struct.unpack_from("<10I", data, 8)
    kernel_size, kernel_addr, ramdisk_size, ramdisk_addr, second_size, _, tags_addr, page, version, os_version = values
    if version != 2 or page != 2048 or struct.unpack_from("<I", data, 1644)[0] != 1660:
        raise ValueError("unexpected boot header version, page or header size")
    if (kernel_addr, ramdisk_addr, tags_addr) != (0x40080000, 0x47c80000, 0x4BC80000):
        raise ValueError("unexpected boot load addresses")
    if os_version & 0x7FF != ((2023 - 2000) << 4 | 12):
        raise ValueError("unexpected boot patch year/month")
    command = (data[64:576].split(b"\0", 1)[0] + b" "
               + data[608:1632].split(b"\0", 1)[0]).decode("ascii")
    if b"bootopt=64S3,32N2,64N2" not in command.encode().split():
        raise ValueError("required boot command line missing")
    recovery_dtbo_size = struct.unpack_from("<I", data, 1632)[0]
    dtb_size, dtb_addr = struct.unpack_from("<IQ", data, 1648)
    if recovery_dtbo_size or second_size or not kernel_size or not ramdisk_size or not dtb_size:
        raise ValueError("unexpected or empty boot image sections")
    if dtb_addr != 0x4BC80000:
        raise ValueError("unexpected DTB load address")
    kernel_start = page
    ramdisk_start = kernel_start + align(kernel_size, page)
    dtb_start = ramdisk_start + align(ramdisk_size, page)
    if dtb_start + dtb_size > len(data) - 64 or data[-64:-60] != b"AVBf":
        raise ValueError("truncated boot sections or missing AVB footer")
    if data[kernel_start:kernel_start + kernel_size] != kernel:
        raise ValueError("kernel differs from reviewed stock input")
    if data[dtb_start:dtb_start + dtb_size] != dtb:
        raise ValueError("DTB differs from reviewed stock input")
    files = ramdisk_files(data[ramdisk_start:ramdisk_start + ramdisk_size])
    if "init" not in files:
        raise ValueError("ramdisk init missing")
    binaries = [files.get(name) for name in ("system/bin/recovery", "sbin/recovery")]
    if not any(entry and stat.S_ISREG(entry[0]) and entry[1].startswith(b"\x7fELF") for entry in binaries):
        raise ValueError("TWRP recovery binary missing")
    for name in ("system/etc/recovery.fstab", "first_stage_ramdisk/fstab.mt6768"):
        entry = files.get(name)
        if not entry or not stat.S_ISREG(entry[0]) or entry[1] != fstab:
            raise ValueError("stock-v14 ramdisk fstab mismatch")
    firmware = files.get("vendor/firmware/novatek_ts_fw.bin")
    if not firmware or not stat.S_ISREG(firmware[0]) or not firmware[1]:
        raise ValueError("Novatek touch firmware missing")
    return {
        "static_validation": "PASS", "image_bytes": len(data),
        "image_sha256": hashlib.sha256(data).hexdigest(), "header_version": version,
        "page_bytes": page, "os_patch_year_month": "2023-12",
        "kernel_sha256": hashlib.sha256(kernel).hexdigest(),
        "dtb_sha256": hashlib.sha256(dtb).hexdigest(), "ramdisk_entries": len(files),
        "kernel_dtb_fstab_match": True,
        "device_boot": "NOT_TESTED", "touch": "NOT_TESTED", "fbe_decryption": "NOT_TESTED",
        "backup_restore": "NOT_TESTED", "safe_to_flash": "NOT_ESTABLISHED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--stock", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.image.is_symlink() or not args.image.is_file() or args.image.stat().st_size > MAX_IMAGE:
        raise ValueError("missing, oversized or linked boot image")
    result = verify(args.image.read_bytes(), (args.stock / "kernel").read_bytes(),
                    (args.stock / "dtb/selene.dtb").read_bytes(), (args.stock / "fstab.mt6768").read_bytes())
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print("Boot image static validation passed; device functions remain untested.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error):
        print("Boot image static validation failed.", file=sys.stderr)
        sys.exit(1)
