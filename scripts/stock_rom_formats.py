#!/usr/bin/env python3
# Requirements: read local stock sparse/super/ext4/ELF data without mounts or OEM tools.
# Ambiguity: unsupported formats/features fail; extracted files do not prove runtime ABI.
# Research: AOSP libsparse/liblp metadata_format.h and Linux ext4 on-disk documentation.
# Optimization: bounded random reads across original Release parts, no raw-super copy.
# Risks: corrupt offsets, cycles, expansion, path traversal and ambiguous dependencies.
# Validation: synthetic malformed inputs and fixed-ROM offline extraction; no new hashes.
"""Small read-only format readers for the fixed Selene stock analysis pipeline."""

import bisect
import io
from pathlib import Path
import re
import stat
import struct


MAX_READ = 128 * 1024**2


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checked_path(name):
    require(isinstance(name, str) and name and not name.startswith('/')
            and '\\' not in name and all(p not in ('', '.', '..') for p in name.split('/'))
            and len(name.encode()) <= 4096
            and all(ord(c) >= 32 and ord(c) != 127 for c in name), 'Unsafe image path')
    return name


def checked_range(size, offset, length):
    require(0 <= offset <= offset + length <= size and length <= MAX_READ,
            'Out-of-bounds or excessive image read')


class Parts:
    """Random access to manifest-declared local parts, including part boundaries."""

    def __init__(self, paths):
        self.paths = [Path(p) for p in paths]
        require(0 < len(self.paths) <= 1000, 'Invalid part count')
        self.starts, self.size = [], 0
        for path in self.paths:
            require(not path.is_symlink() and path.is_file() and path.stat().st_size > 0,
                    'Missing, empty or linked image part')
            self.starts.append(self.size)
            self.size += path.stat().st_size

    def read(self, offset, length):
        checked_range(self.size, offset, length)
        result = bytearray()
        while length:
            index = bisect.bisect_right(self.starts, offset) - 1
            local = offset - self.starts[index]
            count = min(length, self.paths[index].stat().st_size - local)
            with self.paths[index].open('rb') as stream:
                stream.seek(local)
                data = stream.read(count)
            require(len(data) == count, 'Truncated image part')
            result.extend(data)
            offset, length = offset + count, length - count
        return bytes(result)


class Bytes:
    def __init__(self, data):
        self.data, self.size = data, len(data)

    def read(self, offset, length):
        checked_range(self.size, offset, length)
        return self.data[offset:offset + length]


class Slice:
    def __init__(self, source, offset, size):
        require(0 <= offset <= offset + size <= source.size, 'Invalid image slice')
        self.source, self.offset, self.size = source, offset, size

    def read(self, offset, length):
        checked_range(self.size, offset, length)
        return self.source.read(self.offset + offset, length)


class Sparse:
    """Index all Android sparse chunks; DONT_CARE reads as zero for offline export."""

    def __init__(self, source):
        self.source = source
        h = struct.unpack('<I4H4I', source.read(0, 28))
        magic, major, minor, header, chunk_header, block, blocks, count, _ = h
        require(magic == 0xed26ff3a and major == 1 and minor == 0,
                'Unsupported sparse image version')
        require(28 <= header <= 4096 and 12 <= chunk_header <= 4096
                and 512 <= block <= 65536 and block % 4 == 0 and 0 < count <= 2000000,
                'Invalid sparse geometry')
        self.size = block * blocks
        require(0 < self.size <= 64 * 1024**3, 'Excessive sparse expansion')
        self.entries, self.starts = [], []
        physical, logical = header, 0
        for _ in range(count):
            kind, _, nblocks, size = struct.unpack('<HHII', source.read(physical, 12))
            length = nblocks * block
            require(chunk_header <= size <= source.size - physical, 'Invalid sparse chunk size')
            data = physical + chunk_header
            if kind == 0xcac4:
                require(length == 0 and size == chunk_header + 4, 'Invalid sparse CRC chunk')
            else:
                require(length > 0 and logical + length <= self.size, 'Invalid sparse chunk range')
                expected = {0xcac1: length, 0xcac2: 4, 0xcac3: 0}.get(kind)
                require(expected is not None and size == chunk_header + expected,
                        'Unknown or malformed sparse chunk')
                self.starts.append(logical)
                self.entries.append((logical, length, kind, data))
                logical += length
            physical += size
        require(logical == self.size and physical == source.size, 'Incomplete sparse image')

    def read(self, offset, length):
        checked_range(self.size, offset, length)
        result = bytearray()
        while length:
            index = bisect.bisect_right(self.starts, offset) - 1
            start, size, kind, data = self.entries[index]
            count = min(length, start + size - offset)
            if kind == 0xcac1:
                value = self.source.read(data + offset - start, count)
            elif kind == 0xcac2:
                fill = self.source.read(data, 4)
                delta = (offset - start) % 4
                value = (fill * ((count + delta + 3) // 4))[delta:delta + count]
            else:
                value = bytes(count)
            result.extend(value)
            offset, length = offset + count, length - count
        return bytes(result)


def image_reader(source):
    return Sparse(source) if source.read(0, 4) == b'\x3a\xff\x26\xed' else source


class Logical:
    def __init__(self, source, extents):
        self.source, self.extents = source, extents
        self.size = sum(e['bytes'] for e in extents)
        self.starts = [e['logical_offset'] for e in extents]

    def read(self, offset, length):
        checked_range(self.size, offset, length)
        result = bytearray()
        while length:
            entry = self.extents[bisect.bisect_right(self.starts, offset) - 1]
            delta = offset - entry['logical_offset']
            count = min(length, entry['bytes'] - delta)
            result.extend(self.source.read(entry['super_offset'] + delta, count)
                          if entry['type'] == 'linear' else bytes(count))
            offset, length = offset + count, length - count
        return bytes(result)


def lp_metadata(source, slot=0):
    """Read a primary metadata slot, preserving geometry and empty partition entries."""
    geo = source.read(4096, 52)
    magic, size = struct.unpack_from('<II', geo)
    metadata_max, slots, block = struct.unpack_from('<III', geo, 40)
    require(magic == 0x616c4467 and size == 52 and 128 <= metadata_max <= 16 * 1024**2
            and 1 <= slots <= 8 and block >= 512 and block % 512 == 0,
            'Unsupported liblp geometry')
    require(0 <= slot < slots, 'Invalid liblp metadata slot')
    base = 12288 + slot * metadata_max
    header = source.read(base, 128)
    magic, major, minor, header_size = struct.unpack_from('<IHHI', header)
    table_size = struct.unpack_from('<I', header, 44)[0]
    require(magic == 0x414c5030 and major == 10 and minor <= 2
            and 128 <= header_size <= 4096 and header_size + table_size <= metadata_max,
            'Unsupported liblp metadata header')
    tables = source.read(base + header_size, table_size)
    descriptors = []
    for offset, minimum in ((80, 52), (92, 24), (104, 48), (116, 64)):
        start, count, stride = struct.unpack_from('<III', header, offset)
        require(stride >= minimum and count <= 10000 and start + count * stride <= len(tables),
                'Out-of-bounds liblp table')
        descriptors.append([tables[start + i * stride:start + (i + 1) * stride]
                            for i in range(count)])
    partitions, extents, groups, devices = descriptors
    require(len(devices) == 1, 'Only a single physical super device is supported')
    first_sector = struct.unpack_from('<Q', devices[0])[0]
    device_size = struct.unpack_from('<Q', devices[0], 16)[0]
    require(0 < device_size <= source.size and first_sector * 512 >= 12288 + metadata_max * slots * 2,
            'Invalid liblp block device range')
    result, used, physical_ranges = [], set(), []
    for p in partitions:
        name = p[:36].split(b'\0', 1)[0].decode('ascii')
        require(re.fullmatch(r'[A-Za-z0-9_]{1,36}', name) and name not in used,
                'Invalid or duplicate logical partition name')
        used.add(name)
        attributes, first, count, group = struct.unpack_from('<IIII', p, 36)
        require(first + count <= len(extents) and group < len(groups), 'Invalid liblp extent reference')
        mappings, total = [], 0
        for e in extents[first:first + count]:
            sectors, kind, physical, device = struct.unpack_from('<QIQI', e)
            length = sectors * 512
            require(length > 0 and kind in (0, 1) and device == 0, 'Unsupported liblp extent')
            if kind == 0:
                require(first_sector <= physical and physical * 512 + length <= device_size,
                        'Logical extent outside super data area')
                physical_ranges.append((physical * 512, physical * 512 + length))
            mappings.append({'logical_offset': total, 'bytes': length,
                             'type': 'linear' if kind == 0 else 'zero',
                             'super_offset': physical * 512 if kind == 0 else None})
            total += length
        result.append({'name': name, 'bytes': total, 'attributes': attributes,
                       'group': groups[group][:36].split(b'\0', 1)[0].decode('ascii'),
                       'extents': mappings, 'status': 'nonempty' if total else 'empty-no-image'})
    physical_ranges.sort()
    require(all(a[1] <= b[0] for a, b in zip(physical_ranges, physical_ranges[1:])),
            'Overlapping logical extents')
    return {'metadata_slot': slot, 'metadata_slots': slots, 'metadata_max_bytes': metadata_max,
            'logical_block_bytes': block, 'partitions': result,
            'other_metadata_slots': 'NOT_ANALYZED', 'checksums': 'NOT_RECOMPUTED'}


class Ext4:
    """Extent-backed ext4 reader. No journal replay, mount, chmod or host symlinks."""

    def __init__(self, source):
        self.source = source
        s = source.read(1024, 1024)
        require(struct.unpack_from('<H', s, 56)[0] == 0xef53, 'Expected ext4 filesystem')
        log_block = struct.unpack_from('<I', s, 24)[0]
        require(log_block <= 6, 'Invalid ext4 block size')
        self.block = 1024 << log_block
        self.ipg = struct.unpack_from('<I', s, 40)[0]
        self.inodes = struct.unpack_from('<I', s)[0]
        self.inode_size = struct.unpack_from('<H', s, 88)[0]
        incompat = struct.unpack_from('<I', s, 96)[0]
        self.desc_size = max(32, struct.unpack_from('<H', s, 254)[0])
        self.blocks = struct.unpack_from('<I', s, 4)[0]
        if incompat & 0x80:
            self.blocks |= struct.unpack_from('<I', s, 336)[0] << 32
        require(self.blocks * self.block <= source.size and self.ipg > 0 and self.inodes > 0
                and 128 <= self.inode_size <= self.block and 32 <= self.desc_size <= self.block,
                'Invalid ext4 geometry')
        # meta_bg, EA-inode, inline-data and encryption require a different reader.
        require(not incompat & (0x10 | 0x400 | 0x8000 | 0x10000), 'Unsupported ext4 feature')
        self.size = self.blocks * self.block

    def read(self, offset, size):
        checked_range(self.size, offset, size)
        return self.source.read(offset, size)

    def inode(self, number):
        require(1 <= number <= self.inodes, 'Invalid ext4 inode number')
        group, index = divmod(number - 1, self.ipg)
        d = self.read(max(2048, self.block) + group * self.desc_size, self.desc_size)
        table = struct.unpack_from('<I', d, 8)[0]
        if self.desc_size >= 64:
            table |= struct.unpack_from('<I', d, 40)[0] << 32
        raw = self.read(table * self.block + index * self.inode_size, self.inode_size)
        mode, uid = struct.unpack_from('<HH', raw)
        gid = struct.unpack_from('<H', raw, 24)[0]
        uid |= struct.unpack_from('<H', raw, 120)[0] << 16
        gid |= struct.unpack_from('<H', raw, 122)[0] << 16
        size = struct.unpack_from('<I', raw, 4)[0] | struct.unpack_from('<I', raw, 108)[0] << 32
        return {'inode': number, 'mode': mode, 'uid': uid, 'gid': gid, 'bytes': size,
                'links': struct.unpack_from('<H', raw, 26)[0],
                'mtime': struct.unpack_from('<I', raw, 16)[0],
                'flags': struct.unpack_from('<I', raw, 32)[0], '_raw': raw}

    def extents(self, data, expected_depth=None, visited=None):
        magic, count, maximum, depth = struct.unpack_from('<4H', data)
        require(magic == 0xf30a and count <= maximum and 12 + count * 12 <= len(data)
                and depth <= 5 and (expected_depth is None or depth == expected_depth),
                'Invalid ext4 extent tree')
        visited = set() if visited is None else visited
        result = []
        for offset in range(12, 12 + count * 12, 12):
            if depth:
                _, low, high, _ = struct.unpack_from('<IIHH', data, offset)
                physical = (low | high << 32) * self.block
                require(physical not in visited, 'Cyclic ext4 extent tree')
                visited.add(physical)
                result.extend(self.extents(self.read(physical, self.block), depth - 1, visited))
            else:
                logical, length, high, low = struct.unpack_from('<IHHI', data, offset)
                unwritten = length > 32768
                length = (length - 32768 if unwritten else length) * self.block
                physical = (low | high << 32) * self.block
                require(length > 0 and physical + length <= self.size, 'Invalid ext4 extent range')
                result.append((logical * self.block, length, None if unwritten else physical))
        require(all(a[0] + a[1] <= b[0] for a, b in zip(result, result[1:])),
                'Unordered or overlapping ext4 extents')
        return result

    def file(self, entry):
        return InodeFile(self, entry)

    def directory(self, entry):
        require(stat.S_ISDIR(entry['mode']) and entry['bytes'] <= MAX_READ, 'Invalid ext4 directory')
        data = self.file(entry).read()
        offset, names, result = 0, set(), []
        while offset < len(data):
            require(offset + 8 <= len(data), 'Truncated ext4 directory')
            inode, length, size, _ = struct.unpack_from('<IHBB', data, offset)
            require(length >= 8 and length % 4 == 0 and offset + length <= len(data)
                    and size <= length - 8, 'Invalid ext4 directory record')
            if inode:
                name = data[offset + 8:offset + 8 + size].decode('utf-8')
                if name not in ('.', '..'):
                    checked_path(name)
                    require('/' not in name and name not in names, 'Duplicate ext4 directory entry')
                    names.add(name)
                    result.append((name, inode))
            offset += length
        return sorted(result)

    def walk(self):
        pending, directories, count = [('', 2)], set(), 0
        while pending:
            path, number = pending.pop()
            count += 1
            require(count <= 200000 and path.count('/') < 64, 'Excessive ext4 directory tree')
            entry = self.inode(number)
            entry['path'] = path
            if stat.S_ISDIR(entry['mode']):
                require(number not in directories, 'Cyclic ext4 directory graph')
                directories.add(number)
                pending.extend((f'{path}/{name}'.lstrip('/'), inode)
                               for name, inode in reversed(self.directory(entry)))
            yield entry


class InodeFile(io.RawIOBase):
    def __init__(self, fs, entry):
        self.fs, self.entry, self.position = fs, entry, 0
        self.inline = None
        size, flags, raw = entry['bytes'], entry['flags'], entry['_raw']
        require(size <= fs.size, 'Excessive ext4 file size')
        if stat.S_ISLNK(entry['mode']) and size <= 60 and not flags & 0x80000:
            self.inline = raw[40:40 + size]
            self.extents = []
        elif size:
            require(flags & 0x80000 and not flags & 0x10000000,
                    'Non-extent or inline-data ext4 inode needs review')
            self.extents = fs.extents(raw[40:100])
        else:
            self.extents = []

    def read(self, size=-1):
        size = self.entry['bytes'] - self.position if size < 0 else min(size, self.entry['bytes'] - self.position)
        require(size <= MAX_READ, 'Excessive ext4 buffered read')
        result = bytearray(size)
        if self.inline is not None:
            result[:] = self.inline[self.position:self.position + size]
        else:
            end = self.position + size
            for start, length, physical in self.extents:
                left, right = max(self.position, start), min(end, start + length)
                if left < right and physical is not None:
                    result[left - self.position:right - self.position] = self.fs.read(physical + left - start, right - left)
        self.position += size
        return bytes(result)


def elf_info(source):
    """ELF ABI, interpreter and DT_NEEDED/SONAME/RPATH, without executing a loader."""
    head = source.read(0, min(source.size, 64))
    if head[:4] != b'\x7fELF':
        return None
    require(len(head) >= 52 and head[4] in (1, 2) and head[5:7] == b'\x01\x01', 'Unsupported ELF encoding')
    bits = 64 if head[4] == 2 else 32
    machine = struct.unpack_from('<H', head, 18)[0]
    if bits == 64:
        phoff = struct.unpack_from('<Q', head, 32)[0]
        stride, count = struct.unpack_from('<HH', head, 54)
        minimum = 56
    else:
        phoff = struct.unpack_from('<I', head, 28)[0]
        stride, count = struct.unpack_from('<HH', head, 42)
        minimum = 32
    require(count <= 1024 and stride >= minimum and phoff + stride * count <= source.size,
            'Invalid ELF program table')
    loads, dynamic, interpreter = [], None, None
    for index in range(count):
        ph = source.read(phoff + index * stride, minimum)
        if bits == 64:
            kind, _, offset, virtual, _, length, _, _ = struct.unpack('<II6Q', ph)
        else:
            kind, offset, virtual, _, length, _, _, _ = struct.unpack('<8I', ph)
        require(offset + length <= source.size, 'ELF segment outside file')
        if kind == 1:
            loads.append((virtual, length, offset))
        elif kind == 2:
            dynamic = (offset, length)
        elif kind == 3:
            require(length <= 4096, 'Excessive ELF interpreter')
            interpreter = source.read(offset, length).rstrip(b'\0').decode('utf-8')
    result = {'bits': bits, 'machine': machine, 'interpreter': interpreter,
              'needed': [], 'soname': None, 'rpath': None, 'runpath': None}
    if dynamic:
        offset, length = dynamic
        stride = 16 if bits == 64 else 8
        require(length <= 1024 * 1024 and length % stride == 0, 'Invalid ELF dynamic table')
        tags, terminated = [], False
        for pos in range(offset, offset + length, stride):
            tag, value = struct.unpack('<qQ' if bits == 64 else '<iI', source.read(pos, stride))
            if tag == 0:
                terminated = True
                break
            tags.append((tag, value))
        require(terminated, 'Unterminated ELF dynamic table')
        strings = [v for t, v in tags if t == 5]
        sizes = [v for t, v in tags if t == 10]
        if any(t in (1, 14, 15, 29) for t, _ in tags):
            require(len(strings) == len(sizes) == 1 and sizes[0] <= MAX_READ, 'Invalid ELF string table')
            matches = [(o + strings[0] - v, sizes[0]) for v, n, o in loads
                       if v <= strings[0] and strings[0] + sizes[0] <= v + n]
            require(len(matches) == 1, 'Unmapped ELF dynamic string table')
            raw = source.read(*matches[0])
            for tag, value in tags:
                if tag not in (1, 14, 15, 29):
                    continue
                end = raw.find(b'\0', value)
                require(0 <= value <= end < len(raw) and end - value <= 4096, 'Invalid ELF dynamic string')
                text = raw[value:end].decode('utf-8')
                if tag == 1:
                    result['needed'].append(text)
                else:
                    result[{14: 'soname', 15: 'rpath', 29: 'runpath'}[tag]] = text
    # Dynamic symbol sets support later stock/Recovery ABI comparisons. Version
    # tables are intentionally not interpreted as compatibility proof.
    if bits == 64:
        shoff = struct.unpack_from('<Q', head, 40)[0]
        shstride, shcount = struct.unpack_from('<HH', head, 58)
        shminimum = 64
    else:
        shoff = struct.unpack_from('<I', head, 32)[0]
        shstride, shcount = struct.unpack_from('<HH', head, 46)
        shminimum = 40
    result.update(imports={'strong': [], 'weak': []}, exports=[], symbol_versions='NOT_ANALYZED',
                  dynamic_symbols='no-section-table' if not shcount else 'no-dynsym-section')
    if shcount:
        require(shstride >= shminimum and shcount <= 65535
                and shoff + shstride * shcount <= source.size, 'Invalid ELF section table')
        sections = []
        for index in range(shcount):
            raw = source.read(shoff + index * shstride, shminimum)
            if bits == 64:
                _, kind, _, _, offset, size, link, _, _, stride = struct.unpack('<II4QII2Q', raw)
            else:
                _, kind, _, _, offset, size, link, _, _, stride = struct.unpack('<10I', raw)
            sections.append((kind, offset, size, link, stride))
        for kind, offset, size, link, stride in sections:
            if kind != 11:
                continue
            result['dynamic_symbols'] = 'parsed'
            require(stride == (24 if bits == 64 else 16) and size <= 16 * 1024**2
                    and size % stride == 0 and link < shcount, 'Invalid ELF dynsym')
            _, string_offset, string_size, _, _ = sections[link]
            strings = source.read(string_offset, string_size)
            symbols = source.read(offset, size)
            for pos in range(0, size, stride):
                if bits == 64:
                    name, info, visibility, section = struct.unpack_from('<IBBH', symbols, pos)
                else:
                    name, _, _, info, visibility, section = struct.unpack_from('<IIIBBH', symbols, pos)
                binding = info >> 4
                if not name or binding not in (1, 2):
                    continue
                end = strings.find(b'\0', name)
                require(0 < name <= end < len(strings), 'Invalid ELF symbol name')
                symbol = strings[name:end].decode('utf-8')
                if section == 0:
                    result['imports']['weak' if binding == 2 else 'strong'].append(symbol)
                elif (visibility & 3) in (0, 3):
                    result['exports'].append(symbol)
        result['exports'] = sorted(set(result['exports']))
        for kind in ('strong', 'weak'):
            result['imports'][kind] = sorted(set(result['imports'][kind]))
    return result
