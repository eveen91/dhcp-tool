import hashlib
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from dhcp_tool.models import (
    Account,
    Artifact,
    AuditEvent,
    Deployment,
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
class VersionAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("version-editor")
        Account.objects.create(user=self.user, role=Role.EDITOR)
        self.fw = Firewall.objects.create(name="fw-version", profile="R81.10")
        Draft.objects.create(firewall=self.fw)
        FirewallAccess.objects.create(user=self.user, firewall=self.fw)
        self.subnet = Subnet.objects.create(firewall=self.fw, name="Biuro", cidr="192.0.2.0/24")
        Pool.objects.create(subnet=self.subnet, start="192.0.2.100", end="192.0.2.150")
        self.row = Reservation.objects.create(
            subnet=self.subnet, name="printer", ip="192.0.2.20", mac="00:11:22:33:44:55"
        )
        self.client.force_login(self.user)
        self.base = f"/api/v1/firewalls/{self.fw.pk}/"

    def publish(self, description="Pierwsza", revision="1"):
        return self.client.post(
            self.base + "versions/",
            {"description": description},
            content_type="application/json",
            HTTP_X_CONFIG_REVISION=revision,
        )

    def published(self):
        response = self.publish()
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_publish_freezes_snapshot_author_exact_bytes_and_report(self):
        data = self.published()
        version = Version.objects.get(pk=data["id"])
        artifact = Artifact.objects.get(version=version)
        self.assertEqual(version.number, 1)
        self.assertEqual(version.author_id, self.user.pk)
        self.assertEqual(version.snapshot["firewall"]["name"], "fw-version")
        self.assertEqual(version.snapshot["subnets"][0]["reservations"][0]["id"], str(self.row.pk))
        self.assertEqual(artifact.validation["syntax_status"], "parser_unavailable")
        self.assertEqual(artifact.sha256, hashlib.sha256(bytes(artifact.content)).hexdigest())
        self.assertIn(str(version.pk).encode(), bytes(artifact.content))
        self.assertEqual(Draft.objects.get(firewall=self.fw).revision, 1)
        self.assertEqual(AuditEvent.objects.get().operation, "publish")

    def test_download_never_regenerates_after_metadata_and_generator_changes(self):
        data = self.published()
        original = bytes(Artifact.objects.get(version_id=data["id"]).content)
        Firewall.objects.filter(pk=self.fw.pk).update(name="renamed-fw", profile="R82.10")
        self.row.delete()
        with patch(
            "dhcp_tool.validation.prepare_artifact",
            side_effect=AssertionError("must not regenerate"),
        ):
            downloaded = self.client.get(self.base + f"versions/{data['id']}/artifact/")
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, original)
        self.assertEqual(downloaded["Content-Disposition"], 'attachment; filename="dhcpd.conf"')
        self.assertEqual(downloaded["X-Content-SHA256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(downloaded["Cache-Control"], "no-store")
        self.assertEqual(Deployment.objects.count(), 0)

    def test_description_revision_and_invalid_data_block_publication(self):
        for value in ("", "   ", "x" * 2001):
            self.assertEqual(self.publish(value).status_code, 400)
        self.assertEqual(self.publish(revision="").status_code, 400)
        self.assertEqual(self.publish(revision="2").status_code, 409)
        Pool.objects.filter(subnet=self.subnet).delete()
        self.assertEqual(self.publish().status_code, 400)
        self.assertEqual(Version.objects.count(), 0)

    def test_failed_artifact_or_audit_write_leaves_no_partial_version(self):
        for manager in (Artifact.objects, AuditEvent.objects):
            with (
                self.subTest(model=manager.model.__name__),
                patch.object(manager, "create", side_effect=DatabaseError("private failure")),
            ):
                self.assertEqual(self.publish().status_code, 500)
                self.assertEqual(Version.objects.count(), 0)
                self.assertEqual(Artifact.objects.count(), 0)
        self.assertEqual(self.published()["number"], 1)

    def test_parser_failure_cannot_publish(self):
        for status, http in [("syntax_error", 400), ("parser_error", 503), ("parser_timeout", 503)]:
            with (
                self.subTest(status=status),
                patch("dhcp_tool.validation.check_syntax", return_value=SyntaxResult(status)),
            ):
                self.assertEqual(self.publish().status_code, http)
                self.assertEqual(Version.objects.count(), 0)

    def test_edit_during_parser_prevents_stale_publication(self):
        def check(content, **kwargs):
            Draft.objects.filter(firewall=self.fw).update(revision=2)
            return SyntaxResult("syntax_checked")

        with patch("dhcp_tool.validation.check_syntax", side_effect=check):
            response = self.publish()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["current_revision"], 2)
        self.assertEqual(Version.objects.count(), 0)

    def test_access_revoked_during_parser_prevents_commit(self):
        def check(content, **kwargs):
            FirewallAccess.objects.filter(user=self.user, firewall=self.fw).delete()
            return SyntaxResult("syntax_checked")

        with patch("dhcp_tool.validation.check_syntax", side_effect=check):
            self.assertEqual(self.publish().status_code, 404)
        self.assertEqual(Version.objects.count(), 0)

    def test_history_and_semantic_diff_distinguish_rename_by_uuid(self):
        first = self.published()
        self.row.name = "renamed-printer"
        self.row.save()
        Draft.objects.filter(firewall=self.fw).update(revision=2)
        second = self.publish("Zmiana nazwy", "2")
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.json()["number"], 2)
        page = self.client.get(self.base + "versions/", {"page_size": 1}).json()
        self.assertEqual(page["count"], 2)
        self.assertEqual(page["results"][0]["id"], second.json()["id"])
        self.assertIsNotNone(page["next"])
        detail = self.client.get(self.base + f"versions/{first['id']}/").json()
        self.assertEqual(detail["snapshot"]["subnets"][0]["reservations"][0]["name"], "printer")
        diff = self.client.get(
            self.base + "diff/", {"from": first["id"], "to": second.json()["id"]}
        )
        self.assertEqual(diff.status_code, 200)
        self.assertIn("-host printer", diff.json()["text"])
        self.assertEqual(
            diff.json()["semantic"],
            [
                {
                    "kind": "changed",
                    "object_type": "reservation",
                    "object_id": str(self.row.pk),
                    "field": "name",
                    "before": "printer",
                    "after": "renamed-printer",
                }
            ],
        )

    def test_default_diff_handles_absence_and_uses_successful_deployment(self):
        first = self.published()
        second = self.publish("Druga").json()
        response = self.client.get(self.base + "diff/", {"to": second["id"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["baseline_reason"], "no_successful_deployment")
        Deployment.objects.create(
            version_id=first["id"],
            operator=self.user,
            status="successful",
            occurred_at=timezone.now(),
        )
        Deployment.objects.create(
            version_id=second["id"], operator=self.user, status="failed", occurred_at=timezone.now()
        )
        data = self.client.get(self.base + "diff/", {"to": second["id"]}).json()
        self.assertEqual(data["from"]["id"], first["id"])
        self.assertTrue(data["manual_deployment"])

    def test_restore_preserves_scalar_and_multiple_interface_addresses(self):
        for addresses in ("192.0.2.2", ["192.0.2.2", "192.0.2.3"]):
            with self.subTest(addresses=addresses):
                self.subnet.options = {"interface_address": addresses}
                self.subnet.save()
                first = self.published()
                self.subnet.options = {}
                self.subnet.save()
                response = self.client.post(
                    self.base + f"versions/{first['id']}/restore/",
                    {},
                    content_type="application/json",
                    HTTP_X_CONFIG_REVISION="1",
                )
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json()["subnets"][0]["interface_address"], addresses)
                Draft.objects.filter(firewall=self.fw).update(revision=1)

    def test_restore_keeps_ids_history_and_requires_current_revision(self):
        first = self.published()
        original = bytes(Artifact.objects.get(version_id=first["id"]).content)
        identifier = str(self.row.pk)
        self.row.delete()
        Draft.objects.filter(firewall=self.fw).update(revision=2)
        path = self.base + f"versions/{first['id']}/restore/"
        self.assertEqual(
            self.client.post(
                path, {}, content_type="application/json", HTTP_X_CONFIG_REVISION="1"
            ).status_code,
            409,
        )
        response = self.client.post(
            path, {}, content_type="application/json", HTTP_X_CONFIG_REVISION="2"
        )
        self.assertEqual(response.status_code, 200)
        restored = response.json()
        self.assertEqual(restored["revision"], 3)
        self.assertEqual(restored["base_version_id"], first["id"])
        self.assertEqual(restored["subnets"][0]["reservations"][0]["id"], identifier)
        self.assertEqual(Version.objects.count(), 1)
        self.assertEqual(bytes(Artifact.objects.get(version_id=first["id"]).content), original)
        self.assertEqual(AuditEvent.objects.filter(operation="restore").count(), 1)

    def test_foreign_versions_are_denied_even_with_both_grants(self):
        first = self.published()
        other = Firewall.objects.create(name="fw-other", profile="R82.10")
        FirewallAccess.objects.create(user=self.user, firewall=other)
        foreign = f"/api/v1/firewalls/{other.pk}/"
        for suffix in (f"versions/{first['id']}/", f"versions/{first['id']}/artifact/"):
            self.assertEqual(self.client.get(foreign + suffix).status_code, 404)
        self.assertEqual(
            self.client.get(
                foreign + "diff/", {"from": first["id"], "to": first["id"]}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                foreign + f"versions/{first['id']}/restore/",
                {},
                content_type="application/json",
                HTTP_X_CONFIG_REVISION="1",
            ).status_code,
            404,
        )

    def test_reader_operator_csrf_and_archive_boundaries(self):
        first = self.published()
        account = self.user.access_account
        for role in (Role.READER, Role.OPERATOR):
            account.role = role
            account.save()
            self.assertEqual(
                self.client.get(self.base + f"versions/{first['id']}/artifact/").status_code, 200
            )
            self.assertEqual(self.publish().status_code, 403)
            self.assertEqual(
                self.client.post(
                    self.base + f"versions/{first['id']}/restore/",
                    {},
                    content_type="application/json",
                    HTTP_X_CONFIG_REVISION="1",
                ).status_code,
                403,
            )
        account.role = Role.EDITOR
        account.save()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(
            client.post(
                self.base + "versions/",
                {"description": "Zmiana"},
                content_type="application/json",
                HTTP_X_CONFIG_REVISION="1",
            ).status_code,
            403,
        )
        Firewall.objects.filter(pk=self.fw.pk).update(archived=True)
        self.assertEqual(self.publish().status_code, 409)
        self.assertEqual(
            self.client.get(self.base + f"versions/{first['id']}/artifact/").status_code, 200
        )

    def test_immutability_is_enforced_through_api_and_database(self):
        first = self.published()
        for suffix in (f"versions/{first['id']}/", f"versions/{first['id']}/artifact/"):
            self.assertEqual(
                self.client.patch(
                    self.base + suffix, {}, content_type="application/json"
                ).status_code,
                405,
            )
            self.assertEqual(self.client.delete(self.base + suffix).status_code, 405)
        for action in (
            lambda: Version.objects.filter(pk=first["id"]).update(description="tampered"),
            lambda: Artifact.objects.filter(version_id=first["id"]).update(content=b"tampered"),
            lambda: Artifact.objects.filter(version_id=first["id"]).delete(),
        ):
            with self.assertRaises(IntegrityError), transaction.atomic():
                action()

    def test_semantic_diff_reports_settings_pool_and_added_removed_reservations(self):
        first = self.published()
        old_id = str(self.row.pk)
        self.row.delete()
        new_row = Reservation.objects.create(
            subnet=self.subnet, name="server", mac="00:11:22:33:44:66", ip="192.0.2.30"
        )
        Pool.objects.filter(subnet=self.subnet).update(end="192.0.2.160")
        Draft.objects.filter(firewall=self.fw).update(
            revision=2, settings={"domain": "changed.example"}
        )
        second = self.publish("Zmiana", "2").json()
        data = self.client.get(
            self.base + "diff/", {"from": first["id"], "to": second["id"]}
        ).json()
        changes = data["semantic"]
        self.assertTrue(
            any(
                c["object_type"] == "pool" and c["field"] == "end" and c["after"] == "192.0.2.160"
                for c in changes
            )
        )
        self.assertTrue(
            any(
                c["object_type"] == "settings"
                and c["field"] == "domain"
                and c["after"] == "changed.example"
                for c in changes
            )
        )
        self.assertTrue(any(c["kind"] == "removed" and c["object_id"] == old_id for c in changes))
        self.assertTrue(
            any(c["kind"] == "added" and c["object_id"] == str(new_row.pk) for c in changes)
        )

    def test_restore_audit_failure_preserves_current_draft(self):
        first = self.published()
        self.row.name = "new-name"
        self.row.save()
        Draft.objects.filter(firewall=self.fw).update(revision=2)
        before = self.client.get(self.base + "draft/").json()
        with patch.object(AuditEvent.objects, "create", side_effect=DatabaseError("failure")):
            response = self.client.post(
                self.base + f"versions/{first['id']}/restore/",
                {},
                content_type="application/json",
                HTTP_X_CONFIG_REVISION="2",
            )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.client.get(self.base + "draft/").json(), before)

    def test_missing_diff_parameters_duplicate_identifiers_and_unknown_filters(self):
        first = self.published()
        self.assertEqual(self.client.get(self.base + "diff/").status_code, 400)
        self.assertEqual(
            self.client.get(self.base + "diff/", {"to": [first["id"], first["id"]]}).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(self.base + "versions/", {"ordering": "author__password"}).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(self.base + "versions/", {"page_size": 101}).status_code, 400
        )
        self.assertEqual(
            self.client.get(self.base + "versions/", {"search": "Pierwsza"}).json()["count"], 1
        )

    def test_numbers_and_identical_addresses_remain_independent_per_firewall(self):
        first = self.published()
        self.assertEqual(self.publish("Druga").json()["number"], 2)
        other = Firewall.objects.create(name="fw-other", profile="R82.10")
        FirewallAccess.objects.create(user=self.user, firewall=other)
        Draft.objects.create(firewall=other)
        subnet = Subnet.objects.create(firewall=other, name="LAN", cidr="192.0.2.0/24")
        Pool.objects.create(subnet=subnet, start="192.0.2.100", end="192.0.2.150")
        Reservation.objects.create(
            subnet=subnet, name="printer", ip="192.0.2.20", mac="00:11:22:33:44:55"
        )
        self.base = f"/api/v1/firewalls/{other.pk}/"
        second = self.published()
        self.assertEqual(second["number"], 1)
        self.assertNotEqual(first["sha256"], second["sha256"])
        self.assertEqual(Version.objects.filter(firewall=self.fw).count(), 2)
        self.assertEqual(Version.objects.filter(firewall=other).count(), 1)
        self.assertEqual(
            self.client.get(
                self.base + "diff/", {"from": first["id"], "to": second["id"]}
            ).status_code,
            404,
        )

    def test_account_deactivation_during_parser_prevents_commit(self):
        def check(content, **kwargs):
            get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
            return SyntaxResult("syntax_checked")

        with patch("dhcp_tool.validation.check_syntax", side_effect=check):
            self.assertEqual(self.publish().status_code, 403)
        self.assertEqual(Version.objects.count(), 0)

    def test_role_revocation_during_parser_prevents_commit(self):
        def check(content, **kwargs):
            Account.objects.filter(user=self.user).update(role=Role.READER)
            return SyntaxResult("syntax_checked")

        with patch("dhcp_tool.validation.check_syntax", side_effect=check):
            self.assertEqual(self.publish().status_code, 403)
        self.assertEqual(Version.objects.count(), 0)

    def test_real_parser_accepts_published_header_and_complete_artifact(self):
        import os

        parser = os.environ.get("DHCPD_PARSER_PATH")
        if not parser:
            self.skipTest("No real ISC parser configured")
        with override_settings(DHCPD_PARSER_PATH=parser):
            first = self.published()
        self.assertEqual(first["validation"]["syntax_status"], "syntax_checked")
        self.assertIsNotNone(first["validation"]["parser_version"])

    def test_password_change_during_parser_prevents_commit(self):
        def check(content, **kwargs):
            user = get_user_model().objects.get(pk=self.user.pk)
            user.set_password("changed-local-secret-123")
            user.save(update_fields=["password"])
            return SyntaxResult("syntax_checked")

        with patch("dhcp_tool.validation.check_syntax", side_effect=check):
            self.assertEqual(self.publish().status_code, 403)
        self.assertEqual(Version.objects.count(), 0)
