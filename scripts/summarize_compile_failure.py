#!/usr/bin/env python3
# Requirements: classify a failed compile without exporting private log text.
# Ambiguity: unknown diagnostics remain unclassified; no guessed source fixes.
# Research: pinned public name constructors and exact module/relink literals.
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
    'LINK_TYPE_INCOMPATIBLE': r'\bcan not link against [A-Za-z0-9_.@+-]{1,128} \(',
    'LINK_VARIANT_MISSING': r'\bmissing [A-Za-z0-9_.@+-]{1,128} \([A-Z_]{2,32} (?:android|linux|darwin|windows)-',
    'NATIVE_COMPILER_FAILURE': r'clang: error:|ld.lld: error:|undefined reference to',
}
LOCATION = re.compile(r'(?<![\w/.-])([A-Za-z0-9_./+-]+):([0-9]{1,7})(?::[0-9]+)?:')
DEPENDENCY = re.compile(r'(?:undefined module|missing dependencies:)\s*":?([A-Za-z0-9_.@+-]{1,128})"')
APEX_DEPENDENCY = re.compile(r'apex_available:\s*"([A-Za-z0-9_.@+-]{1,128})"\s+is not a valid module name\b')
# The pinned Android 12.1 Make checker emits these messages before main.mk
# stops with "exiting from previous errors". Never export a captured name
# unless its literal also exists in an independently pinned public Git blob.
LINK_VARIANT = re.compile(
    r'\bmissing ([A-Za-z0-9_.@+-]{1,128}) \([A-Z_]{2,32} '
    r'(?:android|linux|darwin|windows)-[A-Za-z0-9_.+-]+\)')
LINK_INCOMPATIBLE = re.compile(
    r'\bcan not link against ([A-Za-z0-9_.@+-]{1,128}) \([^) \r\n]{1,64}\)')
MAKE_REQUIRED = re.compile(
    r'^(?:TARGET|HOST|HOST_CROSS) module [A-Za-z0-9_.@+-]{1,128}(?::(?:32|64))? '
    r'requires non-existent (?:TARGET|HOST|HOST_CROSS) module: '
    r'([A-Za-z0-9_.@+-]{1,128})(?::(?:32|64))?\s*$')
HOST_CROSS_REQUIRED = re.compile(
    r'^HOST_CROSS module [A-Za-z0-9_.@+-]{1,128}(?::(?:32|64))? '
    r'requires non-existent HOST_CROSS module: '
    r'host_cross_([A-Za-z0-9_.@+-]{1,117})(?::(?:32|64))?\s*$')
NAME = re.compile(r'[A-Za-z0-9_.@+-]{1,128}\Z')
LINK_CLASSES = {'SHARED_LIBRARIES', 'STATIC_LIBRARIES', 'EXECUTABLES', 'ETC',
                'HEADER_LIBRARIES', 'JAVA_LIBRARIES', 'APPS', 'NATIVE_TESTS', 'PHONY_PACKAGE'}
LINK_ARCHES = {'arm', 'arm64', 'x86', 'x86_64'}
LINK_CONTEXT = re.compile(
    r'([A-Za-z0-9_.@+-]{1,128}) \(([A-Z_]{2,32}) android-([A-Za-z0-9_]+)\) '
    r'missing ([A-Za-z0-9_.@+-]{1,128}) \(([A-Z_]{2,32}) android-([A-Za-z0-9_]+)\)')
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
        r'^\s*(?:LOCAL_MODULE|LOCAL_PACKAGE_NAME|LOCAL_JAVA_LIBRARIES|LOCAL_STATIC_JAVA_LIBRARIES|'
        r'LOCAL_JNI_SHARED_LIBRARIES|'
        r'LOCAL_REQUIRED_MODULES|LOCAL_SHARED_LIBRARIES|'
        r'LOCAL_STATIC_LIBRARIES|LOCAL_WHOLE_STATIC_LIBRARIES|'
        r'LOCAL_HEADER_LIBRARIES|TWRP_REQUIRED_MODULES|TARGET_RECOVERY_DEVICE_MODULES|PRODUCT_PACKAGES)\s*'
        r'(?::=|\+=|\?=|=)\s*(.*)$')
    relink_assignment = re.compile(
        r'^\s*RECOVERY_(BINARY_SOURCE|LIBRARY_SOURCE|VENDOR_HW_BINARY)_FILES\s*'
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
            for value in relink[2].split():
                # A literal basename is public even if no module owns that file.
                # Do not evaluate Make, expand variables or infer variant suffixes.
                suffix = r'(?:\.so)?' if relink[1] == 'LIBRARY_SOURCE' else ''
                if re.fullmatch(r'\$\([A-Z][A-Z0-9_]*\)/(?:[A-Za-z0-9_.+-]+/)*'
                                + re.escape(name) + suffix, value):
                    return first
        pending = ''
    return None


def has_public_dependency(text, name, path=''):
    return dependency_evidence_line(text, name, path) is not None


def public_variant_suffixes(source, projects, excluded):
    """Return only fixed suffixes independently read from the pinned Soong blob."""
    text = public_file(source, 'build/soong/cc/androidmk.go', projects, excluded)
    if text is None:
        return set()
    constants = {'nativeBridgeSuffix': '.native_bridge', 'productSuffix': '.product',
                 'VendorSuffix': '.vendor', 'ramdiskSuffix': '.ramdisk',
                 'VendorRamdiskSuffix': '.vendor_ramdisk', 'recoverySuffix': '.recovery',
                 'sdkSuffix': '.sdk'}
    suffixes = {suffix for name, suffix in constants.items()
                if re.search(r'\b' + name + r'\s*=\s*"' + re.escape(suffix) + '"', text)}
    # Bootstrap and CFI use literal SubName assignments rather than the table.
    suffixes.update(re.findall(r'\bentries\.SubName\s*(?:=|\+=)\s*"(\.[A-Za-z0-9_]{1,32})"', text))
    return suffixes


def public_recovery_suffix(source, projects, excluded):
    return '.recovery' in public_variant_suffixes(source, projects, excluded)


def public_generated_families(source, projects, excluded):
    """Verify public name constructors without exporting version or device values."""
    families = set()
    vndk = public_file(source, 'build/soong/cc/vndk_prebuilt.go', projects, excluded)
    if (vndk is not None and re.search(r'\bvndkSuffix\s*=\s*"\.vndk\."', vndk)
            and re.search(r'\bbinder32Suffix\s*=\s*"\.binder32"', vndk)
            and all(marker in vndk for marker in ('return name + p.NameSuffix()',
                'suffix := p.version()', 'suffix += "." + p.arch()', 'return vndkSuffix + suffix'))):
        families.add('vndk')
    snapshot = public_file(source, 'build/soong/cc/snapshot_prebuilt.go', projects, excluded)
    if (snapshot is not None and all(marker in snapshot for marker in (
            'return name + p.NameSuffix()', 'return moduleSuffix + versionSuffix',
            'return getSnapshotNameSuffix(p.moduleSuffix(), p.version(), p.arch())',
            'p.baseProperties.ModuleSuffix = image.moduleNameSuffix() + moduleSuffix'))):
        suffixes = public_variant_suffixes(source, projects, excluded)
        if '.vendor' in suffixes:
            families.add('vendor_snapshot')
        if '.recovery' in suffixes:
            families.add('recovery_snapshot')
        for kind in ('header', 'shared', 'static', 'binary', 'object'):
            if not re.search(r'\bsnapshot' + kind.title() + r'Suffix\s*=\s*"_' + kind + r'\."', snapshot):
                families.discard('vendor_snapshot')
                families.discard('recovery_snapshot')
    prebuilt = public_file(source, 'build/soong/android/prebuilt.go', projects, excluded)
    if prebuilt is not None and 'return "prebuilt_" + name' in prebuilt:
        families.add('prebuilt')
    make = public_file(source, 'build/make/core/base_rules.mk', projects, excluded)
    if make is not None and 'my_register_name := host_cross_$(LOCAL_MODULE)' in make:
        families.add('host_cross')
    return families


def generated_link_base(name, families):
    """Decode only the checked public constructors; return no private suffix data."""
    tail = r'[0-9]{1,3}(?:\.(?:arm64|arm|x86_64|x86|mips64|mips))?'
    match = re.fullmatch(r'([A-Za-z0-9_.@+-]{1,100})\.vndk\.' + tail + r'(?:\.binder32)?', name)
    if match and 'vndk' in families:
        return match[1], 'vndk'
    match = re.fullmatch(r'([A-Za-z0-9_.@+-]{1,100})\.(vendor|recovery)_(?:header|shared|static|binary|object)\.' + tail, name)
    if match and match[2] + '_snapshot' in families:
        return match[1], match[2] + '_snapshot'
    for family, prefix in (('prebuilt', 'prebuilt_'), ('host_cross', 'host_cross_')):
        if family in families and name.startswith(prefix) and NAME.fullmatch(name[len(prefix):]):
            return name[len(prefix):], family
    return None


def dependency_names(line):
    """Recognize quoted Blueprint names and Soong's bare comma-separated list."""
    result = set(DEPENDENCY.findall(line))
    result.update(APEX_DEPENDENCY.findall(line))
    missing = re.search(r'missing dependencies:\s*(.*)$', line)
    if missing:
        result.update(name.strip().removeprefix(':') for name in missing[1].split(',')[:128]
                      if NAME.fullmatch(name.strip().removeprefix(':')))
    return result


def public_dependency_sources(source, projects, candidates, excluded, locations=(), module_index=None):
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
    focus += [project.get('path') + '/device.mk' for project in projects
              if project.get('path') == 'device/xiaomi/selene']
    # Catalog locations are untrusted hints; public_file and literal proof below
    # still independently enforce pinned revisions and private-overlay exclusions.
    if isinstance(module_index, dict):
        indexed = []
        for dependency in sorted(pending)[:128]:
            paths = module_index.get(dependency, [])
            if isinstance(paths, list):
                indexed.extend(path for path in paths[:8] if isinstance(path, str)
                               and re.fullmatch(r'[A-Za-z0-9_./+-]{1,512}', path))
        focus = indexed + focus
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
            # Select full references before spending the file budget on Git proof.
            # Substrings such as libfoo_suffix must not hide a later libfoo literal.
            patterns = []
            for dependency in sorted(pending)[:128]:
                escaped = re.escape(dependency)
                references = ('"(:)?' + escaped + '"',
                              '(^|[[:space:]])' + escaped + '([[:space:]]|$)',
                              '/' + escaped + r'(\.so)?([[:space:]]|$)')
                patterns.extend(arg for reference in references for arg in ('-e', reference))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            result = subprocess.run(['git', '-C', str(root), 'grep', '-l', '-z', '-E',
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


def summarize(text, manifest, source, excluded=(), module_index=None):
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
    # Require the actual pinned Make link checker, not a log path or a
    # generic "missing" message alone. Public names still need exact Git proof.
    link_categories = {'LINK_TYPE_INCOMPATIBLE', 'LINK_VARIANT_MISSING'}
    link_candidates, recovery_bases, variant_names, generated_names = set(), set(), {}, {}
    link_contexts, parent_names = [], set()
    if checker is not None and all(marker in checker for marker in
                                   ('define link-type-missing', 'define link-type-error',
                                    '$(error exiting from previous errors)')):
        link_candidates.update(LINK_VARIANT.findall(text)[:128])
        link_candidates.update(LINK_INCOMPATIBLE.findall(text)[:128])
        link_candidates = set(sorted(link_candidates)[:128])
        candidates.update(link_candidates)
        for line in text.splitlines():
            match = LINK_CONTEXT.search(line)
            if match is None or len(link_contexts) >= 32:
                continue
            parent, parent_class, parent_arch, dependency, dep_class, dep_arch = match.groups()
            if (parent_class not in LINK_CLASSES or dep_class not in LINK_CLASSES
                    or parent_arch not in LINK_ARCHES or dep_arch not in LINK_ARCHES):
                continue
            context = {'parent_class': parent_class, 'dependency_class': dep_class,
                       'parent_arch': parent_arch, 'dependency_arch': dep_arch}
            for location in LOCATION.finditer(line):
                path, number = location.groups()
                if cache.get(path) is not None:
                    context.update(path=path, line=int(number))
                    break
            link_contexts.append((parent, context))
            parent_names.add(parent)
        suffixes = public_variant_suffixes(source, projects, excluded) if link_candidates else set()
        for name in sorted(link_candidates):
            for suffix in sorted(suffixes, key=len, reverse=True):
                base = name.removesuffix(suffix)
                if name.endswith(suffix) and NAME.fullmatch(base):
                    variant_names[name] = (base, suffix)
                    candidates.add(base)
                    if suffix == '.recovery':
                        recovery_bases.add(base)
                    break
        families = public_generated_families(source, projects, excluded) if link_candidates else set()
        for name in sorted(link_candidates):
            decoded = generated_link_base(name, families)
            if decoded:
                generated_names[name] = decoded
                candidates.add(decoded[0])
    else:
        categories = [name for name in categories if name not in link_categories]
    cross_prefix_verified = False
    if checker is not None and all(marker in checker for marker in
                                   ('Missing required dependencies:', 'requires non-existent')):
        candidates.update(make_candidates)
        # main.mk adds this internal prefix before resolving host-cross requirements.
        # Report only independently proven literal source names, never generated IDs.
        if '$(eval r := $(addprefix host_cross_,$(r)))' in checker:
            candidates.update(host_cross_candidates)
            cross_prefix_verified = True
    evidence, inherited = public_dependency_sources(source, projects, (candidates | parent_names) - dependencies,
                                                     excluded, locations, module_index)
    result = {'categories': categories or ['UNCLASSIFIED_COMPILE_FAILURE'],
              'public_locations': locations,
              'public_dependencies': sorted(dependencies | (inherited & candidates))[:128]}
    if link_contexts:
        contexts = []
        for parent, context in link_contexts:
            if parent in inherited or any(has_public_dependency(blob, parent, path)
                                          for path, blob in cache.items() if blob is not None):
                context['parent'] = parent
            if context not in contexts:
                contexts.append(context)
        result['public_link_contexts'] = contexts
    if link_categories & set(categories):
        verified = dependencies | inherited
        bases = recovery_bases & verified
        result['link_candidates'] = min(len(link_candidates), 128)
        confirmed_variants = {name: item for name, item in variant_names.items() if item[0] in verified}
        confirmed_generated = {name: item for name, item in generated_names.items() if item[0] in verified}
        result['unverified_link_candidates'] = min(len(link_candidates - verified
            - confirmed_variants.keys() - confirmed_generated.keys()), 128)
        result['generated_link_candidates'] = min(len(generated_names), 128)
        for platform in ('android', 'linux', 'darwin', 'windows'):
            names = re.findall(r'\bmissing ([A-Za-z0-9_.@+-]{1,128}) \([A-Z_]{2,32} '
                               + platform + r'-[A-Za-z0-9_.+-]+\)', text)
            result['link_' + platform + '_candidates'] = min(len(set(names)), 128)
        result['link_aidl_name_candidates'] = sum(bool(re.fullmatch(
            r'.+-V[0-9]{1,3}-(?:ndk_platform|ndk|cpp|java)', name)) for name in link_candidates)
        result['link_second_arch_name_candidates'] = sum(name.endswith(('_32', '_64')) for name in link_candidates)
        if confirmed_generated:
            result['public_generated_links'] = [{'base': base, 'family': family}
                for base, family in sorted(set(confirmed_generated.values()))[:128]]
        result['variant_link_candidates'] = min(len(variant_names), 128)
        result['recovery_link_candidates'] = min(len(recovery_bases), 128)
        if confirmed_variants:
            result['public_link_variants'] = [{'base': base, 'suffix': suffix}
                for base, suffix in sorted(set(confirmed_variants.values()))[:128]]
        if bases:
            result['public_recovery_link_bases'] = sorted(bases)[:128]
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
    parser.add_argument('--public-index', type=Path)
    args = parser.parse_args()
    with args.log.open('rb') as stream:
        first = stream.read(2 * 1024**2)
        stream.seek(max(len(first), args.log.stat().st_size - 2 * 1024**2))
        text = (first + b'\n' + stream.read(2 * 1024**2)).decode('utf-8', errors='replace')
    excluded = {entry['destination'].removeprefix('overlay/') for entry in load_lock()['files']}
    module_index = None
    if args.public_index and args.public_index.is_file() and not args.public_index.is_symlink():
        if args.public_index.stat().st_size <= 8 * 1024**2:
            try:
                module_index = json.loads(args.public_index.read_text())
            except (OSError, ValueError, UnicodeError):
                pass
    result = summarize(text, args.manifest.read_bytes(), args.source, excluded, module_index)
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
