#!/usr/bin/env python3
# Requirements: safe progress, visible diagnostics and an Actions task summary.
# Ambiguity: this checkpoint is telemetry, never proof of image/device success.
# Research: revalidate diagnostic identities before exposing any public names.
# Optimization: one Git scan for all names and prebuilts-project-only names.
# Risks: token redirects, stale file revisions, accidental private-field copying.
# Validation: strict metadata allowlist, fixed API host, public Git blob checks.
"""Mirror restricted build progress without placing credentials in the container."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from source_inputs import NoRedirect, SHA, compose_manifest, load_lock, relative_path
from summarize_compile_failure import RULES, has_public_dependency, public_file
from summarize_repo_failure import RULES as REPO_RULES
from build_telemetry import STAGES, read_json, sanitize_metrics

BRANCH = 'build-progress'


def public_module_catalog(manifest, source):
    """Classify literal names by project path, never infer module availability."""
    names, prebuilts_names, other_names = set(), set(), set()
    for project in ET.fromstring(manifest).findall('project'):
        name = project.get('path', project.get('name', ''))
        relative_path(name)
        revision = project.get('revision', '')
        if not SHA.fullmatch(revision):
            raise ValueError('unlocked module catalog project')
        root = Path(source) / name
        head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                       stderr=subprocess.DEVNULL, timeout=10).decode().strip()
        if head != revision:
            raise ValueError('module catalog checkout mismatch')
        result = subprocess.run([
            'git', '-C', str(root), 'grep', '-h', '-E',
            '^[[:space:]]*name[[:space:]]*:[[:space:]]*"', revision, '--', '*.bp',
        ], capture_output=True, check=False, timeout=30)
        if result.returncode not in (0, 1) or len(result.stdout) > 8 * 1024**2:
            raise ValueError('module catalog input unavailable')
        for literal in re.findall(r'\bname\s*:\s*("(?:[^"\\]|\\.)*")',
                                  result.stdout.decode('utf-8', errors='strict')):
            value = json.loads(literal)
            if re.fullmatch(r'[A-Za-z0-9_.@+:/-]{1,160}', value):
                names.add(value)
                (prebuilts_names if name.startswith('prebuilts/') else other_names).add(value)
        if len(names) > 100000:
            raise ValueError('module catalog size limit')
    return {'public_module_names': sorted(names),
            'public_prebuilts_project_only_names': sorted(prebuilts_names - other_names)}


def public_module_names(manifest, source):
    """Compatibility interface for the pinned literal-name index."""
    return public_module_catalog(manifest, source)['public_module_names']


def record(status, run_id, commit, summary=None, source=None, manifest=None, excluded=(),
           metrics=None, source_summary=None):
    if (not isinstance(status.get('stage'), str) or status['stage'] not in STAGES
            or not SHA.fullmatch(commit) or not 0 < run_id < 10**20):
        raise ValueError('invalid progress identity')
    result = {'schema': 1, 'run_id': run_id, 'builder_commit': commit, 'stage': status['stage']}
    if 'exit_code' in status:
        code = status['exit_code']
        if not isinstance(code, int) or isinstance(code, bool) or not 0 <= code <= 255:
            raise ValueError('invalid exit status')
        result['exit_code'] = code
    safe_metrics = sanitize_metrics(metrics)
    if safe_metrics:
        result['metrics'] = safe_metrics
    if isinstance(source_summary, dict):
        result['source_categories'] = [c for c in source_summary.get('categories', [])
                                       if isinstance(c, str) and c in
                                       (REPO_RULES.keys() | {'UNCLASSIFIED_REPO_FAILURE'})][:16]
        result['http_statuses'] = sorted({c for c in source_summary.get('http_statuses', [])
                                          if isinstance(c, str) and re.fullmatch(r'[45][0-9]{2}', c)})
    if summary and source is not None and manifest is not None:
        projects = ET.fromstring(manifest).findall('project')
        locations, texts = [], []
        for location in summary.get('public_locations', [])[:64]:
            name, line = location.get('path', ''), location.get('line', 0)
            if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_./+-]+', name)
                    or not isinstance(line, int) or isinstance(line, bool) or not 0 < line < 10**7):
                continue
            text = public_file(source, name, projects, excluded, builder_commit=commit)
            if text is not None:
                locations.append({'path': name, 'line': line})
                texts.append((name, text))
        result['categories'] = [c for c in summary.get('categories', [])
                                if isinstance(c, str) and c in
                                (RULES.keys() | {'UNCLASSIFIED_COMPILE_FAILURE'})][:16]
        result['public_locations'] = locations
        sources = []
        for evidence in summary.get('public_dependency_sources', [])[:32]:
            name, line = evidence.get('path', ''), evidence.get('line', 0)
            if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_./+-]+', name)
                    or not isinstance(line, int) or isinstance(line, bool) or not 0 < line < 10**7):
                continue
            text = public_file(source, name, projects, excluded, builder_commit=commit)
            if text is None:
                continue
            names = sorted({dep for dep in evidence.get('dependencies', [])
                            if isinstance(dep, str) and re.fullmatch(r'[A-Za-z0-9_.@+-]{1,128}', dep)
                            and has_public_dependency(text, dep, name)})[:128]
            if names:
                sources.append({'path': name, 'line': line, 'dependencies': names})
                texts.append((name, text))
        if sources:
            result['public_dependency_sources'] = sources
        result['public_dependencies'] = sorted({name for name in summary.get('public_dependencies', [])
            if isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_.@+-]{1,128}', name)
            and any(has_public_dependency(text, name, path) for path, text in texts)})[:128]
        for key in ('required_candidates', 'unverified_required_candidates',
                    'host_cross_required_candidates'):
            count = summary.get(key)
            if type(count) is int and 0 <= count <= 128:
                result[key] = count
    return result


def render_summary(value):
    """Render only a record already filtered by record(), never arbitrary JSON."""
    lines = ['### Build diagnostics', '',
             f"Stage: `{value['stage']}`; exit: `{value.get('exit_code', 'running')}`.", '']
    metrics = value.get('metrics', {})
    timings = metrics.get('stage_seconds', {})
    if timings:
        lines += ['| Stage | Seconds |', '| --- | ---: |']
        lines += [f'| {stage} | {seconds} |' for stage, seconds in timings.items()]
        lines.append('')
    for key in sorted(NUMERIC_SUMMARY & metrics.keys()):
        lines.append(f'- {key}: {metrics[key]}')
    for key in ('categories', 'source_categories', 'http_statuses', 'public_dependencies'):
        if value.get(key):
            lines.append(f"- {key}: " + ', '.join('`' + item + '`' for item in value[key]))
    for key in ('required_candidates', 'unverified_required_candidates',
                'host_cross_required_candidates'):
        if key in value:
            lines.append(f'- {key}: {value[key]}')
    for location in value.get('public_locations', []):
        lines.append(f"- Public source: `{location['path']}:{location['line']}`")
    for source in value.get('public_dependency_sources', []):
        lines.append(f"- Dependency evidence: `{source['path']}:{source['line']}`; "
                     + ', '.join('`' + name + '`' for name in source['dependencies']))
    lines += ['', 'Ninja progress is per batch. Device functionality remains NOT_TESTED.', '']
    return '\n'.join(lines)


NUMERIC_SUMMARY = {'elapsed_seconds', 'disk_free_mib', 'memory_available_mib',
                   'swap_free_mib', 'load_1m', 'log_bytes', 'log_idle_seconds'}


class Client:
    def __init__(self, repository, token):
        if (not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository)
                or any(part in ('.', '..') for part in repository.split('/'))):
            raise ValueError('invalid repository')
        self.prefix = 'https://api.github.com/repos/' + repository
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, suffix, method='GET', data=None):
        body = None if data is None else json.dumps(data).encode()
        request = urllib.request.Request(self.prefix + suffix, data=body, method=method, headers={
            'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json',
        })
        with self.opener.open(request, timeout=20) as response:
            return json.loads(response.read(1024**2))

    def publish(self, value, directory='runs'):
        if directory not in {'runs', 'catalogs'}:
            raise ValueError('invalid progress topic')
        try:
            self.request('/git/ref/heads/' + BRANCH)
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            self.request('/git/refs', 'POST', {'ref': 'refs/heads/' + BRANCH,
                                             'sha': value['builder_commit']})
        path = '/contents/' + directory + '/' + str(value['run_id']) + '.json'
        encoded = (json.dumps(value, indent=2) + '\n').encode()
        digest = hashlib.sha1(b'blob ' + str(len(encoded)).encode() + b'\0' + encoded).hexdigest()
        content = base64.b64encode(encoded).decode()
        for attempt in range(3):
            update = {'branch': BRANCH, 'message': '[skip ci] Update restricted build progress',
                      'content': content}
            try:
                old = self.request(path + '?ref=' + urllib.parse.quote(BRANCH))
                if old['sha'] == digest:
                    return
                update['sha'] = old['sha']
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
            try:
                self.request(path, 'PUT', update)
                return
            except urllib.error.HTTPError as error:
                if error.code not in (409, 422) or attempt == 2:
                    raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    status = json.loads((args.work / 'output/status.json').read_text())
    path = args.work / 'output/compile-error-summary.json'
    summary = json.loads(path.read_text()) if path.is_file() else None
    manifest = args.work / 'manifest/default.xml'
    manifest_data = manifest.read_bytes() if manifest.is_file() else None
    if manifest_data is not None:
        expected = compose_manifest(load_lock(), (args.work / 'inputs/default.xml').read_bytes())
        if manifest_data != expected:
            raise ValueError('diagnostic manifest differs from the locked graph')
    excluded = {entry['destination'].removeprefix('overlay/') for entry in load_lock()['files']}
    run_id, commit = int(os.environ['GITHUB_RUN_ID']), os.environ['GITHUB_SHA']
    value = record(status, run_id, commit, summary,
                   args.work / 'android', manifest_data, excluded,
                   metrics=read_json(args.work / 'output/telemetry.json'),
                   source_summary=read_json(args.work / 'output/source-error-summary.json'))
    print('BUILD_DIAGNOSTICS ' + json.dumps(value, sort_keys=True), flush=True)
    if 'exit_code' in value and os.environ.get('GITHUB_STEP_SUMMARY'):
        try:
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
                stream.write(render_summary(value))
        except OSError:
            print('Build task summary unavailable.', flush=True)
    client = Client(os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN'])
    client.publish(value)
    # The pinned catalog is needed once per attempt, not on every heartbeat/exit.
    if status['stage'] == 'compile' and 'exit_code' not in status:
        catalog = public_module_catalog(manifest_data, args.work / 'android')
        print('BUILD_CATALOG ' + json.dumps({key: len(names) for key, names in catalog.items()},
                                          sort_keys=True), flush=True)
        client.publish({'schema': 1, 'run_id': run_id, 'builder_commit': commit,
                        'kind': 'literal-public-bp-names', **catalog}, 'catalogs')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError, subprocess.SubprocessError):
        # Reporting is best-effort and must not expose an API response or stop a build.
        print('Restricted progress checkpoint unavailable.')
