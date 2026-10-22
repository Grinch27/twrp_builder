# Requirements: synthetic output fixtures; never access private Android inputs.
# Ambiguity: these tests verify delivery, not a real recovery image.
# Research: the recipient private key remains local to this synthetic fixture.
# Optimization: standard-library tests and OpenSSL already required by the build.
# Risks: plaintext leakage, recipient mismatch, tampering, unsafe file selection.
# Validation: roundtrip members/bytes, authentication failure, overwrite rejection.
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from seal_output import MEMBERS, seal


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / 'output'
        self.output.mkdir()
        for name in MEMBERS:
            (self.output / name).write_bytes(('synthetic-' + name).encode())
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-subj', '/CN=synthetic', '-keyout', str(self.root / 'private.pem'),
                        '-out', str(self.root / 'public.pem')],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    def decrypt(self, path):
        return subprocess.run(['openssl', 'cms', '-decrypt', '-binary', '-inform', 'DER',
                               '-in', str(path), '-inkey', str(self.root / 'private.pem')],
                              capture_output=True, check=False)

    def test_authenticated_roundtrip_contains_only_expected_members(self):
        (self.output / 'private.log').write_text('never export this fixture')
        encrypted = seal(self.output, self.root / 'public.pem')
        result = self.decrypt(encrypted)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn(b'synthetic-boot.img', encrypted.read_bytes())
        with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
            self.assertEqual(archive.getnames(), list(MEMBERS))
            for name in MEMBERS:
                self.assertEqual(archive.extractfile(name).read(), (self.output / name).read_bytes())
        with self.assertRaises(FileExistsError):
            seal(self.output, self.root / 'public.pem')

    def test_modified_ciphertext_fails_authentication(self):
        encrypted = seal(self.output, self.root / 'public.pem')
        data = bytearray(encrypted.read_bytes())
        data[-1] ^= 1
        encrypted.write_bytes(data)
        self.assertNotEqual(self.decrypt(encrypted).returncode, 0)

    def test_symlink_and_missing_members_are_rejected(self):
        path = self.output / 'boot.img'
        path.unlink()
        with self.assertRaises(ValueError):
            seal(self.output, self.root / 'public.pem')
        path.symlink_to(self.output / 'SHA256SUMS')
        with self.assertRaises(ValueError):
            seal(self.output, self.root / 'public.pem')
