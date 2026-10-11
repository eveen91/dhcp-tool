import csv
import io
import json

import test_draft
from django.test import TestCase

from dhcp_tool.models import Firewall, Reservation, Subnet


class ConfigurationCSVTests(TestCase):
    change = test_draft.DraftAPITests.change
    subnet = test_draft.DraftAPITests.subnet
    pool = test_draft.DraftAPITests.pool
    reservation = test_draft.DraftAPITests.reservation

    def setUp(self):
        test_draft.DraftAPITests.setUp(self)
        self.sid = self.subnet()
        self.pool(self.sid)
        self.rid = self.reservation(self.sid).json()["id"]

    def csv(self, edit=None):
        response = self.client.get(self.base + "csv/config/export/")
        self.assertEqual(response.status_code, 200)
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        if edit:
            rows = edit(rows)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()

    def preview(self, content):
        response = self.change("post", "csv/config/preview/", {"csv": content})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_cluster_addresses_round_trip_through_full_csv(self):
        addresses = ["10.0.0.2", "10.0.0.3"]

        def edit(rows):
            for row in rows:
                if row["kind"] == "subnet":
                    row["options"] = json.dumps(
                        {"gateway": "10.0.0.1", "interface_address": addresses}
                    )
            return rows

        preview = self.preview(self.csv(edit))
        response = self.change("post", "csv/config/apply/", {"token": preview["token"]})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["subnets"][0]["interface_address"], addresses)
        exported = list(csv.DictReader(io.StringIO(self.csv())))
        options = json.loads(next(row for row in exported if row["kind"] == "subnet")["options"])
        self.assertEqual(options["interface_address"], addresses)

    def test_exports_entire_configuration_and_imports_options_atomically(self):
        def edit(rows):
            for row in rows:
                if row["kind"] == "settings":
                    row["options"] = '{"domain":"example.org","dns":["10.0.0.2"]}'
                if row["kind"] == "pool":
                    row["end"] = "10.0.0.99"
                if row["kind"] == "subnet":
                    row["name"] = "Biuro Łódź"
                if row["kind"] == "reservation":
                    row["ip"] = "10.0.0.6"
            return rows

        before = self.client.get(self.base + "draft/").json()
        preview = self.preview(self.csv(edit))
        self.assertEqual(preview["counts"]["update"], 4)
        self.assertEqual(self.client.get(self.base + "draft/").json(), before)
        response = self.change("post", "csv/config/apply/", {"token": preview["token"]})
        self.assertEqual(response.status_code, 200)
        after = response.json()
        self.assertEqual(after["settings"]["domain"], "example.org")
        self.assertEqual(after["subnets"][0]["pool"]["end"], "10.0.0.99")
        self.assertEqual(after["subnets"][0]["reservations"][0]["id"], self.rid)
        self.assertEqual(after["subnets"][0]["created_at"], before["subnets"][0]["created_at"])

    def test_subnet_deletion_previews_every_affected_child(self):
        def edit(rows):
            row = next(row for row in rows if row["kind"] == "subnet")
            row["action"] = "delete"
            return [row]

        preview = self.preview(self.csv(edit))
        self.assertEqual(preview["counts"]["delete"], 3)
        self.assertEqual(
            {change["kind"] for change in preview["changes"]}, {"subnet", "pool", "reservation"}
        )
        self.assertEqual(
            self.change("post", "csv/config/apply/", {"token": preview["token"]}).status_code, 400
        )
        self.assertTrue(Subnet.objects.filter(pk=self.sid).exists())
        self.assertEqual(
            self.change(
                "post", "csv/config/apply/", {"token": preview["token"], "confirm_deletions": True}
            ).status_code,
            200,
        )
        self.assertFalse(Reservation.objects.filter(pk=self.rid).exists())

    def test_adds_subnet_pool_and_reservation_with_blank_ids(self):
        def edit(rows):
            rows = [row for row in rows if row["kind"] in ["subnet", "pool", "reservation"]]
            for row in rows:
                row["id"] = ""
                row["subnet_cidr"] = "10.1.0.0/24"
                if row["kind"] == "subnet":
                    row["options"] = '{"gateway":"10.1.0.1"}'
                if row["kind"] == "pool":
                    row["start"] = "10.1.0.10"
                    row["end"] = "10.1.0.99"
                if row["kind"] == "reservation":
                    row["name"] = "new-host"
                    row["ip"] = "10.1.0.5"
                    row["mac"] = "02:00:00:00:01:05"
            return rows

        preview = self.preview(self.csv(edit))
        self.assertEqual(preview["counts"]["create"], 3)
        self.assertEqual(
            self.change("post", "csv/config/apply/", {"token": preview["token"]}).status_code, 200
        )
        self.assertEqual(Subnet.objects.filter(firewall_id=self.fw).count(), 2)

    def test_profile_changes_require_admin_and_unknown_directives_are_rejected(self):
        def edit(rows):
            next(row for row in rows if row["kind"] == "subnet")["options"] = (
                '{"arbitrary_directive":"foo"}'
            )
            return rows

        self.assertEqual(
            self.change("post", "csv/config/preview/", {"csv": self.csv(edit)}).status_code, 400
        )

        def profile(rows):
            next(row for row in rows if row["kind"] == "firewall")["options"] = (
                '{"profile":"R82.10","location":"","management_address":null}'
            )
            return rows

        preview = self.preview(self.csv(profile))
        self.assertEqual(
            self.change("post", "csv/config/apply/", {"token": preview["token"]}).status_code, 200
        )
        self.assertEqual(Firewall.objects.get(pk=self.fw).profile, "R82.10")

    def test_editor_cannot_change_firewall_and_preview_is_revision_bound(self):
        from dhcp_tool.models import Account, FirewallAccess, Role

        content = self.csv(
            lambda rows: [
                dict(row, name="renamed") if row["kind"] == "firewall" else row for row in rows
            ]
        )
        Account.objects.filter(user=self.user).update(role=Role.EDITOR)
        FirewallAccess.objects.create(user=self.user, firewall_id=self.fw)
        self.assertEqual(
            self.change("post", "csv/config/preview/", {"csv": content}).status_code, 403
        )
        preview = self.preview(self.csv())
        self.change("patch", "draft/", {"domain": "changed.example"})
        self.assertEqual(
            self.change("post", "csv/config/apply/", {"token": preview["token"]}).status_code, 409
        )

    def test_failed_audit_rolls_back_entire_import(self):
        from unittest.mock import patch

        before = self.client.get(self.base + "draft/").json()
        preview = self.preview(
            self.csv(
                lambda rows: [
                    dict(row, name="changed-host") if row["kind"] == "reservation" else row
                    for row in rows
                ]
            )
        )
        with patch(
            "dhcp_tool.csv_config_views.AuditEvent.objects.create",
            side_effect=RuntimeError("failure"),
        ):
            self.assertEqual(
                self.change("post", "csv/config/apply/", {"token": preview["token"]}).status_code,
                500,
            )
        self.assertEqual(self.client.get(self.base + "draft/").json(), before)

    def test_roundtrip_is_unchanged_and_token_is_not_transferable(self):
        preview = self.preview(self.csv())
        self.assertEqual(preview["changes"], [])
        token = preview["token"]
        self.assertEqual(
            self.change("post", "csv/config/apply/", {"token": token + "tamper"}).status_code, 400
        )
        from django.contrib.auth import get_user_model

        from dhcp_tool.models import Account, Role

        other = get_user_model().objects.create_user("csv-other")
        Account.objects.create(user=other, role=Role.ADMIN)
        self.client.force_login(other)
        self.assertEqual(
            self.change("post", "csv/config/apply/", {"token": token}).status_code, 400
        )
