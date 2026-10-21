# Requirements: synthetic error text only; never add private logs to tests.
# Ambiguity: unknown failures must retain an unclassified result.
# Research: structured metadata is a diagnosis aid, not a root-cause proof.
# Optimization: small in-memory fixtures.
# Risks: echoing credentials, arbitrary URLs, source excerpts or log messages.
# Validation: output only fixed categories, numeric HTTP codes and known projects.
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from summarize_repo_failure import summarize

MANIFEST = b'<manifest><project name="platform/bionic" revision="' + b'1' * 40 + b'"/></manifest>'


class SummaryTests(unittest.TestCase):
    def test_private_text_and_credentials_are_not_returned(self):
        raw = 'fatal: private config secret-value https://private.example/token?secret=abc HTTP 403'
        result = summarize(raw, MANIFEST)
        self.assertEqual(result['http_statuses'], ['403'])
        self.assertIn('AUTHENTICATION_REQUIRED', result['categories'])
        self.assertNotIn('secret', json.dumps(result))
        self.assertNotIn('private.example', json.dumps(result))

    def test_only_reviewed_project_is_reported(self):
        result = summarize('error: Cannot fetch platform/bionic; Cannot fetch private/project', MANIFEST)
        self.assertEqual(result['public_projects'], [{'project': 'platform/bionic', 'revision': '1' * 40}])

    def test_unknown_error_does_not_echo_text(self):
        result = summarize('error: arbitrary private source excerpt', MANIFEST)
        self.assertEqual(result['categories'], ['UNCLASSIFIED_REPO_FAILURE'])

    def test_ref_failure_classification(self):
        result = summarize("fatal: couldn't find remote ref android-12.1", MANIFEST)
        self.assertIn('REF_NOT_FOUND', result['categories'])
