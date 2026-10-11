#!/usr/bin/env python3
"""Publish an encrypted export for administrator downloads, without publishing its key."""

import argparse
import grp
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import uuid
from pathlib import Path


def publish(source, destination, group):
    gid = grp.getgrnam(group).gr_gid
    metadata = json.loads((source / "latest.json").read_text())
    filename, expected = metadata["file"], metadata["sha256"]
    if not re.fullmatch(r"dhcp-tool-\d{8}T\d{6}Z-[0-9a-f]{8}\.tar\.gpg", filename):
        raise ValueError
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError
    destination.mkdir(parents=True, exist_ok=True, mode=0o750)
    if destination.is_symlink():
        raise ValueError
    destination.chmod(0o750)
    os.chown(destination, -1, gid)
    directory = Path(tempfile.mkdtemp(prefix=".publishing-", dir=destination))
    link = destination / f".current-{uuid.uuid4().hex}"
    try:
        descriptor = os.open(source / filename, os.O_RDONLY | os.O_NOFOLLOW)
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(descriptor, "rb") as original:
            if not stat.S_ISREG(os.fstat(original.fileno()).st_mode):
                raise ValueError
            with (directory / "artifact.tar.gpg").open("xb") as target:
                while chunk := original.read(1024 * 1024):
                    target.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                target.flush()
                os.fsync(target.fileno())
        if digest.hexdigest() != expected:
            raise ValueError
        (directory / "metadata.json").write_text(
            json.dumps({"filename": filename, "sha256": expected, "size": size}) + "\n"
        )
        for file in directory.iterdir():
            file.chmod(0o640)
            os.chown(file, -1, gid)
        directory.chmod(0o750)
        os.chown(directory, -1, gid)
        generation = destination / f"export-{uuid.uuid4().hex}"
        directory.rename(generation)
        directory = generation
        link.symlink_to(generation.name, target_is_directory=True)
        link.replace(destination / "current")
    except BaseException:
        link.unlink(missing_ok=True)
        shutil.rmtree(directory)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--group", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        publish(args.source, args.destination, args.group)
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"event": "backup_publication_failed"}))
        raise SystemExit(1) from None
    print(json.dumps({"event": "backup_published"}))


if __name__ == "__main__":
    main()
