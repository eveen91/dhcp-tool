import csv
import io
from unittest.mock import patch

import test_draft
from django.test import Client, TestCase

from dhcp_tool.models import AuditEvent, Reservation


class CSVTests(TestCase):
    change = test_draft.DraftAPITests.change
    subnet = test_draft.DraftAPITests.subnet
    pool = test_draft.DraftAPITests.pool
    reservation = test_draft.DraftAPITests.reservation

    def setUp(self):
        test_draft.DraftAPITests.setUp(self)
        self.subnet_id = self.subnet()
        self.pool(self.subnet_id)
        self.row = self.reservation(self.subnet_id).json()

    def export(self):
        response = self.client.get(self.base + "csv/export/")
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8-sig")

    def edited(self, **values):
        rows = list(csv.DictReader(io.StringIO(self.export())))
        rows[0].update(values)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()

    def test_preview_does_not_write_apply_is_audited_and_single_use(self):
        before = self.client.get(self.base + "draft/").json()
        csv_text = self.edited(ip="10.0.0.6", description="Biuro Łódź")
        preview = self.change("post", "csv/preview/", {"csv": csv_text})
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(
            preview.json()["counts"], {"create": 0, "update": 1, "delete": 0, "unchanged": 0}
        )
        self.assertEqual(self.client.get(self.base + "draft/").json(), before)
        applied = self.change("post", "csv/apply/", {"token": preview.json()["token"]})
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(Reservation.objects.get(pk=self.row["id"]).ip, "10.0.0.6")
        event = AuditEvent.objects.filter(firewall_id=self.fw).latest("created_at")
        self.assertEqual(event.operation, "csv_import")
        self.assertEqual(event.before, before)
        self.assertEqual(
            self.change("post", "csv/apply/", {"token": preview.json()["token"]}).status_code, 409
        )

    def test_validation_foreign_ids_and_tampered_preview_are_rejected(self):
        invalid = self.edited(ip="10.0.0.20")
        self.assertEqual(self.change("post", "csv/preview/", {"csv": invalid}).status_code, 400)
        foreign = self.edited(id="00000000-0000-0000-0000-000000000001")
        self.assertEqual(self.change("post", "csv/preview/", {"csv": foreign}).status_code, 400)
        self.assertEqual(self.change("post", "csv/apply/", {"token": "forged"}).status_code, 400)
        self.assertEqual(Reservation.objects.get(pk=self.row["id"]).ip, "10.0.0.5")

    def test_delete_is_explicit_and_requires_confirmation(self):
        preview = self.change("post", "csv/preview/", {"csv": self.edited(action="delete")})
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["counts"]["delete"], 1)
        payload = {"token": preview.json()["token"]}
        self.assertEqual(self.change("post", "csv/apply/", payload).status_code, 400)
        payload["confirm_deletions"] = True
        self.assertEqual(self.change("post", "csv/apply/", payload).status_code, 200)
        self.assertFalse(Reservation.objects.filter(pk=self.row["id"]).exists())

    def test_export_escapes_spreadsheet_formulas_and_roundtrips(self):
        self.change("patch", f"reservations/{self.row['id']}/", {"description": "=1+1"})
        exported = self.export()
        self.assertIn("'=1+1", exported)
        preview = self.change("post", "csv/preview/", {"csv": exported})
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["counts"]["unchanged"], 1)

    def test_csrf_and_reader_permissions(self):
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.user)
        self.assertEqual(
            protected.post(
                self.base + "csv/preview/", "{}", content_type="application/json"
            ).status_code,
            403,
        )
        from dhcp_tool.models import Account, Role

        Account.objects.filter(user=self.user).update(role=Role.READER)
        from dhcp_tool.models import FirewallAccess

        FirewallAccess.objects.create(user=self.user, firewall_id=self.fw)
        self.assertEqual(self.client.get(self.base + "csv/export/").status_code, 200)
        self.assertEqual(self.change("post", "csv/preview/", {"csv": ""}).status_code, 403)

    def test_audit_failure_rolls_back_every_change(self):
        preview = self.change("post", "csv/preview/", {"csv": self.edited(ip="10.0.0.6")})
        self.assertEqual(preview.status_code, 200)
        with patch(
            "dhcp_tool.csv_views.AuditEvent.objects.create", side_effect=RuntimeError("test")
        ):
            self.assertEqual(
                self.change("post", "csv/apply/", {"token": preview.json()["token"]}).status_code,
                500,
            )
        self.assertEqual(Reservation.objects.get(pk=self.row["id"]).ip, "10.0.0.5")

    def test_malformed_header_is_a_validation_error(self):
        response = self.change("post", "csv/preview/", {"csv": '"unterminated'})
        self.assertEqual(response.status_code, 400)

    def test_create_and_missing_rows_do_not_delete_existing_reservations(self):
        csv_text = self.edited(id="", name="nowy-host", ip="10.0.0.7", mac="02:00:00:00:00:07")
        preview = self.change("post", "csv/preview/", {"csv": csv_text})
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["counts"]["create"], 1)
        self.assertEqual(
            self.change("post", "csv/apply/", {"token": preview.json()["token"]}).status_code, 200
        )
        self.assertEqual(Reservation.objects.filter(subnet__firewall_id=self.fw).count(), 2)

    def test_null_characters_and_invalid_unicode_are_rejected_before_preview(self):
        for value in ("null\x00text", "\ud800"):
            response = self.change("post", "csv/preview/", {"csv": self.edited(description=value)})
            self.assertEqual(response.status_code, 400)

    def test_preview_is_bound_to_user_firewall_revision_and_expiry(self):
        import time

        from django.contrib.auth import get_user_model

        from dhcp_tool.models import Account, Role

        preview = self.change("post", "csv/preview/", {"csv": self.edited(ip="10.0.0.6")}).json()
        payload = {"token": preview["token"]}
        other = get_user_model().objects.create_user("csv-other-admin")
        Account.objects.create(user=other, role=Role.ADMIN)
        self.client.force_login(other)
        self.assertEqual(self.change("post", "csv/apply/", payload).status_code, 400)
        self.client.force_login(self.user)
        with patch("django.core.signing.time.time", return_value=time.time() + 700):
            self.assertEqual(self.change("post", "csv/apply/", payload).status_code, 400)
        self.change("patch", "draft/", {"domain": "example.org"})
        self.assertEqual(self.change("post", "csv/apply/", payload).status_code, 409)

    def test_duplicate_rows_unknown_columns_and_oversized_csv_are_rejected(self):
        exported = self.export()
        lines = exported.splitlines()
        repeated = exported + lines[1] + "\n"
        self.assertEqual(self.change("post", "csv/preview/", {"csv": repeated}).status_code, 400)
        self.assertEqual(
            self.change(
                "post", "csv/preview/", {"csv": exported.replace("action,", "unknown,", 1)}
            ).status_code,
            400,
        )
        self.assertEqual(self.change("post", "csv/preview/", {"csv": "x" * 32769}).status_code, 413)
