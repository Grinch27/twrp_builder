#!/usr/bin/env python3
# Requirements: report only structured public-source failure metadata.
# Ambiguity: unmatched errors remain unclassified; raw logs stay private.
# Research: use the first concrete upstream failure before changing dependencies.
# Optimization: inspect only the final 256 KiB of the selected phase log.
# Risks: private text or credentials appearing in compiler/network diagnostics.
# Validation: output fixed categories and exact reviewed project identities only.
"""Summarize a repo failure without returning source text or log lines."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

RULES = {
    'REMOTE_NOT_FOUND': r'repository .*not found|repository not found|HTTP (?:error )?404',
    'AUTHENTICATION_REQUIRED': r'authentication failed|could not read Username|HTTP (?:error )?(?:401|403)',
    'REF_NOT_FOUND': r"couldn.t find remote ref|not our ref|invalid revision|revision .*not found|unable to resolve revision",
    'NETWORK_FAILURE': r'Could not resolve host|Failed to connect|TLS|Connection reset|timed out|HTTP (?:error )?5[0-9]{2}',
    'MANIFEST_PARSE_ERROR': r'ManifestParseError|manifest parse|duplicate path|duplicate project|invalid manifest',
    'REPO_ARGUMENT_ERROR': r'no such option|unrecognized arguments|unknown option',
    'PYTHON_RUNTIME_ERROR': r'ModuleNotFoundError|ImportError|TypeError|AttributeError',
    'GIT_COMMAND_FAILURE': r'GitCommandError|GitError|fatal:|Cannot fetch',
}


def summarize(text, manifest):
    errors = '\n'.join(line for line in text.splitlines()
                       if re.search(r'error|fatal|failed|cannot|exception|traceback', line, re.I))
    categories = [name for name, pattern in RULES.items() if re.search(pattern, errors, re.I)]
    projects = []
    for project in ET.fromstring(manifest).findall('project'):
        name = project.get('name', '')
        revision = project.get('revision', '')
        if (re.fullmatch(r'[A-Za-z0-9_.\-/]+', name) and re.fullmatch(r'[0-9a-f]{40}', revision)
                and re.search(r'(?<![A-Za-z0-9_./-])' + re.escape(name) + r'(?![A-Za-z0-9_./-])', errors)):
            projects.append({'project': name, 'revision': revision})
    return {'categories': categories or ['UNCLASSIFIED_REPO_FAILURE'],
            'http_statuses': sorted(set(re.findall(r'HTTP[^\n0-9]{0,20}([45][0-9]{2})', errors))),
            'public_projects': projects[:8]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.log.open('rb') as stream:
        stream.seek(max(0, args.log.stat().st_size - 262144))
        text = stream.read().decode('utf-8', errors='replace')
    args.output.write_text(json.dumps(summarize(text, args.manifest.read_bytes()), indent=2) + '\n')


if __name__ == '__main__':
    main()
