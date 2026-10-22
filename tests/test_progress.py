# Requirements: synthetic progress records, no credentials or network calls.
# Ambiguity: progress metadata cannot establish device functionality.
# Research: diagnostics must be validated separately against pinned public Git.
# Optimization: reuse existing public diagnostic identity tests.
# Risks: copying unknown/private fields or allowing invalid phase/commit values.
# Validation: strict output fields and invalid identity/exit-code rejection.
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from report_progress import Client, record


class ProgressTests(unittest.TestCase):
    def test_unknown_fields_and_unverified_diagnostics_are_omitted(self):
        result = record({'stage': 'compile', 'exit_code': 1, 'private': 'secret'}, 42, 'a' * 40,
                        {'public_dependencies': ['secret']})
        self.assertEqual(result, {'schema': 1, 'run_id': 42, 'builder_commit': 'a' * 40,
                                  'stage': 'compile', 'exit_code': 1})

    def test_invalid_identity_and_exit_status_are_rejected(self):
        for status, run, commit in [({'stage': 'private'}, 1, 'a' * 40),
                                     ({'stage': 'compile'}, 0, 'a' * 40),
                                     ({'stage': 'compile'}, 1, 'main'),
                                     ({'stage': 'compile', 'exit_code': True}, 1, 'a' * 40),
                                     ({'stage': 'compile', 'exit_code': -1}, 1, 'a' * 40)]:
            with self.subTest(status=status, run=run), self.assertRaises(ValueError):
                record(status, run, commit)

    def test_api_repository_cannot_select_an_external_host(self):
        for repository in ['../private', 'owner/repo?token=private', 'https://example.com']:
            with self.assertRaises(ValueError):
                Client(repository, 'synthetic-token')
