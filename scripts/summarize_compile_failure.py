#!/usr/bin/env python3
# Requirements: classify a failed compile without exporting private log text.
# Ambiguity: unknown diagnostics remain unclassified; no guessed source fixes.
# Research: public locations and dependencies must exist in pinned upstream Git.
# Optimization: inspect bounded log fragments and at most 64 candidate files.
# Risks: private overlay contents, paths, identifiers or credentials in errors.
# Validation: fixed categories and Git-confirmed public metadata; synthetic tests.
"""Return restricted compiler diagnostics, never compiler output or source text."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

from source_inputs import load_lock, relative_path

RULES = {
    'UNDEFINED_MODULE': r'depends on undefined module|missing dependencies:',
    'MISSING_SOURCE_INPUT': r'source path .*does not exist|missing and no known rule to make it',
    'DUPLICATE_MODULE': r'module .*already defined|duplicate module',
    'UNKNOWN_BUILD_PROPERTY': r'unrecognized property|unrecognized module type',
    'SOONG_BOOTSTRAP_FAILURE': r'soong bootstrap failed|bootstrap failed',
    'DISK_EXHAUSTED': r'no space left on device',
    'MEMORY_EXHAUSTED': r'out of memory|cannot allocate memory|fatal error: runtime: out of memory',
    'HOST_TOOL_EXECUTION_FAILURE': r'cannot execute binary file|exec format error|command not found|error while loading shared libraries',
    'JAVA_RUNTIME_FAILURE': r'UnsupportedClassVersionError|NoClassDefFoundError|java.lang.OutOfMemoryError',
    'GO_RUNTIME_FAILURE': r'panic:|fatal error: runtime:',
    'NATIVE_COMPILER_FAILURE': r'clang: error:|ld.lld: error:|undefined reference to',
}
LOCATION = re.compile(r'(?<![\w/.-])([A-Za-z0-9_./+-]+):([0-9]{1,7})(?::[0-9]+)?:')
DEPENDENCY = re.compile(r'(?:undefined module|missing dependencies:)\s*"([A-Za-z0-9_.+-]{1,128})"')


def public_file(source, name, projects, excluded):
    """Use pinned Git blobs rather than private overlays or arbitrary log paths."""
    try:
        relative_path(name)
        if name in excluded or Path(name).suffix not in {'.bp', '.mk', '.go', '.c', '.cc', '.cpp', '.h', '.py', '.sh', '.S', '.s'}:
            return None
        candidates = sorted(projects, key=lambda p: len(p.get('path', p.get('name', ''))), reverse=True)
        for project in candidates:
            prefix = project.get('path', project.get('name', ''))
            relative_path(prefix)
            if not name.startswith(prefix + '/'):
                continue
            suffix = name[len(prefix) + 1:]
            relative_path(suffix)
            revision = project.get('revision', '')
            if not re.fullmatch(r'[0-9a-f]{40}', revision):
                return None
            root = Path(source) / prefix
            head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                           stderr=subprocess.DEVNULL, timeout=10).decode().strip()
            if head != revision:
                return None
            size = subprocess.check_output(['git', '-C', str(root), 'cat-file', '-s', revision + ':' + suffix],
                                           stderr=subprocess.DEVNULL, timeout=10)
            if int(size) > 2 * 1024**2:
                return None
            data = subprocess.check_output(['git', '-C', str(root), 'show', revision + ':' + suffix],
                                           stderr=subprocess.DEVNULL, timeout=10)
            if len(data) > 2 * 1024**2 or b'\0' in data:
                return None
            return data.decode('utf-8')
    except (ValueError, OSError, UnicodeError, subprocess.SubprocessError):
        return None
    return None


def summarize(text, manifest, source, excluded=()):
    categories = [name for name, rule in RULES.items() if re.search(rule, text, re.I)]
    projects = ET.fromstring(manifest).findall('project')
    locations, dependencies, cache = [], set(), {}
    for line in text.splitlines():
        for match in LOCATION.finditer(line):
            name, number = match.groups()
            if name not in cache:
                if len(cache) >= 64:
                    continue
                cache[name] = public_file(source, name, projects, excluded)
                if cache[name] is not None:
                    locations.append({'path': name, 'line': int(number)})
            public = cache[name]
            if public is None:
                continue
            for dependency in DEPENDENCY.findall(line):
                # Only a literal present in this exact public Git blob is eligible.
                if json.dumps(dependency) in public:
                    dependencies.add(dependency)
    return {'categories': categories or ['UNCLASSIFIED_COMPILE_FAILURE'],
            'public_locations': locations, 'public_dependencies': sorted(dependencies)[:128]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.log.open('rb') as stream:
        first = stream.read(2 * 1024**2)
        stream.seek(max(len(first), args.log.stat().st_size - 2 * 1024**2))
        text = (first + b'\n' + stream.read(2 * 1024**2)).decode('utf-8', errors='replace')
    excluded = {entry['destination'].removeprefix('overlay/') for entry in load_lock()['files']}
    result = summarize(text, args.manifest.read_bytes(), args.source, excluded)
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
