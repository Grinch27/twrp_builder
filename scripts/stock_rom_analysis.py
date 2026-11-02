#!/usr/bin/env python3
# Requirements: reusable stock boot, logical filesystems, APEX and TEE/FBE evidence.
# Ambiguity: static providers and proprietary TA contents are not runtime proof.
# Research: fixed V14 stock layout, AOSP boot/liblp/APEX and L4 module-table fields.
# Optimization: reuse extracted local payload parts; stream logical images and tar files.
# Risks: hostile paths/offsets, partial Release, disk exhaustion and unsupported formats.
# Validation: bounded readers, exact lengths, complete manifests and synthetic/real ROMs.
"""Prepare reusable offline analysis assets from stock_rom.py's local output."""

import argparse
import gzip
import io
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import stat
import struct
import tarfile
import tempfile
import zipfile
import zlib
import xml.etree.ElementTree as ET

from stock_rom import PART_BYTES, RESERVE_BYTES, ROM_URL, ROM_VERSION
from stock_rom_formats import (Bytes, Ext4, Logical, Parts, Slice, checked_path,
                               elf_info, image_reader, lp_metadata, require)


METADATA = ('stock-analysis.json', 'stock-analysis.md')
MAX_SELECTED = 2 * 1024**3
MAX_APEX = 1024**3
MAX_APEX_TOTAL = 2 * 1024**3
REQUIRED_FILES = ('system_a/system/build.prop', 'vendor_a/build.prop',
                  'vendor_a/etc/init/microtrust.rc',
                  'vendor_a/bin/hw/android.hardware.keymaster@4.1-service.beanpod',
                  'vendor_a/lib64/libTEECommon.so', 'system_a/system/bin/vold',
                  'vendor_a/thh/ta/c09c9c5daa504b78b0e46eda61556c3a.ta')
FOCUS = re.compile(r'keymaster|keymint|gatekeeper|keystore|vold|teei|microtrust|beanpod|'
                   r'rpmb|sst|itrust|isee|cryptfs|fscrypt|weaver|hwservicemanager|servicemanager', re.I)


def dump_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


class SplitWriter:
    """Write bounded parts in a private staging directory; expose only complete assets."""

    def __init__(self, output, name, used, part_bytes=PART_BYTES):
        require(0 < part_bytes <= PART_BYTES, 'Invalid asset part size')
        checked_path(name)
        require('/' not in name, 'Asset names cannot contain directories')
        self.output, self.name, self.used, self.limit = Path(output), name, used, part_bytes
        self.parts, self.stream, self.current, self.total = [], None, 0, 0

    def write(self, data):
        whole = len(data)
        view = memoryview(data)
        while view:
            if self.stream is None or self.current == self.limit:
                if self.stream:
                    self.stream.close()
                require(len(self.parts) + len(self.used) + 1 <= 1000, 'Release asset limit exceeded')
                part_name = f'{self.name}.part{len(self.parts) + 1:04d}'
                require(part_name.casefold() not in self.used and self.name.casefold() not in self.used,
                        'Conflicting derived asset name')
                self.stream = (self.output / 'partial' / part_name).open('xb')
                self.parts.append({'name': part_name, 'bytes': 0})
                self.current = 0
            take = min(len(view), self.limit - self.current)
            self.stream.write(view[:take])
            self.current += take
            self.total += take
            self.parts[-1]['bytes'] += take
            view = view[take:]
        return whole

    def flush(self):
        if self.stream:
            self.stream.flush()

    def finish(self):
        if self.stream:
            self.stream.close()
        require(self.total > 0, 'Empty derived asset')
        original_names = [p['name'] for p in self.parts]
        if len(self.parts) == 1:
            self.parts[0]['name'] = self.name
        for old, part in zip(original_names, self.parts):
            require(part['name'].casefold() not in self.used, 'Conflicting completed asset')
            destination = self.output / 'assets' / part['name']
            require(not destination.exists(), 'Refusing asset overwrite')
            (self.output / 'partial' / old).rename(destination)
            self.used.add(part['name'].casefold())
        return {'name': self.name, 'bytes': self.total, 'assets': self.parts}


def tar_bytes(archive, name, data):
    checked_path(name)
    info = tarfile.TarInfo(name)
    info.size, info.mode, info.mtime = len(data), 0o644, 0
    archive.addfile(info, io.BytesIO(data))


def tar_stream(archive, name, size, stream):
    checked_path(name)
    info = tarfile.TarInfo(name)
    info.size, info.mode, info.mtime = size, 0o644, 0
    archive.addfile(info, stream)


def compressed_tar(output, name, used, fill):
    writer = SplitWriter(output, name, used)
    try:
        with gzip.GzipFile(filename='', fileobj=writer, mode='wb', compresslevel=1, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode='w|', format=tarfile.PAX_FORMAT) as archive:
                fill(archive)
        return writer.finish()
    finally:
        if writer.stream and not writer.stream.closed:
            writer.stream.close()


def export_image(reader, output, name, used):
    writer = SplitWriter(output, name, used)
    try:
        for offset in range(0, reader.size, 1024 * 1024):
            writer.write(reader.read(offset, min(1024 * 1024, reader.size - offset)))
        return writer.finish()
    finally:
        if writer.stream and not writer.stream.closed:
            writer.stream.close()


def index_bundle(output, used):
    """Small independently downloadable indexes/configs and secure-world modules."""
    output = Path(output)
    root = output / 'bundle'
    def fill(archive):
        for path in sorted(root.rglob('*')):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            include = not relative.startswith('files/') and relative not in ('tee/soter-expanded.bin', 'boot/kernel.bin', 'boot/dtb.bin', 'boot/second.bin', 'boot/recovery_dtbo.bin')
            if relative.startswith('files/'):
                include = (path.suffix in ('.rc', '.prop', '.xml', '.fstab', '.conf', '.json', '.txt', '.cil', '.te')
                           or path.name.startswith(('fstab.', 'ueventd.', 'ld.config'))
                           or path.name.endswith('_contexts')) and path.stat().st_size <= 4 * 1024**2
            if include:
                with path.open('rb') as stream:
                    tar_stream(archive, relative, path.stat().st_size, stream)
    return compressed_tar(output, 'stock-analysis-index.tar.gz', used, fill)


def expand_gzip(data, limit):
    stream = zlib.decompressobj(31)
    result = stream.decompress(data, limit + 1)
    require(len(result) <= limit and stream.eof and not stream.unconsumed_tail,
            'Truncated or excessive gzip payload')
    return result, len(data) - len(stream.unused_data)


def boot_sections(reader):
    h = reader.read(0, 1660)
    require(h[:8] == b'ANDROID!', 'Unsupported stock boot magic')
    kernel, _, ramdisk, _, second, _, _, page, version, os_version = struct.unpack_from('<10I', h, 8)
    require(version in (0, 1, 2) and page in (2048, 4096, 8192, 16384)
            and kernel > 0 and ramdisk > 0, 'Unsupported stock boot header')
    align = lambda n: (n + page - 1) // page * page
    offset, sections = page, {}
    for name, size in (('kernel', kernel), ('ramdisk', ramdisk), ('second', second)):
        if size:
            sections[name] = {'offset': offset, 'bytes': size}
            require(offset + size <= reader.size, 'Truncated boot section')
        offset += align(size)
    if version >= 1:
        dtbo_size, dtbo_offset, header_size = struct.unpack_from('<IQI', h, 1632)
        require(header_size == (1648 if version == 1 else 1660), 'Unexpected boot header length')
        if dtbo_size:
            require(dtbo_offset == offset and dtbo_offset + dtbo_size <= reader.size,
                    'Invalid recovery DTBO offset')
            sections['recovery_dtbo'] = {'offset': dtbo_offset, 'bytes': dtbo_size}
            offset += align(dtbo_size)
    if version == 2:
        size, address = struct.unpack_from('<IQ', h, 1648)
        require(offset + size <= reader.size, 'Truncated boot DTB')
        if size:
            sections['dtb'] = {'offset': offset, 'bytes': size, 'load_address': address}
    return {'header_version': version, 'page_bytes': page, 'os_version_header': os_version,
            'command_line': (h[64:576].split(b'\0')[0] + b' ' + h[608:1632].split(b'\0')[0]).decode('ascii'),
            'sections': sections}


def cpio(data):
    """Retain numeric ownership and special-node metadata; never create host links."""
    offset, seen, entries = 0, set(), []
    while offset + 110 <= len(data):
        h = data[offset:offset + 110]
        require(h[:6] in (b'070701', b'070702'), 'Unsupported boot cpio')
        f = [int(h[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        number, mode, uid, gid, links, mtime, size, devmajor, devminor, major, minor, namesize, _ = f
        require(1 <= namesize <= 4096 and offset + 110 + namesize <= len(data), 'Invalid cpio name size')
        name = data[offset + 110:offset + 110 + namesize]
        require(name[-1:] == b'\0', 'Unterminated cpio name')
        name = name[:-1].decode('utf-8')
        body = (offset + 110 + namesize + 3) // 4 * 4
        require(body + size <= len(data), 'Truncated cpio file')
        if name == 'TRAILER!!!':
            groups = {}
            for entry in entries:
                if stat.S_ISREG(entry['mode']) and entry['links'] > 1:
                    groups.setdefault(entry['_hardlink_key'], []).append(entry)
            for group in groups.values():
                bodies = {entry['_data'] for entry in group if entry['_data']}
                require(len(bodies) <= 1, 'Conflicting cpio hardlink contents')
                body = next(iter(bodies), b'')
                for entry in group:
                    entry['cpio_record_bytes'] = entry['bytes']
                    entry['bytes'], entry['_data'] = len(body), body
            return entries
        if name.startswith('./'):
            name = name[2:]
        if name != '.':
            checked_path(name)
            require(name not in seen and len(seen) < 200000, 'Duplicate or excessive cpio entries')
            seen.add(name)
            entries.append({'path': name, 'inode': number, 'mode': mode, 'uid': uid, 'gid': gid,
                            'links': links, 'mtime': mtime, 'bytes': size, 'rdev_major': major,
                            'rdev_minor': minor, '_hardlink_key': (number, devmajor, devminor),
                            '_data': data[body:body + size]})
        offset = (body + size + 3) // 4 * 4
    raise ValueError('Missing cpio trailer')


def soter_modules(tee):
    """Decode the fixed V14 L4 module table, not ELF/string carving heuristics."""
    candidates, start, attempts = [], 0, 0
    while True:
        start = tee.find(b'\x1f\x8b\x08', start)
        if start < 0:
            break
        attempts += 1
        require(attempts <= 256, 'Excessive TEE gzip candidates')
        try:
            data, length = expand_gzip(tee[start:], 64 * 1024**2)
            if len(data) >= 88 and data[:20] == bytes(20):
                count, table, total, alignment = struct.unpack_from('<4I', data, 20)
                if table == 88 and total == len(data) and alignment == 4096 and 0 < count <= 1024:
                    candidates.append((start, length, data, count, table))
        except (ValueError, zlib.error):
            pass
        start += 3
    require(len(candidates) == 1, 'Expected one recognized V14 SOTER module table')
    start, length, data, count, table = candidates[0]
    require(table + count * 16 < 4096, 'Invalid SOTER module table size')
    records, previous = [], 4096
    for index in range(count):
        begin, end, name_offset, flags = struct.unpack_from('<4I', data, table + index * 16)
        require(previous <= begin < end <= len(data) and begin % 4096 == 0
                and table + count * 16 <= name_offset < 4096 and flags == 0,
                'Invalid SOTER module record')
        name_end = data.find(b'\0', name_offset, 4096)
        require(name_end >= name_offset, 'Unterminated SOTER module name')
        command = data[name_offset:name_end].decode('utf-8')
        require(command.split() and all(32 <= ord(c) != 127 for c in command), 'Invalid SOTER command line')
        name = re.sub(r'[^A-Za-z0-9._-]', '_', command.split()[0])
        require(name not in ('.', '..'), 'Invalid SOTER filename')
        records.append({'index': index, 'command': command, 'offset': begin, 'bytes': end - begin,
                        'name_offset': name_offset, 'flags': flags,
                        'bundle_path': f'tee/modules/{index:03d}-{name}',
                        '_data': data[begin:end]})
        previous = end
    return {'tee_gzip_offset': start, 'compressed_bytes': length, 'expanded_bytes': len(data),
            'format': 'V14 L4 module table: begin/end/name_offset/flags', 'modules': records}, data


def metadata_entry(entry):
    result = {key: value for key, value in entry.items() if not key.startswith('_')}
    mode = entry['mode']
    result['type'] = ('file' if stat.S_ISREG(mode) else 'directory' if stat.S_ISDIR(mode)
                      else 'symlink' if stat.S_ISLNK(mode) else 'special')
    return result


def selected(path, apex=False):
    p = PurePosixPath(path)
    return (apex and (p.suffix == '.so' or 'bin' in p.parts)
            or p.name.endswith('.prop') or p.name.startswith(('fstab.', 'init.', 'ueventd.'))
            or p.name in ('init.rc', 'linker', 'linker64', 'ld.config.txt', 'apex_manifest.json')
            or any(part in ('vintf', 'selinux', 'thh', 'tee', 'trustzone', 'linkerconfig') for part in p.parts)
            or ('etc/init' in path) or bool(FOCUS.search(p.name)))


class Analysis:
    def __init__(self, payload_output, output):
        self.payload_output, self.output = Path(payload_output), Path(output)
        manifest_path = self.payload_output / 'assets/stock-rom-manifest.json'
        require(not manifest_path.is_symlink() and manifest_path.is_file(), 'Missing local payload manifest')
        self.manifest = json.loads(manifest_path.read_text())
        require(self.manifest['source_url'] == ROM_URL and self.manifest['rom_version'] == ROM_VERSION
                and self.manifest['device'] == 'selene', 'Wrong stock source')
        self.used = {p.name.casefold() for p in (self.payload_output / 'assets').iterdir()}
        self.used.update(p['name'].casefold() for p in self.manifest['original_rom']['assets'])
        self.used.update(('original-rom-manifest.json', *METADATA))
        self.readers, self.items = {}, {}
        for item in self.manifest['payloads']:
            name = item['name']
            require(name not in self.items, 'Duplicate payload manifest entry')
            self.items[name] = item
            paths = []
            for part in item['assets']:
                checked_path(part['name'])
                require('/' not in part['name'], 'Unexpected payload asset path')
                path = self.payload_output / 'assets' / part['name']
                require(path.stat().st_size == part['bytes'], 'Wrong payload part length')
                paths.append(path)
            reader = Parts(paths)
            require(reader.size == item['bytes'], 'Wrong payload total length')
            self.readers[name] = reader
        require(all(name in self.readers for name in ('boot.img', 'super.img', 'tee.img')),
                'Required stock boot/super/tee payload missing')
        require(not self.output.exists(), 'Analysis output already exists')
        self.output.mkdir(parents=True, mode=0o700)
        for name in ('assets', 'partial', 'bundle'):
            (self.output / name).mkdir(mode=0o700)
        self.assets, self.filesystems, self.nodes, self.aliases = [], [], {}, {}
        self.selected_bytes, self.dependencies, self.apex_count = 0, {}, 0
        self.apex_expanded_bytes = 0
        self.apex_export_bytes = 0

    def save(self, name, data):
        checked_path(name)
        self.selected_bytes += len(data)
        require(self.selected_bytes <= MAX_SELECTED, 'Focused bundle exceeds byte budget')
        path = self.output / 'bundle' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
        return name

    def payload_provenance(self, name):
        return {'payload': name, 'archive_path': self.items[name]['path'],
                'assets': self.items[name]['assets']}

    def add_node(self, scope, entry, read):
        name = f'{scope}/{entry["path"]}'
        checked_path(name)
        require(name not in self.nodes, 'Duplicate analysis file')
        self.nodes[name] = {'metadata': metadata_entry(entry), 'read': read,
                            'domain': 'tee' if '/thh/ta/' in name else 'android'}
        return name

    def collect(self, scope, entries, open_file, source, apex=False, max_file_bytes=128 * 1024**2):
        """Export every regular file; links/devices stay numeric metadata only."""
        require(re.fullmatch(r'[A-Za-z0-9._-]+', scope), 'Invalid filesystem scope')
        inventory, package_entries, links = [], [], []
        for entry in entries:
            record = metadata_entry(entry)
            if not entry['path']:
                inventory.append(record)
                continue
            checked_path(entry['path'])
            if stat.S_ISLNK(entry['mode']):
                require(entry['bytes'] <= 4096, 'Excessive image symlink')
                record['link_target'] = open_file(entry).read().decode('utf-8')
                links.append((entry['path'], record['link_target']))
            if stat.S_ISREG(entry['mode']):
                name = self.add_node(scope, entry, lambda e=entry: open_file(e))
                if selected(entry['path'], apex):
                    require(entry['bytes'] <= 128 * 1024**2, 'Selected file exceeds buffer limit')
                    self.save('files/' + name, open_file(entry).read())
                package_entries.append(entry)
            inventory.append(record)
        # Resolve only links within this image, lexically; never follow a host link.
        # Cross-image /apex links are retained as metadata and handled by candidate ABI.
        link_map = dict(links)
        partition = re.sub(r'_[ab]$', '', scope)
        def resolve(path):
            visited = set()
            while path in link_map:
                if path in visited or len(visited) >= 32:
                    return None
                visited.add(path)
                target = link_map[path]
                if target.startswith('/'):
                    candidates = [target.lstrip('/')]
                    if target.startswith('/' + partition + '/'):
                        candidates.append(target[len(partition) + 2:])
                    path = next((p for p in candidates if f'{scope}/{p}' in self.nodes or p in link_map), candidates[0])
                else:
                    path = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
                if path.startswith('../') or path in ('.', '..'):
                    return None
            key = f'{scope}/{path}'
            return key if key in self.nodes else None
        for path, _ in links:
            target = resolve(path)
            if target:
                self.aliases[f'{scope}/{path}'] = target
        info = {'scope': scope, 'source': source, 'entries': inventory,
                'regular_files': len(package_entries), 'xattrs': 'NOT_DECODED; retained in raw partition',
                'links_and_devices': 'metadata only; no host links/devices created'}
        require(sum(entry['bytes'] for entry in package_entries) <= max_file_bytes,
                'Filesystem file-content budget exceeded')
        self.save(f'inventory/{scope}.json', dump_json(info))
        def fill(archive):
            for entry in package_entries:
                tar_stream(archive, 'files/' + entry['path'], entry['bytes'], open_file(entry))
            tar_bytes(archive, 'filesystem.json', dump_json(info))
        asset = compressed_tar(self.output, f'stock-files-{scope}.tar.gz', self.used, fill)
        self.assets.append(asset)
        self.filesystems.append({'scope': scope, 'source': source, 'entry_count': len(inventory),
                                 'regular_files': len(package_entries), 'file_archive': asset})
        print(f'FILESYSTEM {scope}: {len(inventory)} entries, {len(package_entries)} regular files', flush=True)

    def boot(self):
        reader = self.readers['boot.img']
        metadata = boot_sections(reader)
        for name, section in metadata['sections'].items():
            if name != 'ramdisk':
                self.save(f'boot/{name}.bin', reader.read(section['offset'], section['bytes']))
        section = metadata['sections']['ramdisk']
        compressed = reader.read(section['offset'], section['bytes'])
        data, consumed = expand_gzip(compressed, 128 * 1024**2)
        require(consumed == len(compressed), 'Unexpected trailing boot ramdisk data')
        entries = cpio(data)
        self.collect('boot-ramdisk', entries, lambda e: io.BytesIO(e['_data']),
                     {**self.payload_provenance('boot.img'), 'ramdisk': section})
        self.save('boot/header.json', dump_json(metadata))
        return metadata

    def tee(self):
        reader = self.readers['tee.img']
        require(reader.size <= 32 * 1024**2, 'Excessive tee.img')
        metadata, expanded = soter_modules(reader.read(0, reader.size))
        self.save('tee/soter-expanded.bin', expanded)
        records = []
        for module in metadata['modules']:
            self.save(module['bundle_path'], module['_data'])
            record = {k: v for k, v in module.items() if not k.startswith('_')}
            record['elf'] = elf_info(Bytes(module['_data']))
            local = self.output / 'bundle' / module['bundle_path']
            self.nodes[module['bundle_path']] = {
                'metadata': {'bytes': module['bytes']}, 'domain': 'tee',
                'provider_name': module['command'].split()[0], 'bundle_path': module['bundle_path'],
                'read': lambda p=local: p.open('rb')}
            records.append(record)
        metadata['modules'] = records
        metadata['source'] = self.payload_provenance('tee.img')
        metadata['secure_storage'] = 'NO_DEVICE_DATA; public firmware modules only'
        self.save('tee/modules.json', dump_json(metadata))
        return metadata

    def logical(self):
        source = image_reader(self.readers['super.img'])
        metadata = lp_metadata(source)
        metadata['primary_metadata_slots'] = []
        for slot in range(metadata['metadata_slots']):
            other = metadata if slot == 0 else lp_metadata(source, slot)
            require(other['partitions'] == metadata['partitions'],
                    'Different liblp slot layouts require explicit review')
            metadata['primary_metadata_slots'].append({'slot': slot, 'layout': 'same-as-slot-0'})
        metadata.pop('other_metadata_slots', None)
        metadata['backup_metadata'] = 'NOT_ANALYZED'
        size = sum(p['bytes'] for p in metadata['partitions'])
        require(size <= 16 * 1024**3, 'Fixed-ROM logical partition budget exceeded')
        plans, available = [], set()
        for partition in metadata['partitions']:
            if not partition['bytes']:
                continue
            reader = Logical(source, partition['extents'])
            fs = Ext4(reader)
            entries = list(fs.walk())
            available.update(f'{partition["name"]}/{e["path"]}' for e in entries if stat.S_ISREG(e['mode']))
            plans.append((partition, reader, fs, entries))
        require(all(name in available for name in REQUIRED_FILES), 'Fixed-ROM mandatory analysis file missing')
        file_bytes = sum(e['bytes'] for _, _, _, entries in plans for e in entries if stat.S_ISREG(e['mode']))
        require(file_bytes <= 32 * 1024**3, 'Excessive logical filesystem file-content expansion')
        # Sparse files, shared blocks and hardlinks can make contents larger than the
        # partition. Budget the actual inode lengths, not just partition sizes.
        require(shutil.disk_usage(self.output).free >= size + file_bytes + 6 * 1024**3 + RESERVE_BYTES,
                'Insufficient disk space for complete stock analysis')
        metadata['exported_regular_file_bytes'] = file_bytes
        for partition, reader, fs, entries in plans:
            partition['raw_image'] = export_image(reader, self.output,
                                                  f'logical-{partition["name"]}.img', self.used)
            self.assets.append(partition['raw_image'])
            self.collect(partition['name'], entries, fs.file,
                         {**self.payload_provenance('super.img'), 'logical_partition': partition['name']},
                         max_file_bytes=sum(e['bytes'] for e in entries if stat.S_ISREG(e['mode'])))
        self.save('super/partitions.json', dump_json(metadata))
        return metadata

    def apex(self):
        # Fully retained outer packages are already in their partition file archives.
        packages = [(name, node) for name, node in self.nodes.items()
                    if PurePosixPath(name).suffix in ('.apex', '.capex')]
        require(len(packages) <= 128, 'Excessive APEX package count')
        manifests = []
        for name, node in sorted(packages):
            require(node['metadata']['bytes'] <= MAX_APEX, 'Excessive outer APEX package')
            with tempfile.TemporaryDirectory(prefix='apex-', dir=self.output / 'partial') as temporary:
                root = Path(temporary)
                outer = root / 'package.zip'
                with outer.open('xb') as target:
                    shutil.copyfileobj(node['read'](), target, 1024 * 1024)
                with zipfile.ZipFile(outer) as package:
                    if name.endswith('.capex'):
                        self.zip_member(package, 'original_apex', root / 'original.apex')
                        outer = root / 'original.apex'
                with zipfile.ZipFile(outer) as package:
                    length = self.zip_member(package, 'apex_payload.img', root / 'payload.img',
                                             min(MAX_APEX, MAX_APEX_TOTAL - self.apex_expanded_bytes))
                    self.apex_expanded_bytes += length
                fs = Ext4(image_reader(Parts([root / 'payload.img'])))
                entries = list(fs.walk())
                file_bytes = sum(e['bytes'] for e in entries if stat.S_ISREG(e['mode']))
                self.apex_export_bytes += file_bytes
                require(self.apex_export_bytes <= MAX_APEX_TOTAL, 'Excessive total APEX file-content expansion')
                self.apex_count += 1
                scope = f'apex-{self.apex_count:03d}-{PurePosixPath(name).stem}'
                inner = {'outer_file': name, 'payload_member': 'apex_payload.img',
                         'package_name': None, 'runtime_mount': 'NOT_VERIFIED'}
                for entry in entries:
                    if entry['path'] == 'apex_manifest.json' and stat.S_ISREG(entry['mode']):
                        require(entry['bytes'] <= 1024 * 1024, 'Excessive APEX manifest')
                        inner['package_name'] = json.loads(fs.file(entry).read()).get('name')
                self.collect(scope, entries, fs.file, inner, apex=True, max_file_bytes=file_bytes)
                # APEX readers cannot outlive the temporary payload. Native binaries,
                # libraries and configs were selected above; use those saved bytes.
                for key in [k for k in self.nodes if k.startswith(scope + '/')]:
                    local = self.output / 'bundle/files' / key
                    if local.is_file():
                        self.nodes[key]['read'] = lambda p=local: p.open('rb')
                    else:
                        del self.nodes[key]
                manifests.append({'scope': scope, **inner})
        self.save('apex/packages.json', dump_json(manifests))
        return manifests

    @staticmethod
    def zip_member(package, name, destination, limit=MAX_APEX):
        matches = [entry for entry in package.infolist() if entry.filename == name]
        require(len(matches) == 1 and 0 < matches[0].file_size <= limit
                and not matches[0].is_dir(), 'Invalid or missing APEX member')
        with package.open(matches[0]) as source, destination.open('xb') as target:
            remaining = matches[0].file_size
            while remaining:
                data = source.read(min(remaining, 1024 * 1024))
                require(data, 'Truncated APEX member')
                target.write(data)
                remaining -= len(data)
            require(not source.read(1), 'APEX member exceeds declared size')
        return matches[0].file_size

    def closure(self):
        by_name = {}
        for name, node in self.nodes.items():
            by_name.setdefault(node.get('provider_name', PurePosixPath(name).name), []).append(name)
        for alias, target in self.aliases.items():
            if target in self.nodes:
                by_name.setdefault(PurePosixPath(alias).name, []).append(target)
        queue = [name for name, node in self.nodes.items() if selected(name) or node['domain'] == 'tee']
        seen, unresolved, edges = set(), [], []
        while queue:
            name = queue.pop()
            if name in seen:
                continue
            seen.add(name)
            require(len(seen) <= 10000, 'Excessive dependency closure')
            node = self.nodes[name]
            if node['metadata']['bytes'] < 4:
                continue
            stream = node['read']()
            magic = stream.read(4)
            stream.close()
            if magic != b'\x7fELF':
                continue
            require(node['metadata']['bytes'] <= 128 * 1024**2, 'Excessive selected ELF')
            with node['read']() as stream:
                data = stream.read()
            info = elf_info(Bytes(data))
            if 'bundle_path' not in node and not (self.output / 'bundle/files' / name).exists():
                self.save('files/' + name, data)
            self.dependencies[name] = info
            for needed in info['needed']:
                candidates = []
                for candidate in sorted(set(by_name.get(needed, []))):
                    candidate_node = self.nodes[candidate]
                    if candidate_node['domain'] != node['domain']:
                        continue
                    with candidate_node['read']() as stream:
                        head = stream.read(20)
                    if (len(head) == 20 and head[:4] == b'\x7fELF'
                            and head[4] == (2 if info['bits'] == 64 else 1)
                            and struct.unpack_from('<H', head, 18)[0] == info['machine']):
                        candidates.append(candidate)
                        queue.append(candidate)
                edge = {'consumer': name, 'needed': needed, 'candidate_files': candidates,
                        'domain': node['domain'],
                        'namespace_resolution': 'NOT_VERIFIED'}
                edges.append(edge)
                if not candidates:
                    unresolved.append(edge)
        report = {'elf_files': self.dependencies, 'edges': edges, 'unresolved': unresolved,
                  'within_image_aliases': self.aliases,
                  'resolution': 'all basename+ABI candidates; not Android linker namespace proof',
                  'symbol_versions': 'NOT_ANALYZED'}
        self.save('elf/dependencies.json', dump_json(report))
        return {'elf_files': len(self.dependencies), 'dependency_edges': len(edges),
                'unresolved_edges': len(unresolved), 'runtime_linking': 'NOT_VERIFIED'}

    def configuration(self):
        properties, init, fstabs, relevant, vintf = {}, [], [], [], []
        for path in sorted((self.output / 'bundle/files').rglob('*')):
            if not path.is_file() or path.stat().st_size > 4 * 1024**2:
                continue
            relative = path.relative_to(self.output / 'bundle/files').as_posix()
            if path.suffix not in ('.prop', '.rc', '.xml') and not path.name.startswith(('fstab.', 'ueventd.', 'ld.config')):
                continue
            try:
                text = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                continue
            if path.suffix == '.prop':
                properties[relative] = [line for line in text.splitlines() if re.match(
                    r'ro\.(build\.version\.(release|security_patch|sdk)|vendor\.build\.(version\.release|security_patch)|crypto\.)', line)]
            if path.suffix == '.xml' and '/vintf/' in relative:
                require('<!DOCTYPE' not in text.upper() and '<!ENTITY' not in text.upper(),
                        'VINTF XML entities are not allowed')
                tree = ET.fromstring(text)
                vintf.append({'source': relative, 'kind': tree.tag,
                              'hals': [ET.tostring(hal, encoding='unicode') for hal in tree.findall('hal')]})
            if path.suffix == '.rc':
                block = None
                for number, line in enumerate(text.splitlines(), 1):
                    if line.startswith(('service ', 'on ', 'import ')):
                        block = {'source': relative, 'line': number, 'header': line, 'commands': []}
                        init.append(block)
                    elif block and line.strip() and not line.lstrip().startswith('#'):
                        block['commands'].append({'line': number, 'text': line.strip()})
            if path.name.startswith('fstab.'):
                fstabs.append({'source': relative, 'entries': [line for line in text.splitlines()
                                                              if line.strip() and not line.lstrip().startswith('#')]})
            for number, line in enumerate(text.splitlines(), 1):
                if re.search(r'teei|microtrust|beanpod|keymaster|keymint|gatekeeper|rpmb|persist|sst|/dev/.*tee|/metadata', line, re.I):
                    relevant.append({'source': relative, 'line': number, 'text': line})
        result = {'target_properties': properties, 'init_blocks': init, 'fstabs': fstabs,
                  'vintf': vintf,
                  'tee_storage_references': relevant,
                  'init_order': 'source blocks only; property/action scheduling requires runtime validation'}
        self.save('configuration/index.json', dump_json(result))
        return {'property_files': len(properties), 'init_blocks': len(init),
                'fstab_files': len(fstabs), 'vintf_files': len(vintf),
                'tee_storage_references': len(relevant)}

    def run(self):
        boot = self.boot()
        tee = self.tee()
        super_info = self.logical()
        apex = self.apex()
        dependencies = self.closure()
        config = self.configuration()
        bundle_root = self.output / 'bundle'
        files = [{'path': path.relative_to(bundle_root).as_posix(), 'bytes': path.stat().st_size}
                 for path in sorted((bundle_root / 'files').rglob('*')) if path.is_file()]
        self.save('selected-files.json', dump_json(files))
        self.assets.append(index_bundle(self.output, self.used))
        def fill(archive):
            for path in sorted(bundle_root.rglob('*')):
                if path.is_file():
                    with path.open('rb') as stream:
                        tar_stream(archive, path.relative_to(bundle_root).as_posix(), path.stat().st_size, stream)
        bundle = compressed_tar(self.output, 'stock-analysis-bundle.tar.gz', self.used, fill)
        self.assets.append(bundle)
        commit = os.environ.get('GITHUB_SHA', '')
        manifest = {'schema': 1, 'status': 'COMPLETE_OFFLINE_EXTRACTION', 'rom_version': ROM_VERSION,
                    'source_url': ROM_URL, 'source_manifest': 'stock-rom-manifest.json',
                    'builder_commit': commit if re.fullmatch(r'[0-9a-f]{40}', commit) else 'NOT_CAPTURED',
                    'boot': boot, 'super': super_info, 'filesystems': self.filesystems,
                    'tee_module_count': len(tee['modules']), 'apex_packages': apex,
                    'dependency_analysis': dependencies, 'configuration_analysis': config,
                    'assets': self.assets, 'metadata_assets': list(METADATA),
                    'privacy': 'public factory firmware only; no device or private log inputs',
                    'limitations': ['No runtime/FBE/flash-safety proof', 'TA security envelopes remain opaque',
                                    'Sparse DONT_CARE regions are zero-filled; not device readbacks',
                                    'No linker namespace or symbol-version compatibility proof',
                                    'Primary liblp slots must describe the same layout; backups not analyzed',
                                    'Filesystem xattrs retained in raw images, not decoded',
                                    'No extra SHA256, signature/certificate or DEX scans']}
        notes = self.notes(manifest)
        # Fail before publication if any completed asset was truncated or an undeclared one appeared.
        declared = {p['name']: p['bytes'] for item in self.assets for p in item['assets']}
        # Match the workflow's non-dot asset glob; staging/internal files cannot
        # become Release attachments through that glob.
        actual = {p.name: p.stat().st_size for p in (self.output / 'assets').iterdir()
                  if not p.name.startswith('.')}
        require(set(actual) == set(declared)
                and all(actual[name] == size for name, size in declared.items())
                and len(self.used) <= 1000, 'Incomplete or unexpected analysis assets')
        # Completion is the last mutation, after all derived bytes and notes exist.
        with (self.output / 'assets' / METADATA[1]).open('x', encoding='utf-8') as stream:
            stream.write(notes)
        old_notes = (self.payload_output / 'release-notes.md').read_text()
        with (self.output / 'release-notes.md').open('x', encoding='utf-8') as stream:
            stream.write(old_notes + '\n\n' + notes)
        partial = self.output / 'partial' / METADATA[0]
        with partial.open('xb') as stream:
            stream.write(dump_json(manifest))
        partial.rename(self.output / 'assets' / METADATA[0])
        return manifest

    @staticmethod
    def notes(manifest):
        lines = ['## Reusable offline stock analysis', '',
                 'Start with `stock-analysis.md`, `stock-analysis.json` and the small `stock-analysis-index.tar.gz`.',
                 'Download `stock-analysis-bundle.tar.gz` when actual Android binaries/libraries are needed.',
                 'The bundle includes source inventories, boot sections, all TEE module payloads,',
                 'init/fstab/VINTF/SELinux/linker files, relevant properties and the ELF dependency closure.',
                 'All regular files are also exported per filesystem; links/devices are inventory records.',
                 'The archives use safe regular entries and neutral host permissions; original numeric',
                 'ownership/mode/link targets are in filesystem.json. Raw logical images retain xattrs.', '',
                 '| Logical partition | Bytes | State |', '| --- | ---: | --- |']
        for p in manifest['super']['partitions']:
            lines.append(f'| {p["name"]} | {p["bytes"]} | {p["status"]} |')
        lines += ['', f'TEE modules: {manifest["tee_module_count"]}; APEX payloads: {len(manifest["apex_packages"])}.',
                  f'ELF dependency analysis: {manifest["dependency_analysis"]}.', '',
                  '### Derived assets and reassembly', '',
                  'These raw logical images are already expanded; do not apply simg2img again.',
                  'Download every declared part into a new empty directory, then run the relevant command:', '', '```bash']
        for item in manifest['assets']:
            if len(item['assets']) > 1:
                parts = ' '.join(p['name'] for p in item['assets'])
                lines.append(f'cat -- {parts} > {item["name"]}')
        lines += ['```', '', '| Asset | Bytes | Parts |', '| --- | ---: | ---: |']
        for item in manifest['assets']:
            lines.append(f'| {item["name"]} | {item["bytes"]} | {len(item["assets"])} |')
        lines += ['', '### Evidence boundaries', ''] + ['- ' + s for s in manifest['limitations']]
        lines += ['', 'No personal keys, credentials, RPMB/persist contents from a device, or private diagnostics',
                  'are inputs. SST module presence/startup configuration is not proof of live SST health.',
                  'Absent/empty slots are not fabricated images. Do not flash individual parts.', '']
        return '\n'.join(lines)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload_output', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    manifest = Analysis(args.payload_output, args.output).run()
    print(f'Prepared complete offline stock extraction: {len(manifest["assets"])} derived assets.', flush=True)


if __name__ == '__main__':
    main()
