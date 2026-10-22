#!/usr/bin/env python3
# Requirements: publish only safe build progress on a separate public branch.
# Ambiguity: this checkpoint is telemetry, never proof of image/device success.
# Research: revalidate diagnostic identities before exposing any public names.
# Optimization: write only on phase transitions; no raw logs or private text.
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
from summarize_compile_failure import RULES, public_file

BRANCH = 'build-progress'
STAGES = {'repo_tool', 'repo_initialization', 'repo_tool_verification', 'source_sync',
          'checkout_verification', 'preflight', 'compile', 'static_validation', 'complete'}


def public_module_names(manifest, source):
    """Index only literal names from pinned public Git blobs, never worktree text."""
    names = set()
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
        if len(names) > 100000:
            raise ValueError('module catalog size limit')
    return sorted(names)


def record(status, run_id, commit, summary=None, source=None, manifest=None, excluded=()):
    if status.get('stage') not in STAGES or not SHA.fullmatch(commit) or not 0 < run_id < 10**20:
        raise ValueError('invalid progress identity')
    result = {'schema': 1, 'run_id': run_id, 'builder_commit': commit, 'stage': status['stage']}
    if 'exit_code' in status:
        code = status['exit_code']
        if not isinstance(code, int) or isinstance(code, bool) or not 0 <= code <= 255:
            raise ValueError('invalid exit status')
        result['exit_code'] = code
    if summary and source is not None and manifest is not None:
        projects = ET.fromstring(manifest).findall('project')
        locations, texts = [], []
        for location in summary.get('public_locations', [])[:64]:
            name, line = location.get('path', ''), location.get('line', 0)
            if not isinstance(line, int) or not 0 < line < 10**7:
                continue
            text = public_file(source, name, projects, excluded)
            if text is not None:
                locations.append({'path': name, 'line': line})
                texts.append(text)
        result['categories'] = [c for c in summary.get('categories', []) if c in RULES][:16]
        result['public_locations'] = locations
        result['public_dependencies'] = sorted({name for name in summary.get('public_dependencies', [])
            if isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_.+-]{1,128}', name)
            and any(json.dumps(name) in text for text in texts)})[:128]
    return result


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
    excluded = {entry['destination'].removeprefix('overlay/') for entry in load_lock()['files']}
    run_id, commit = int(os.environ['GITHUB_RUN_ID']), os.environ['GITHUB_SHA']
    value = record(status, run_id, commit, summary,
                   args.work / 'android', manifest.read_bytes() if manifest.is_file() else None, excluded)
    client = Client(os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN'])
    client.publish(value)
    if status['stage'] in {'preflight', 'compile', 'static_validation', 'complete'}:
        expected = compose_manifest(load_lock(), (args.work / 'inputs/default.xml').read_bytes())
        if manifest.read_bytes() != expected:
            raise ValueError('module catalog manifest mismatch')
        names = public_module_names(expected, args.work / 'android')
        client.publish({'schema': 1, 'run_id': run_id, 'builder_commit': commit,
                        'kind': 'literal-public-bp-names', 'public_module_names': names}, 'catalogs')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError, subprocess.SubprocessError):
        # Reporting is best-effort and must not expose an API response or stop a build.
        print('Restricted progress checkpoint unavailable.')
