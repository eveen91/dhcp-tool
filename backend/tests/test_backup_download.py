import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from dhcp_tool.models import Account, Role


class BackupDownloadTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        directory = self.root / "published"
        directory.mkdir()
        self.content = b"encrypted-fixture-bytes\x00\xff"
        (directory / "artifact.tar.gpg").write_bytes(self.content)
        (directory / "metadata.json").write_text(
            json.dumps(
                {
                    "filename": "dhcp-tool-20261011T120000Z-a1b2c3d4.tar.gpg",
                    "sha256": hashlib.sha256(self.content).hexdigest(),
                    "size": len(self.content),
                }
            )
        )
        (self.root / "current").symlink_to(directory, target_is_directory=True)
        self.settings_override = override_settings(BACKUP_DOWNLOAD_DIR=str(self.root))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.user = get_user_model().objects.create_user("backup-admin")
        self.account = Account.objects.create(user=self.user, role=Role.ADMIN)
        self.url = "/api/v1/backups/latest/download/"

    def test_only_active_administrator_can_download(self):
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_login(self.user)
        for role in (Role.READER, Role.EDITOR, Role.OPERATOR):
            self.account.role = role
            self.account.save()
            self.assertEqual(self.client.get(self.url).status_code, 403)
        self.account.role = Role.ADMIN
        self.account.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), self.content)
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertEqual(response["X-Backup-SHA256"], hashlib.sha256(self.content).hexdigest())
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertIn("Cookie", response["Vary"])
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_missing_copy_has_safe_error_and_no_filesystem_details(self):
        self.client.force_login(self.user)
        (self.root / "current").unlink()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "backup_unavailable")
        self.assertNotIn(str(self.root), response.content.decode())

    def test_user_cannot_choose_file_or_trigger_export(self):
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(self.url + "?file=/etc/dhcp-tool-backup.key").status_code, 400
        )
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_link_outside_published_directory_is_rejected(self):
        self.client.force_login(self.user)
        outside = self.root.parent / ("outside-" + self.root.name)
        outside.mkdir()
        self.addCleanup(outside.rmdir)
        (self.root / "current").unlink()
        (self.root / "current").symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_publisher_checks_integrity_and_keeps_previous_download_on_failure(self):
        import grp

        source = self.root / "source"
        source.mkdir()
        filename = "dhcp-tool-20261011T120000Z-a1b2c3d4.tar.gpg"
        (source / filename).write_bytes(self.content)
        (source / "latest.json").write_text(
            json.dumps({"file": filename, "sha256": hashlib.sha256(self.content).hexdigest()})
        )
        destination = self.root / "downloads"
        script = Path(__file__).resolve().parents[2] / "scripts/publish-backup.py"
        command = [
            sys.executable,
            str(script),
            "--source",
            str(source),
            "--destination",
            str(destination),
            "--group",
            grp.getgrgid(os.getgid()).gr_name,
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        previous = (destination / "current").resolve()
        self.assertEqual((previous / "artifact.tar.gpg").read_bytes(), self.content)
        self.assertEqual((previous / "artifact.tar.gpg").stat().st_mode & 0o777, 0o640)
        self.assertFalse((previous / "export.key").exists())
        (source / filename).write_bytes(b"corrupted")
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((destination / "current").resolve(), previous)
        self.assertEqual((previous / "artifact.tar.gpg").read_bytes(), self.content)
