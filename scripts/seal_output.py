#!/usr/bin/env python3
# Requirements: retain only verified outputs, encrypted to a public recipient cert.
# Ambiguity: encrypted delivery does not authorize plaintext public releases.
# Research: OpenSSL 3 CMS supports authenticated AES-GCM and RSA-OAEP transport.
# Optimization: standard-library packaging and the existing OpenSSL host tool.
# Risks: private delivery keys must never enter this repository or the runner.
# Validation: exact members, no symlinks/overwrites, AEAD roundtrip and tamper tests.
"""Seal the three verified build outputs without disclosing plaintext artifacts."""

import argparse
from pathlib import Path
import subprocess
import tarfile
import tempfile

MEMBERS = ('boot.img', 'static-validation.json', 'SHA256SUMS')


def seal(output, certificate):
    output = Path(output)
    for name in MEMBERS:
        path = output / name
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 70 * 1024**2:
            raise ValueError('invalid output member')
    target = output / 'sealed-output.cms'
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        archive = Path(temp) / 'output.tar'
        with tarfile.open(archive, 'w') as bundle:
            for name in MEMBERS:
                bundle.add(output / name, arcname=name, recursive=False)
        with target.open('xb') as encrypted:
            subprocess.run([
                'openssl', 'cms', '-encrypt', '-aes-256-gcm', '-binary',
                '-in', str(archive), '-outform', 'DER', '-recip', str(certificate),
                '-keyopt', 'rsa_padding_mode:oaep', '-keyopt', 'rsa_oaep_md:sha256',
            ], stdout=encrypted, stderr=subprocess.DEVNULL, check=True, timeout=180)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--certificate', type=Path, required=True)
    args = parser.parse_args()
    seal(args.output, args.certificate)
    print('Authenticated encrypted delivery prepared.')


if __name__ == '__main__':
    main()
