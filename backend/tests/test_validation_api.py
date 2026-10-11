import hashlib
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from dhcp_tool.models import (
    Account,
    Artifact,
    AuditEvent,
    Draft,
    Firewall,
    FirewallAccess,
    Pool,
    Reservation,
    Role,
    Subnet,
    Version,
)
from dhcp_tool.syntax import SyntaxResult


@override_settings(DHCPD_PARSER_PATH=None)
class ValidationAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("validation-reader")
        Account.objects.create(user=self.user, role=Role.READER)
        self.fw = Firewall.objects.create(name="fw-validation", profile="R81.10")
        self.draft = Draft.objects.create(firewall=self.fw)
        FirewallAccess.objects.create(user=self.user, firewall=self.fw)
        self.subnet = Subnet.objects.create(
            firewall=self.fw, name="Biuro", cidr="192.0.2.0/24", options={"gateway": "192.0.2.1"}
        )
        Pool.objects.create(subnet=self.subnet, start="192.0.2.100", end="192.0.2.150")
        self.row = Reservation.objects.create(
            subnet=self.subnet, name="printer", ip="192.0.2.20", mac="00:11:22:33:44:55"
        )
        self.client.force_login(self.user)
        self.base = f"/api/v1/firewalls/{self.fw.pk}/"

    def post(self, path, data=None, revision="1"):
        return self.client.post(
            self.base + path,
            data or {},
            content_type="application/json",
            HTTP_X_CONFIG_REVISION=revision,
        )

    def test_validation_and_preview_are_readonly_and_report_exact_bytes(self):
        before = self.client.get(self.base + "draft/").json()
        checked = self.post("validation/")
        self.assertEqual(checked.status_code, 200)
        report = checked.json()
        self.assertTrue(report["data_validated"])
        self.assertEqual(report["syntax_status"], "parser_unavailable")
        self.assertEqual(report["gaia_compatibility"], "unverified")
        preview = self.post("preview/")
        self.assertEqual(preview.status_code, 200)
        content = preview.json()["content"].encode("ascii")
        self.assertIn(b"fixed-address 192.0.2.20;", content)
        self.assertEqual(report["sha256"], hashlib.sha256(content).hexdigest())
        self.assertEqual(report["artifact_bytes"], len(content))
        self.assertEqual(preview["Cache-Control"], "no-store")
        self.assertEqual(self.client.get(self.base + "draft/").json(), before)
        self.assertEqual(Version.objects.count(), 0)
        self.assertEqual(Artifact.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_revision_csrf_authentication_and_scope_are_required(self):
        self.assertEqual(self.post("validation/", revision="").status_code, 400)
        self.assertEqual(self.post("preview/", revision="2").status_code, 409)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(
            client.post(
                self.base + "validation/",
                {},
                content_type="application/json",
                HTTP_X_CONFIG_REVISION="1",
            ).status_code,
            403,
        )
        other = Firewall.objects.create(name="fw-other", profile="R82.10")
        self.assertEqual(
            self.client.post(
                f"/api/v1/firewalls/{other.pk}/preview/",
                {},
                content_type="application/json",
                HTTP_X_CONFIG_REVISION="1",
            ).status_code,
            404,
        )
        self.client.logout()
        self.assertEqual(self.post("preview/").status_code, 403)

    def test_empty_incomplete_and_inactive_pool_block_completion(self):
        for change in ("pool", "subnet", "empty"):
            with self.subTest(change=change):
                if change == "pool":
                    Pool.objects.filter(subnet=self.subnet).update(active=False)
                elif change == "subnet":
                    self.subnet.active = False
                    self.subnet.save()
                else:
                    self.subnet.delete()
                response = self.post("validation/")
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.json()["error"]["fields"])
                self.assertEqual(Version.objects.count(), 0)

    def test_invalid_stored_data_identifies_object_and_field(self):
        self.row.ip = "192.0.2.100"
        self.row.save()
        response = self.post("validation/")
        self.assertEqual(response.status_code, 400)
        fields = response.json()["error"]["fields"]
        self.assertIn(f"subnets.{self.subnet.pk}.reservations.{self.row.pk}.ip", fields)
        self.assertNotIn("192.0.2.100", response.content.decode())

    def test_clients_cannot_supply_parser_path_or_arbitrary_config(self):
        for body in (
            {"parser_path": "/tmp/untrusted"},
            {"content": 'include "secret";'},
            {"profile": "R82.10"},
        ):
            self.assertEqual(self.post("preview/", body).status_code, 400)

    def test_archived_firewall_still_allows_readonly_preview(self):
        self.fw.archived = True
        self.fw.save()
        self.assertEqual(self.post("preview/").status_code, 200)

    @override_settings(DHCPD_PARSER_PATH="/trusted/parser")
    def test_parser_statuses_are_reported_without_returning_failed_preview(self):
        for status, code, http in [
            ("syntax_checked", 0, 200),
            ("syntax_error", 1, 400),
            ("parser_error", 2, 503),
            ("parser_timeout", None, 503),
        ]:
            with (
                self.subTest(status=status),
                patch(
                    "dhcp_tool.validation.check_syntax",
                    return_value=SyntaxResult(status, "isc-dhcpd-test", code),
                ),
            ):
                response = self.post("preview/")
                self.assertEqual(response.status_code, http)
                result = response.json()
                self.assertEqual(result["syntax_status"], status)
                self.assertTrue(result["data_validated"])
                self.assertEqual(result["gaia_compatibility"], "unverified")
                if http != 200:
                    self.assertNotIn("content", result)

    def test_preview_hash_remains_bound_to_captured_revision_when_draft_changes(self):
        # Parser processing can outlive an edit; the response must retain the snapshot revision.
        def check(content, **kwargs):
            Draft.objects.filter(firewall=self.fw).update(
                revision=2, settings={"domain": "changed.example"}
            )
            return SyntaxResult("syntax_checked", "isc-dhcpd-test", 0)

        with patch("dhcp_tool.validation.check_syntax", side_effect=check):
            response = self.post("preview/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["revision"], 1)
        self.assertNotIn("changed.example", data["content"])
        self.assertEqual(
            data["sha256"], hashlib.sha256(data["content"].encode("ascii")).hexdigest()
        )
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.revision, 2)

    def test_rendered_descriptions_cannot_inject_directives(self):
        self.row.description = '";\ninclude "evil"; # comment'
        self.row.save()
        self.subnet.description = "deny unknown-clients;"
        self.subnet.save()
        response = self.post("preview/")
        self.assertEqual(response.status_code, 200)
        content = response.json()["content"]
        self.assertNotIn("include", content)
        self.assertNotIn("deny unknown-clients", content)
