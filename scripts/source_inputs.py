#!/usr/bin/env python3
# Requirements: pinned selene archive inputs; private credential only during fetch.
# Ambiguity: a complete checkout of the locked manifest is not yet a proven build.
# Research: resolve the first real dependency failure without disabling modules.
# Optimization: fetch ten selected files, rather than the whole archive.
# Risks: path traversal, credential disclosure, partial downloads, upstream drift.
# Validation: Git blob identities, sizes, manifest paths, clean project HEADs.
"""Fetch reviewed inputs and verify a fresh repo checkout. Python >= 3.10."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

SHA = re.compile(r"[0-9a-f]{40}\Z")
ROOT = Path(__file__).resolve().parents[1]


def relative_path(value):
    """Accept a canonical relative POSIX path, without Git control directories."""
    path = PurePosixPath(value)
    if (not value or value == "." or path.is_absolute() or str(path) != value
            or any(p in (".", "..", ".git", ".repo") for p in path.parts)
            or "\\" in value or any(ord(c) < 32 for c in value)):
        raise ValueError("unsafe relative path")
    return path


def load_lock(path=ROOT / "source.lock.json"):
    lock = json.loads(Path(path).read_text(encoding="utf-8"))
    if lock.get("schema") != 1 or not SHA.fullmatch(lock["source"]["commit"]):
        raise ValueError("unsupported source lock")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", lock["source"]["repository"]):
        raise ValueError("invalid source repository")
    for entry in lock["files"]:
        relative_path(entry["path"])
        relative_path(entry["destination"])
        if not SHA.fullmatch(entry["blob"]) or not 0 < entry["size"] < 32 * 1024**2:
            raise ValueError("invalid locked file")
    for key in ("path", "destination"):
        if len({e[key] for e in lock["files"]}) != len(lock["files"]):
            raise ValueError("duplicate locked file")
    return lock


def validate_manifest(data, expected_count):
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("XML declarations are forbidden")
    root = ET.fromstring(data)
    if root.tag != "manifest":
        raise ValueError("not a repo manifest")
    allowed = {"remote", "default", "project", "superproject", "contactinfo"}
    if any(e.tag not in allowed for e in root):
        raise ValueError("unreviewed manifest directive")
    remotes = {}
    for remote in root.findall("remote"):
        url = urllib.parse.urlsplit(remote.get("fetch", ""))
        if (url.scheme != "https" or url.hostname not in
                {"github.com", "android.googlesource.com"} or url.username
                or url.password or url.port or url.query or url.fragment):
            raise ValueError("unreviewed source host")
        name = remote.get("name")
        if not name or name in remotes:
            raise ValueError("duplicate or empty remote")
        remotes[name] = remote
    defaults = root.findall("default")
    if len(defaults) != 1:
        raise ValueError("one manifest default is required")
    projects = root.findall("project")
    if len(projects) != expected_count:
        raise ValueError("unexpected project count")
    paths, destinations = set(), set()
    for project in projects:
        relative_path(project.get("name", ""))
        path = str(relative_path(project.get("path", project.get("name", ""))))
        if path in paths or not SHA.fullmatch(project.get("revision", "")):
            raise ValueError("duplicate project or unlocked revision")
        paths.add(path)
        if project.get("remote", defaults[0].get("remote")) not in remotes:
            raise ValueError("unknown manifest remote")
        for child in project:
            if child.tag not in {"copyfile", "linkfile"}:
                raise ValueError("unreviewed project directive")
            relative_path(child.get("src", ""))
            dest = str(relative_path(child.get("dest", "")))
            if dest in destinations:
                raise ValueError("duplicate copy/link destination")
            destinations.add(dest)
    return projects


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("source API redirect rejected")


class SourceClient:
    def __init__(self, repository, revision, token):
        self.prefix = "https://api.github.com/repos/" + repository
        self.revision = revision
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, suffix):
        request = urllib.request.Request(self.prefix + suffix, headers={
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "selene-twrp-builder",
        })
        for attempt in range(3):
            try:
                with self.opener.open(request, timeout=60) as response:
                    data = response.read(48 * 1024**2 + 1)
                if len(data) > 48 * 1024**2:
                    raise ValueError("source API response too large")
                return json.loads(data)
            except urllib.error.HTTPError as exc:
                if attempt == 2 or exc.code not in (429, 500, 502, 503, 504):
                    raise ValueError(f"source API failed (HTTP {exc.code})") from None
                time.sleep(2 ** attempt)
            except urllib.error.URLError:
                raise ValueError("source API connection failed") from None
        raise ValueError("source API retry limit")

    def read(self, entry):
        suffix = "/contents/" + urllib.parse.quote(entry["path"], safe="/")
        record = self.request(suffix + "?ref=" + self.revision)
        if (record.get("type") != "file" or record.get("sha") != entry["blob"]
                or record.get("size") != entry["size"]):
            raise ValueError("source file differs from reviewed lock")
        if record.get("encoding") != "base64":
            record = self.request("/git/blobs/" + entry["blob"])
        if record.get("sha") != entry["blob"] or record.get("encoding") != "base64":
            raise ValueError("source blob unavailable")
        data = base64.b64decode("".join(record["content"].split()), validate=True)
        verify_blob(data, entry)
        return data


def verify_blob(data, entry):
    digest = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if len(data) != entry["size"] or digest != entry["blob"]:
        raise ValueError("source blob size or Git identity mismatch")


def write_new(root, name, data):
    path = root.joinpath(*relative_path(name).parts)
    for parent in (path.parent, *path.parent.parents):
        if parent.is_symlink():
            raise ValueError("symlink in output path")
        if parent == root:
            break
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(data)


def fetch(lock, output, client):
    # A failed partial output is retained; reusing it requires a fresh run path.
    output = Path(output)
    if output.is_symlink() or output.absolute() != output.resolve():
        raise ValueError("source output path must not traverse symlinks")
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    records = []
    for entry in lock["files"]:
        data = client.read(entry)
        if entry["destination"] == "default.xml":
            validate_manifest(data, lock["source"]["manifest_projects"])
        write_new(output, entry["destination"], data)
        records.append({"path": entry["path"], "git_blob": entry["blob"],
                        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    write_new(output, "input-identities.json", json.dumps({
        "source_commit": lock["source"]["commit"], "files": records,
    }, indent=2).encode() + b"\n")


def verify_checkout(lock, manifest, source):
    projects = validate_manifest(Path(manifest).read_bytes(), lock["source"]["manifest_projects"])
    for project in projects:
        path = Path(source) / project.get("path", project.get("name"))
        head = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
        if head != project.get("revision"):
            raise ValueError("checkout revision mismatch")
        dirty = subprocess.check_output([
            "git", "-C", str(path), "status", "--porcelain", "--untracked-files=normal",
        ], text=True)
        if dirty:
            raise ValueError("fresh checkout contains unexpected changes")
    return len(projects)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=ROOT / "source.lock.json")
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser("fetch")
    download.add_argument("--output", type=Path, required=True)
    manifest = commands.add_parser("manifest")
    manifest.add_argument("path", type=Path)
    checkout = commands.add_parser("checkout")
    checkout.add_argument("--manifest", type=Path, required=True)
    checkout.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    lock = load_lock(args.lock)
    if args.command == "fetch":
        token = os.environ.get("TWRP_SOURCE_TOKEN", "")
        if not token:
            raise ValueError("configure TWRP_SOURCE_TOKEN with read access to the source repository")
        fetch(lock, args.output, SourceClient(lock["source"]["repository"], lock["source"]["commit"], token))
    elif args.command == "manifest":
        validate_manifest(args.path.read_bytes(), lock["source"]["manifest_projects"])
    else:
        verify_checkout(lock, args.manifest, args.source)
    print("Source input verification passed.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, ET.ParseError, subprocess.CalledProcessError):
        # Do not echo private response bodies, source text, or compiler output.
        print("Source input verification failed; check access, lock identities and paths.", file=sys.stderr)
        sys.exit(1)
