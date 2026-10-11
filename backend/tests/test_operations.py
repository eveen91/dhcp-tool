"""Real encrypted export/restore; targets only disposable PostgreSQL databases."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import psycopg
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from dhcp_tool.models import (
    Account,
    Artifact,
    AuditEvent,
    Deployment,
    Draft,
    Firewall,
    Pool,
    Reservation,
    Role,
    Subnet,
    Version,
)

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/operations.py"


class OperationsTests(TransactionTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dhcp-tool-ops-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.config = self.directory / "config"
        self.config.mkdir(mode=0o700)
        (self.config / "backend.env").write_text("SENSITIVE=restore-config-test\n")
        self.key = self.config / "export.key"
        self.key.write_text("test-only-long-export-key-never-production\n")
        self.key.chmod(0o600)
        database = settings.DATABASES["default"]
        self.env = {
            **os.environ,
            "POSTGRES_DB": connection.settings_dict["NAME"],
            "POSTGRES_USER": database["USER"],
            "POSTGRES_PASSWORD": database["PASSWORD"],
            "POSTGRES_HOST": database["HOST"],
            "POSTGRES_PORT": str(database["PORT"]),
        }
        self.target = "test_dhcp_restore_" + uuid.uuid4().hex[:12]
        with psycopg.connect(
            dbname=self.env["POSTGRES_DB"],
            user=database["USER"],
            password=database["PASSWORD"],
            host=database["HOST"],
            port=database["PORT"],
            autocommit=True,
        ) as admin:
            admin.execute(
                psycopg.sql.SQL("CREATE DATABASE {}").format(psycopg.sql.Identifier(self.target))
            )
        self.addCleanup(self.drop_target)

    def drop_target(self):
        with psycopg.connect(**self.credentials(self.env["POSTGRES_DB"]), autocommit=True) as admin:
            admin.execute(
                psycopg.sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                    psycopg.sql.Identifier(self.target)
                )
            )

    def credentials(self, name):
        return {
            "dbname": name,
            "user": self.env["POSTGRES_USER"],
            "password": self.env["POSTGRES_PASSWORD"],
            "host": self.env["POSTGRES_HOST"],
            "port": self.env["POSTGRES_PORT"],
        }

    def run_command(self, *args, env=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            env=env or self.env,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def export(self):
        result = self.run_command(
            "export",
            "--config-dir",
            self.config,
            "--output-dir",
            self.directory / "backups",
            "--key-file",
            self.key,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return next((self.directory / "backups").glob("*.gpg"))

    def test_encrypted_roundtrip_preserves_all_tables_and_binary_hashes(self):
        user = get_user_model().objects.create_user(
            "restore-admin", password="Local-test-strong-pass"
        )
        Account.objects.create(user=user, role=Role.ADMIN)
        firewall = Firewall.objects.create(name="restore-firewall", profile="R81.10")
        Draft.objects.create(firewall=firewall, settings={"domain_name": "restore.example"})
        version = Version.objects.create(
            firewall=firewall,
            number=1,
            profile="R81.10",
            generator_version="1",
            snapshot={"firewall": {"name": "restore-firewall"}, "revision": 1},
        )
        content = b"# immutable artifact\n\x00\xff"
        Artifact.objects.create(
            version=version, content=content, sha256=hashlib.sha256(content).hexdigest()
        )
        AuditEvent.objects.create(
            firewall=firewall,
            actor=user,
            operation="create",
            object_type="firewall",
            object_id=firewall.pk,
            revision=1,
            after={"name": firewall.name},
        )
        subnet = Subnet.objects.create(
            firewall=firewall,
            name="office",
            cidr="192.0.2.0/24",
            options={"routers": ["192.0.2.1"]},
        )
        Pool.objects.create(subnet=subnet, start="192.0.2.100", end="192.0.2.200")
        Reservation.objects.create(
            subnet=subnet, name="host", ip="192.0.2.10", mac="02:00:00:00:00:10"
        )
        Deployment.objects.create(
            version=version,
            operator=user,
            occurred_at=timezone.now(),
            status="successful",
            supplied_hash=hashlib.sha256(content).hexdigest(),
        )
        before = self.run_command("fingerprint")
        self.assertEqual(before.returncode, 0, before.stderr)
        archive = self.export()
        self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(b"restore-config-test", archive.read_bytes())
        restored_config = self.directory / "restored-config"
        restored = self.run_command(
            "restore",
            "--archive",
            archive,
            "--key-file",
            self.key,
            "--target-db",
            self.target,
            "--config-output",
            restored_config,
        )
        self.assertEqual(restored.returncode, 0, restored.stderr)
        after = self.run_command("fingerprint", env={**self.env, "POSTGRES_DB": self.target})
        self.assertEqual(json.loads(before.stdout), json.loads(after.stdout))
        self.assertEqual(
            (restored_config / "backend.env").read_text(), "SENSITIVE=restore-config-test\n"
        )
        self.assertEqual(restored_config.stat().st_mode & 0o777, 0o700)
        self.assertFalse((restored_config / "export.key").exists())
        with psycopg.connect(**self.credentials(self.target)) as restored_db:
            row = restored_db.execute(
                "SELECT content, sha256 FROM dhcp_tool_artifact WHERE version_id = %s",
                (version.pk,),
            ).fetchone()
            self.assertEqual(bytes(row[0]), content)
            self.assertEqual(row[1], hashlib.sha256(content).hexdigest())

    def test_restore_refuses_populated_database_without_changing_existing_data(self):
        archive = self.export()
        with psycopg.connect(**self.credentials(self.target)) as target:
            target.execute("CREATE TABLE keep_data (value text)")
            target.execute("INSERT INTO keep_data VALUES ('keep-me')")
        result = self.run_command(
            "restore",
            "--archive",
            archive,
            "--key-file",
            self.key,
            "--target-db",
            self.target,
            "--config-output",
            self.directory / "restored",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target_not_empty", result.stderr)
        with psycopg.connect(**self.credentials(self.target)) as target:
            self.assertEqual(target.execute("SELECT value FROM keep_data").fetchone()[0], "keep-me")

    def test_export_refuses_public_key_file_and_leaves_no_completed_backup(self):
        self.key.chmod(0o644)
        result = self.run_command(
            "export",
            "--config-dir",
            self.config,
            "--output-dir",
            self.directory / "backups",
            "--key-file",
            self.key,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("key_permissions", result.stderr)
        self.assertFalse(list(self.directory.glob("backups/*.gpg")))

    def test_corrupted_archive_is_rejected_before_database_changes(self):
        archive = self.export()
        content = bytearray(archive.read_bytes())
        content[len(content) // 2] ^= 0x80
        archive.write_bytes(content)
        result = self.run_command(
            "restore",
            "--archive",
            archive,
            "--key-file",
            self.key,
            "--target-db",
            self.target,
            "--config-output",
            self.directory / "restored",
        )
        self.assertNotEqual(result.returncode, 0)
        with psycopg.connect(**self.credentials(self.target)) as target:
            self.assertEqual(
                target.execute(
                    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
                ).fetchone()[0],
                0,
            )

    def test_monitor_reports_stale_backup_and_unreachable_database(self):
        import threading
        import time
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.export()
        url = f"http://127.0.0.1:{server.server_port}/"
        args = (
            "monitor",
            "--url",
            url,
            "--frontend-url",
            url,
            "--backup-dir",
            self.directory / "backups",
            "--min-free-bytes",
            "0",
        )
        healthy = self.run_command(*args)
        self.assertEqual(healthy.returncode, 0, healthy.stderr)
        marker_path = self.directory / "backups/latest.json"
        marker = json.loads(marker_path.read_text())
        marker["created_at"] = time.time() - 37 * 3600
        marker_path.write_text(json.dumps(marker))
        stale = self.run_command(*args)
        self.assertEqual(stale.returncode, 1)
        self.assertFalse(json.loads(stale.stdout)["backup"])
        import socket

        with socket.socket() as refusal:
            refusal.bind(("127.0.0.1", 0))
            unavailable = self.run_command(
                *args, env={**self.env, "POSTGRES_PORT": str(refusal.getsockname()[1])}
            )
        self.assertEqual(unavailable.returncode, 1)
        self.assertFalse(json.loads(unavailable.stdout)["database"])
        self.assertNotIn(self.env["POSTGRES_PASSWORD"], unavailable.stdout + unavailable.stderr)

    def test_export_refuses_directory_inside_configuration(self):
        result = self.run_command(
            "export",
            "--config-dir",
            self.config,
            "--output-dir",
            self.config / "exports",
            "--key-file",
            self.key,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid_export_directory", result.stderr)
        self.assertFalse((self.config / "exports").exists())
