#!/usr/bin/env python3
# Requirements: classify a failed compile without exporting private log text.
# Ambiguity: unknown diagnostics remain unclassified; no guessed source fixes.
# Research: public module assignments and literal Recovery relink file names.
# Optimization: bounded log fragments, 64 locations and a 45-second literal search.
# Risks: private overlay contents, paths, identifiers or credentials in errors.
# Validation: fixed categories and Git-confirmed public metadata; synthetic tests.
"""Return restricted compiler diagnostics, never compiler output or source text."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

from source_inputs import load_lock, relative_path

RULES = {
    'UNDEFINED_MODULE': r'depends on undefined module|missing dependencies:',
    'MISSING_REQUIRED_MODULE': r'Missing required dependencies:|requires non-existent (?:TARGET|HOST|HOST_CROSS) module:',
    'INVALID_APEX_AVAILABLE': r'apex_available:\s*"[^"\r\n]+"\s+is not a valid module name',
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
DEPENDENCY = re.compile(r'(?:undefined module|missing dependencies:)\s*":?([A-Za-z0-9_.@+-]{1,128})"')
APEX_DEPENDENCY = re.compile(r'apex_available:\s*"([A-Za-z0-9_.@+-]{1,128})"\s+is not a valid module name\b')
MAKE_REQUIRED = re.compile(
    r'^(?:TARGET|HOST|HOST_CROSS) module [A-Za-z0-9_.@+-]{1,128}(?::(?:32|64))? '
    r'requires non-existent (?:TARGET|HOST|HOST_CROSS) module: '
    r'([A-Za-z0-9_.@+-]{1,128})(?::(?:32|64))?\s*$')
HOST_CROSS_REQUIRED = re.compile(
    r'^HOST_CROSS module [A-Za-z0-9_.@+-]{1,128}(?::(?:32|64))? '
    r'requires non-existent HOST_CROSS module: '
    r'host_cross_([A-Za-z0-9_.@+-]{1,117})(?::(?:32|64))?\s*$')
NAME = re.compile(r'[A-Za-z0-9_.@+-]{1,128}\Z')
BUILDER_ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATCH = 'builder-public/patches/recovery-required-modules.patch'


def public_builder_patch(revision):
    """Read one public patch at the checkout's GitHub commit, never its worktree."""
    if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{40}', revision):
        return None
    try:
        def git(*args):
            return subprocess.check_output(['git', '-C', str(BUILDER_ROOT), *args],
                                           stderr=subprocess.DEVNULL, timeout=2)
        origin = git('remote', 'get-url', 'origin').decode().strip().removesuffix('.git')
        if origin != 'https://github.com/Grinch27/twrp_builder':
            return None
        if git('rev-parse', 'HEAD').decode().strip() != revision:
            return None
        target = revision + ':patches/recovery-required-modules.patch'
        if int(git('cat-file', '-s', target)) > 65536:
            return None
        data = git('show', target)
        if len(data) > 65536 or b'\0' in data:
            return None
        return data.decode('utf-8')
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        return None


def public_file(source, name, projects, excluded, timeout=10, builder_commit=None):
    """Use pinned Git blobs rather than private overlays or arbitrary log paths."""
    try:
        relative_path(name)
        if name == BUILDER_PATCH and name not in excluded:
            return public_builder_patch(builder_commit or os.environ.get('GITHUB_SHA'))
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
                                           stderr=subprocess.DEVNULL, timeout=timeout).decode().strip()
            if head != revision:
                return None
            size = subprocess.check_output(['git', '-C', str(root), 'cat-file', '-s', revision + ':' + suffix],
                                           stderr=subprocess.DEVNULL, timeout=timeout)
            if int(size) > 2 * 1024**2:
                return None
            data = subprocess.check_output(['git', '-C', str(root), 'show', revision + ':' + suffix],
                                           stderr=subprocess.DEVNULL, timeout=timeout)
            if len(data) > 2 * 1024**2 or b'\0' in data:
                return None
            return data.decode('utf-8')
    except (ValueError, OSError, UnicodeError, subprocess.SubprocessError):
        return None
    return None


def dependency_literals(name):
    """Accept only an exact quoted module name or a local :module source label."""
    if not isinstance(name, str) or not NAME.fullmatch(name):
        return ()
    return (json.dumps(name), json.dumps(':' + name))


def dependency_evidence_line(text, name, path=''):
    """Locate quoted names or bare tokens in public Make module assignments."""
    literals = dependency_literals(name)
    if not literals:
        return None
    if path == BUILDER_PATCH:
        token = re.compile(r'(?<![A-Za-z0-9_.@+-])' + re.escape(name)
                           + r'(?![A-Za-z0-9_.@+-])')
        for number, line in enumerate(text.splitlines(), 1):
            if line.startswith('+') and not line.startswith('+++') and token.search(line[1:]):
                return number
        return None
    for number, line in enumerate(text.splitlines(), 1):
        if any(literal in line for literal in literals):
            return number
    if not path.endswith('.mk'):
        return None
    assignment = re.compile(
        r'^\s*(?:LOCAL_MODULE|LOCAL_REQUIRED_MODULES|LOCAL_SHARED_LIBRARIES|'
        r'LOCAL_STATIC_LIBRARIES|LOCAL_WHOLE_STATIC_LIBRARIES|'
        r'LOCAL_HEADER_LIBRARIES|TWRP_REQUIRED_MODULES|PRODUCT_PACKAGES)\s*'
        r'(?::=|\+=|\?=|=)\s*(.*)$')
    relink_assignment = re.compile(
        r'^\s*RECOVERY_(?:BINARY_SOURCE|LIBRARY_SOURCE|VENDOR_HW_BINARY)_FILES\s*'
        r'(?::=|\+=|\?=|=)\s*(.*)$')
    pending, first = '', 0
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split('#', 1)[0].rstrip()
        if not pending:
            first = number
        pending += line[:-1] + ' ' if line.endswith('\\') else line
        if line.endswith('\\'):
            continue
        match = assignment.fullmatch(pending)
        if match and name in match[1].split():
            return first
        relink = relink_assignment.fullmatch(pending)
        if relink:
            for value in relink[1].split():
                # A literal basename is public even if no module owns that file.
                # Do not evaluate Make, expand variables or infer variant suffixes.
                if re.fullmatch(r'\$\([A-Z][A-Z0-9_]*\)/(?:[A-Za-z0-9_.+-]+/)*'
                                + re.escape(name), value):
                    return first
        pending = ''
    return None


def has_public_dependency(text, name, path=''):
    return dependency_evidence_line(text, name, path) is not None


def dependency_names(line):
    """Recognize quoted Blueprint names and Soong's bare comma-separated list."""
    result = set(DEPENDENCY.findall(line))
    result.update(APEX_DEPENDENCY.findall(line))
    missing = re.search(r'missing dependencies:\s*(.*)$', line)
    if missing:
        result.update(name.strip().removeprefix(':') for name in missing[1].split(',')[:128]
                      if NAME.fullmatch(name.strip().removeprefix(':')))
    return result


def public_dependency_sources(source, projects, candidates, excluded, locations=()):
    """Find literal proof in pinned public Git, never in worktree/default overlays."""
    pending = {name for name in candidates if NAME.fullmatch(name)}
    if not pending:
        return [], set()
    deadline = time.monotonic() + 45
    evidence, verified, seen = [], set(), set()
    public_patch = public_file(source, BUILDER_PATCH, projects, excluded)
    if public_patch is not None:
        hits = sorted(name for name in pending
                      if has_public_dependency(public_patch, name, BUILDER_PATCH))
        if hits:
            evidence.append({'path': BUILDER_PATCH,
                             'line': min(dependency_evidence_line(public_patch, name, BUILDER_PATCH)
                                         for name in hits), 'dependencies': hits})
            pending.difference_update(hits)
            verified.update(hits)
            seen.add(BUILDER_PATCH)
    # Prioritize pinned public files identified by this run's verified error locations.
    # The existing 45-second, 32-file, and exact-Git-blob evidence limits remain.
    focus = [item['path'] for item in locations if isinstance(item, dict)
             and isinstance(item.get('path'), str)]
    # Check these exact locations before scanning potentially large projects.
    for name in dict.fromkeys(focus):
        if not pending or time.monotonic() >= deadline or len(seen) >= 32:
            break
        if name in seen:
            continue
        seen.add(name)
        text = public_file(source, name, projects, excluded, timeout=2)
        if text is None:
            continue
        hits = sorted(dep for dep in pending if has_public_dependency(text, dep, name))
        if hits:
            evidence.append({'path': name,
                             'line': min(dependency_evidence_line(text, dep, name) for dep in hits),
                             'dependencies': hits})
            verified.update(hits)
            pending.difference_update(hits)
    priority = {'build/soong': 0, 'frameworks/base': 1}

    def rank(project):
        prefix = project.get('path', project.get('name', ''))
        for index, path in enumerate(focus):
            if path.startswith(prefix + '/'):
                return (0, index)
        return (1, priority.get(prefix, 2))

    ordered = sorted(projects, key=rank)
    for project in ordered:
        remaining = deadline - time.monotonic()
        if not pending or remaining <= 0 or len(seen) >= 32:
            break
        prefix = project.get('path', project.get('name', ''))
        revision = project.get('revision', '')
        try:
            relative_path(prefix)
            if not re.fullmatch(r'[0-9a-f]{40}', revision):
                continue
            root = Path(source) / prefix
            head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                           stderr=subprocess.DEVNULL,
                                           timeout=min(2, remaining)).decode().strip()
            if head != revision:
                continue
            # The broad Git search only finds files; exact proof is checked below.
            patterns = [arg for name in sorted(pending)[:128] for arg in ('-e', name)]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            result = subprocess.run(['git', '-C', str(root), 'grep', '-l', '-z', '-F',
                                     *patterns, revision, '--', '*.bp', '*.mk', '*.go'],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    timeout=min(2, remaining), check=False)
            if result.returncode not in (0, 1) or len(result.stdout) > 1024**2:
                continue
            for raw in result.stdout.decode('utf-8').split('\0'):
                remaining = deadline - time.monotonic()
                if remaining < 0.15 or not pending or len(seen) >= 32:
                    break
                if not raw.startswith(revision + ':'):
                    continue
                name = prefix + '/' + raw[len(revision) + 1:]
                if name in seen or not re.fullmatch(r'[A-Za-z0-9_./+-]+', name):
                    continue
                seen.add(name)
                text = public_file(source, name, projects, excluded,
                                   timeout=min(2, remaining / 3))
                if text is None:
                    continue
                hits = sorted(dep for dep in pending if has_public_dependency(text, dep, name))
                if hits:
                    line = min(dependency_evidence_line(text, dep, name) for dep in hits)
                    evidence.append({'path': name, 'line': line, 'dependencies': hits})
                    verified.update(hits)
                    pending.difference_update(hits)
        except (ValueError, OSError, UnicodeError, subprocess.SubprocessError):
            continue
    return evidence, verified


def summarize(text, manifest, source, excluded=()):
    categories = [name for name, rule in RULES.items() if re.search(rule, text, re.I)]
    projects = ET.fromstring(manifest).findall('project')
    locations, dependencies, candidates, cache = [], set(), set(), {}
    make_candidates, host_cross_candidates = set(), set()
    for line in text.splitlines():
        required = MAKE_REQUIRED.fullmatch(line.strip())
        if required and len(make_candidates) < 128:
            make_candidates.add(required[1])
            cross = HOST_CROSS_REQUIRED.fullmatch(line.strip())
            if cross:
                host_cross_candidates.add(cross[1])
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
            names = dependency_names(line)
            candidates.update(names)
            for dependency in names:
                # Only a literal present in this exact public Git blob is eligible.
                if has_public_dependency(public, dependency, name):
                    dependencies.add(dependency)
    checker = cache.get('build/make/core/main.mk')
    cross_prefix_verified = False
    if checker is not None and all(marker in checker for marker in
                                   ('Missing required dependencies:', 'requires non-existent')):
        candidates.update(make_candidates)
        # main.mk adds this internal prefix before resolving host-cross requirements.
        # Report only independently proven literal source names, never generated IDs.
        if '$(eval r := $(addprefix host_cross_,$(r)))' in checker:
            candidates.update(host_cross_candidates)
            cross_prefix_verified = True
    evidence, inherited = public_dependency_sources(source, projects, candidates - dependencies, excluded, locations)
    result = {'categories': categories or ['UNCLASSIFIED_COMPILE_FAILURE'],
              'public_locations': locations,
              'public_dependencies': sorted(dependencies | inherited)[:128]}
    if checker is not None and 'MISSING_REQUIRED_MODULE' in categories:
        result['required_candidates'] = len(make_candidates)
        verified_names = dependencies | inherited
        verified_internal = {'host_cross_' + name for name in host_cross_candidates & verified_names
                             if cross_prefix_verified}
        result['unverified_required_candidates'] = len(make_candidates - verified_names - verified_internal)
        result['host_cross_required_candidates'] = len(host_cross_candidates)
    if evidence:
        result['public_dependency_sources'] = evidence
    return result


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
