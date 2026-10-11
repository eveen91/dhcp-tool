#!/usr/bin/env python3
"""Private encrypted exports, empty-database restore and local operational checks."""

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql


class OperationError(Exception):
    pass


def credentials(database=None):
    return {
        "dbname": database or os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
        "host": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "connect_timeout": 3,
    }


def pg_environment(database=None):
    values = credentials(database)
    return {
        **os.environ,
        "PGDATABASE": values["dbname"],
        "PGUSER": values["user"],
        "PGPASSWORD": values["password"],
        "PGHOST": values["host"],
        "PGPORT": str(values["port"]),
        "PGCONNECT_TIMEOUT": "3",
        "PGOPTIONS": "-c statement_timeout=120000 -c lock_timeout=3000",
    }


def run(command, *, env=None):
    try:
        subprocess.run(command, env=env, check=True, capture_output=True, timeout=180)
    except (subprocess.SubprocessError, OSError) as error:
        # Raw stderr may contain credentials, SQL or configuration. Never print it.
        raise OperationError("external_command_failed") from error


def private_key(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
        raise OperationError("key_permissions")
    if len(path.read_bytes().strip()) < 32:
        raise OperationError("key_too_short")


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
        raise OperationError("directory_permissions")


def encrypt_options(directory, key):
    return [
        "gpg",
        "--homedir",
        str(directory / "gnupg"),
        "--batch",
        "--yes",
        "--pinentry-mode",
        "loopback",
        "--passphrase-file",
        str(key),
    ]


def export(args):
    if args.output_dir.resolve().is_relative_to(args.config_dir.resolve()):
        raise OperationError("invalid_export_directory")
    private_key(args.key_file)
    private_directory(args.output_dir)
    files = sorted(args.config_dir.rglob("*"))
    if not args.config_dir.is_dir() or any(path.is_symlink() for path in files):
        raise OperationError("invalid_config_directory")
    name = datetime.now(timezone.utc).strftime("dhcp-tool-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    final = args.output_dir / (name + ".tar.gpg")
    with tempfile.TemporaryDirectory(prefix=".export-", dir=args.output_dir) as temporary:
        directory = Path(temporary)
        private_directory(directory / "gnupg")
        dump = directory / "database.dump"
        run(
            [
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--file",
                str(dump),
            ],
            env=pg_environment(),
        )
        bundle = directory / "bundle.tar"
        with tarfile.open(bundle, "w") as archive:
            archive.add(dump, arcname="database.dump")
            for path in files:
                if path.is_file() and path.resolve() != args.key_file.resolve():
                    archive.add(
                        path,
                        arcname="config/" + path.relative_to(args.config_dir).as_posix(),
                    )
        encrypted = directory / "encrypted.gpg"
        run(
            [
                *encrypt_options(directory, args.key_file),
                "--cipher-algo",
                "AES256",
                "--output",
                str(encrypted),
                "--symmetric",
                str(bundle),
            ]
        )
        encrypted.chmod(0o600)
        os.replace(encrypted, final)
        marker = directory / "latest.json"
        marker.write_text(
            json.dumps(
                {
                    "file": final.name,
                    "sha256": checksum(final),
                    "created_at": time.time(),
                }
            )
        )
        marker.chmod(0o600)
        os.replace(marker, args.output_dir / "latest.json")
    print(json.dumps({"event": "export_complete", "file": final.name}))


def restore(args):
    private_key(args.key_file)
    if args.target_db == os.environ["POSTGRES_DB"]:
        raise OperationError("target_is_source")
    if args.config_output.exists():
        raise OperationError("config_output_exists")
    # Advisory lock coordinates our restores; application services must remain stopped.
    with psycopg.connect(**credentials(args.target_db), autocommit=True) as target:
        target.execute("SELECT pg_advisory_lock(7492140801)")
        occupied = target.execute(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','v','m','S')"
        ).fetchone()[0]
        if occupied:
            raise OperationError("target_not_empty")
        # Put decrypted temporary data beside its final private config directory.
        args.config_output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".restore-", dir=args.config_output.parent
        ) as temporary:
            directory = Path(temporary)
            private_directory(directory / "gnupg")
            bundle = directory / "bundle.tar"
            run(
                [
                    *encrypt_options(directory, args.key_file),
                    "--output",
                    str(bundle),
                    "--decrypt",
                    str(args.archive),
                ]
            )
            with tarfile.open(bundle) as archive:
                members = archive.getmembers()
                names = set()
                for member in members:
                    name = Path(member.name)
                    if (
                        not member.isfile()
                        or name.is_absolute()
                        or ".." in name.parts
                        or member.name in names
                        or (
                            member.name != "database.dump" and not member.name.startswith("config/")
                        )
                    ):
                        raise OperationError("invalid_archive")
                    names.add(member.name)
                if "database.dump" not in names:
                    raise OperationError("missing_database_dump")
                archive.extractall(directory, members=members, filter="data")
            config = directory / "config"
            private_directory(config)
            for path in config.rglob("*"):
                path.chmod(0o700 if path.is_dir() else 0o600)
            run(
                [
                    "pg_restore",
                    "--exit-on-error",
                    "--single-transaction",
                    "--no-owner",
                    "--no-acl",
                    "--dbname",
                    args.target_db,
                    str(directory / "database.dump"),
                ],
                env=pg_environment(args.target_db),
            )
            os.replace(config, args.config_output)
    print(json.dumps({"event": "restore_complete"}))


def fingerprint(args):
    result = {}
    with psycopg.connect(**credentials()) as database:
        database.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        tables = database.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        ).fetchall()
        for (table,) in tables:
            digest = hashlib.sha256()
            count = 0
            with database.cursor(name="fingerprint") as cursor:
                cursor.execute(
                    sql.SQL('SELECT row_to_json(t)::text COLLATE "C" FROM {} t ORDER BY 1').format(
                        sql.Identifier(table)
                    )
                )
                for (row,) in cursor:
                    digest.update(row.encode() + b"\n")
                    count += 1
            result[table] = {"count": count, "sha256": digest.hexdigest()}
    print(json.dumps(result, sort_keys=True))


def monitor(args):
    result = {"event": "operational_check"}
    try:
        with urllib.request.urlopen(args.url, timeout=5) as response:
            result["api"] = (
                response.status == 200 and json.loads(response.read(1024)).get("status") == "ok"
            )
    except (OSError, ValueError):
        result["api"] = False
    try:
        with urllib.request.urlopen(args.frontend_url, timeout=5) as response:
            result["frontend"] = response.status == 200
    except OSError:
        result["frontend"] = False
    try:
        with psycopg.connect(**credentials()) as database:
            result["database"] = database.execute("SELECT 1").fetchone() == (1,)
    except (psycopg.Error, KeyError):
        result["database"] = False
    try:
        result["disk"] = shutil.disk_usage(args.backup_dir).free >= args.min_free_bytes
        marker = json.loads((args.backup_dir / "latest.json").read_text())
        archive = args.backup_dir / marker["file"]
        result["backup"] = (
            archive.parent == args.backup_dir
            and archive.is_file()
            and 0 <= time.time() - marker["created_at"] <= args.max_backup_age_hours * 3600
            and checksum(archive) == marker["sha256"]
        )
    except (OSError, ValueError, KeyError, TypeError):
        result["disk"] = result.get("disk", False)
        result["backup"] = False
    print(json.dumps(result))
    return (
        0 if all(result[name] for name in ("api", "frontend", "database", "disk", "backup")) else 1
    )


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("export")
    backup.add_argument("--config-dir", type=Path, required=True)
    backup.add_argument("--output-dir", type=Path, required=True)
    backup.add_argument("--key-file", type=Path, required=True)
    recovery = commands.add_parser("restore")
    recovery.add_argument("--archive", type=Path, required=True)
    recovery.add_argument("--key-file", type=Path, required=True)
    recovery.add_argument("--target-db", required=True)
    recovery.add_argument("--config-output", type=Path, required=True)
    commands.add_parser("fingerprint")
    check = commands.add_parser("monitor")
    check.add_argument("--url", default="http://127.0.0.1:8000/api/v1/health/")
    check.add_argument("--frontend-url", default="http://127.0.0.1:3000/")
    check.add_argument("--backup-dir", type=Path, required=True)
    check.add_argument("--min-free-bytes", type=int, default=2 * 1024**3)
    check.add_argument("--max-backup-age-hours", type=int, default=36)
    args = parser.parse_args()
    try:
        return {
            "export": export,
            "restore": restore,
            "fingerprint": fingerprint,
            "monitor": monitor,
        }[args.command](args) or 0
    except OperationError as error:
        print(
            json.dumps({"event": "operation_failed", "code": str(error)}),
            file=sys.stderr,
        )
    except (OSError, ValueError, KeyError, psycopg.Error, tarfile.TarError):
        print(
            json.dumps({"event": "operation_failed", "code": "operation_failed"}),
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
