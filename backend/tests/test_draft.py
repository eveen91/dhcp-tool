from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from dhcp_tool.models import Account, FirewallAccess, Role


class DraftAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("draft-admin")
        Account.objects.create(user=self.user, role=Role.ADMIN)
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/v1/firewalls/",
            {"name": "fw-draft", "profile": "R81.10"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.fw = response.json()["id"]
        self.base = f"/api/v1/firewalls/{self.fw}/"

    def change(self, method, path, data=None, revision=None):
        if revision is None:
            revision = self.client.get(self.base + "draft/").json()["revision"]
        return getattr(self.client, method)(
            self.base + path,
            data or {},
            content_type="application/json",
            HTTP_X_CONFIG_REVISION=str(revision),
        )

    def subnet(self):
        response = self.change(
            "post", "subnets/", {"name": "Biuro", "cidr": "10.0.0.0/24", "gateway": "10.0.0.1"}
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def pool(self, subnet):
        response = self.change(
            "put", f"subnets/{subnet}/pool/", {"start": "10.0.0.10", "end": "10.0.0.100"}
        )
        self.assertEqual(response.status_code, 200)

    def reservation(self, subnet):
        return self.change(
            "post",
            "reservations/",
            {"subnet_id": subnet, "name": "drukarka", "mac": "AA-BB-CC-DD-EE-01", "ip": "10.0.0.5"},
        )

    def test_cluster_addresses_save_and_protect_both_members(self):
        subnet = self.subnet()
        addresses = ["10.0.0.2", "10.0.0.3"]
        response = self.change("patch", f"subnets/{subnet}/", {"interface_address": addresses})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["interface_address"], addresses)
        before = self.client.get(self.base + "draft/").json()
        for address in addresses:
            response = self.change(
                "put", f"subnets/{subnet}/pool/", {"start": address, "end": "10.0.0.100"}
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.client.get(self.base + "draft/").json(), before)
        self.assertEqual(
            self.change("patch", f"subnets/{subnet}/", {"interface_address": None}).status_code, 200
        )
        self.assertNotIn(
            "interface_address", self.client.get(self.base + "draft/").json()["subnets"][0]
        )

    def test_invalid_cluster_member_errors_identify_interface_field(self):
        subnet = self.subnet()
        response = self.change(
            "patch", f"subnets/{subnet}/", {"interface_address": ["10.0.0.2", "10.0.1.3"]}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("subnets[0].interface_address", response.json()["error"]["fields"])

    def test_create_initializes_draft_and_audit(self):
        self.assertEqual(self.client.get(self.base + "draft/").json()["revision"], 1)
        from dhcp_tool.models import AuditEvent

        event = AuditEvent.objects.get(firewall_id=self.fw)
        self.assertEqual(event.actor_id, self.user.pk)
        self.assertIsNone(event.before)
        self.assertEqual(event.after["name"], "fw-draft")

    def test_crud_stable_ids_normalization_and_audit(self):
        subnet = self.subnet()
        self.pool(subnet)
        response = self.reservation(subnet)
        self.assertEqual(response.status_code, 201)
        row = response.json()
        self.assertEqual(row["mac"], "aa:bb:cc:dd:ee:01")
        changed = self.change("patch", f"reservations/{row['id']}/", {"description": "Nowy opis"})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["id"], row["id"])
        from dhcp_tool.models import AuditEvent

        event = AuditEvent.objects.filter(firewall_id=self.fw).latest("created_at")
        self.assertEqual(event.before["description"], "")
        self.assertEqual(event.after["description"], "Nowy opis")
        self.assertEqual(self.change("delete", f"reservations/{row['id']}/").status_code, 204)
        self.assertEqual(self.client.get(self.base + "reservations/").json()["count"], 0)

    def test_stale_and_missing_revision_do_not_change_data(self):
        self.subnet()
        response = self.change("patch", "draft/", {"domain": "example.org"}, 1)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["current_revision"], 2)
        self.assertEqual(
            self.client.patch(
                self.base + "draft/", {"domain": "example.org"}, content_type="application/json"
            ).status_code,
            400,
        )
        self.assertNotIn("domain", self.client.get(self.base + "draft/").json()["settings"])

    def test_invalid_mutations_roll_back_revision_and_audit(self):
        subnet = self.subnet()
        self.pool(subnet)
        self.assertEqual(self.reservation(subnet).status_code, 201)
        before = self.client.get(self.base + "draft/").json()
        from dhcp_tool.models import AuditEvent

        count = AuditEvent.objects.count()
        self.assertEqual(self.reservation(subnet).status_code, 400)
        self.assertEqual(
            self.change(
                "put", f"subnets/{subnet}/pool/", {"start": "10.0.0.1", "end": "10.0.0.20"}
            ).status_code,
            400,
        )
        self.assertEqual(self.client.get(self.base + "draft/").json(), before)
        self.assertEqual(AuditEvent.objects.count(), count)

    def test_foreign_path_and_json_relationship_are_rejected(self):
        subnet = self.subnet()
        other = self.client.post(
            "/api/v1/firewalls/",
            {"name": "fw-other", "profile": "R82.10"},
            content_type="application/json",
        ).json()["id"]
        foreign = f"/api/v1/firewalls/{other}/"
        for method, suffix, data in [
            ("patch", f"subnets/{subnet}/", {"name": "changed"}),
            (
                "post",
                "reservations/",
                {"subnet_id": subnet, "name": "host", "ip": "10.0.0.5", "mac": "00:11:22:33:44:55"},
            ),
        ]:
            self.assertEqual(
                getattr(self.client, method)(
                    foreign + suffix,
                    data,
                    content_type="application/json",
                    HTTP_X_CONFIG_REVISION="1",
                ).status_code,
                404,
            )
        self.assertEqual(
            self.client.get(foreign + "reservations/", {"subnet_id": subnet}).status_code, 404
        )

    def test_identical_addresses_on_two_devices_are_independent(self):
        subnet = self.subnet()
        self.pool(subnet)
        self.assertEqual(self.reservation(subnet).status_code, 201)
        other = self.client.post(
            "/api/v1/firewalls/",
            {"name": "fw-other", "profile": "R82.10"},
            content_type="application/json",
        ).json()["id"]
        self.base = f"/api/v1/firewalls/{other}/"
        subnet = self.subnet()
        self.pool(subnet)
        self.assertEqual(self.reservation(subnet).status_code, 201)

    def test_archive_preserves_children_and_blocks_edit(self):
        subnet = self.subnet()
        self.assertEqual(self.change("patch", "", {"archived": True}).status_code, 200)
        self.assertEqual(self.change("patch", f"subnets/{subnet}/", {"name": "X"}).status_code, 409)
        self.assertEqual(self.client.get(self.base + "subnets/").json()["count"], 1)
        self.assertEqual(self.change("patch", "", {"archived": False}).status_code, 200)
        self.assertEqual(self.client.delete(self.base).status_code, 405)

    def test_role_boundaries(self):
        account = self.user.access_account
        account.role = Role.READER
        account.save()
        FirewallAccess.objects.create(user=self.user, firewall_id=self.fw)
        self.assertEqual(
            self.change("post", "subnets/", {"name": "X", "cidr": "10.0.0.0/24"}).status_code, 403
        )
        account.role = Role.EDITOR
        account.save()
        self.assertEqual(self.change("patch", "", {"name": "other"}).status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/v1/firewalls/",
                {"name": "other", "profile": "R81.10"},
                content_type="application/json",
            ).status_code,
            403,
        )
        self.subnet()

    def test_search_pagination_and_numeric_ip_order(self):
        subnet = self.subnet()
        self.pool(subnet)
        for name, ip, mac in [
            ("host-two", "10.0.0.2", "00:11:22:33:44:02"),
            ("host-nine", "10.0.0.9", "00:11:22:33:44:09"),
        ]:
            self.assertEqual(
                self.change(
                    "post",
                    "reservations/",
                    {"subnet_id": subnet, "name": name, "ip": ip, "mac": mac},
                ).status_code,
                201,
            )
        rows = self.client.get(
            self.base + "reservations/", {"ordering": "ip", "page_size": "1"}
        ).json()
        self.assertEqual(rows["results"][0]["ip"], "10.0.0.2")
        self.assertIsNotNone(rows["next"])
        self.assertEqual(
            self.client.get(self.base + "reservations/", {"search": "44:09"}).json()["count"], 1
        )
        self.assertEqual(
            self.client.get(self.base + "reservations/", {"ordering": "password"}).status_code, 400
        )

    def test_delete_subnet_cascades_draft_children_and_keeps_audit(self):
        subnet = self.subnet()
        self.pool(subnet)
        self.assertEqual(self.reservation(subnet).status_code, 201)
        self.assertEqual(self.change("delete", f"subnets/{subnet}/").status_code, 204)
        self.assertEqual(self.client.get(self.base + "draft/").json()["subnets"], [])
        from dhcp_tool.models import AuditEvent

        event = AuditEvent.objects.filter(firewall_id=self.fw).latest("created_at")
        self.assertEqual(len(event.before["reservations"]), 1)
        self.assertIsNone(event.after)

    def test_invalid_inactive_data_and_injection_rejected(self):
        for data in [
            {"name": "X", "cidr": "bad", "active": False},
            {"name": "X", "cidr": "10.0.0.0/31"},
            {"name": "X", "cidr": "10.0.0.0/24", "firewall_id": self.fw},
        ]:
            self.assertEqual(self.change("post", "subnets/", data).status_code, 400)
        self.assertEqual(
            self.change("patch", "draft/", {"domain": 'bad";\ninclude "secret'}).status_code, 400
        )

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(
            client.post(
                self.base + "subnets/",
                {"name": "X", "cidr": "10.0.0.0/24"},
                content_type="application/json",
                HTTP_X_CONFIG_REVISION="1",
            ).status_code,
            403,
        )

    def test_metadata_updates_revision_and_preserves_id(self):
        response = self.change(
            "patch",
            "",
            {
                "profile": "R82.10",
                "description": "Warszawa",
                "location": "DC1",
                "management_address": "192.168.1.2",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.fw)
        self.assertEqual(self.client.get(self.base + "draft/").json()["revision"], 2)

    def test_global_settings_clear_and_inherited_lease_validation(self):
        self.assertEqual(
            self.change(
                "patch",
                "draft/",
                {"domain": "example.org", "default_lease_time": 100, "max_lease_time": 200},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.change("patch", "draft/", {"default_lease_time": 300}).status_code, 400
        )
        self.assertEqual(self.change("patch", "draft/", {"domain": None}).status_code, 200)
        self.assertNotIn("domain", self.client.get(self.base + "draft/").json()["settings"])

    def test_pool_put_updates_single_pool_and_delete_preserves_reservations(self):
        subnet = self.subnet()
        self.pool(subnet)
        self.assertEqual(self.reservation(subnet).status_code, 201)
        first = self.client.get(self.base + f"subnets/{subnet}/pool/").json()["id"]
        response = self.change(
            "put", f"subnets/{subnet}/pool/", {"start": "10.0.0.20", "end": "10.0.0.100"}
        )
        self.assertEqual(response.json()["id"], first)
        self.assertEqual(self.change("delete", f"subnets/{subnet}/pool/").status_code, 204)
        self.assertEqual(self.client.get(self.base + "reservations/").json()["count"], 1)
        self.assertEqual(self.client.get(self.base + f"subnets/{subnet}/pool/").status_code, 404)

    def test_reservation_cannot_be_moved_to_foreign_subnet(self):
        subnet = self.subnet()
        row = self.reservation(subnet).json()
        other = self.client.post(
            "/api/v1/firewalls/",
            {"name": "fw-other", "profile": "R82.10"},
            content_type="application/json",
        ).json()["id"]
        response = self.client.post(
            f"/api/v1/firewalls/{other}/subnets/",
            {"name": "other", "cidr": "10.0.0.0/24"},
            content_type="application/json",
            HTTP_X_CONFIG_REVISION="1",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            self.change(
                "patch", f"reservations/{row['id']}/", {"subnet_id": response.json()["id"]}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(self.base + f"reservations/{row['id']}/").json()["subnet_id"], subnet
        )

    def test_scoped_editor_cannot_read_or_write_unassigned_device(self):
        other = self.client.post(
            "/api/v1/firewalls/",
            {"name": "fw-other", "profile": "R82.10"},
            content_type="application/json",
        ).json()["id"]
        account = self.user.access_account
        account.role = Role.EDITOR
        account.save()
        FirewallAccess.objects.create(user=self.user, firewall_id=self.fw)
        for method, path, data in [
            ("get", "draft/", {}),
            ("post", "subnets/", {"name": "other", "cidr": "10.0.0.0/24"}),
            ("get", "reservations/", {}),
        ]:
            response = getattr(self.client, method)(
                f"/api/v1/firewalls/{other}/" + path,
                data,
                content_type="application/json",
                HTTP_X_CONFIG_REVISION="1",
            )
            self.assertEqual(response.status_code, 404)

    def test_audit_storage_failure_rolls_back_entire_mutation(self):
        from unittest.mock import patch

        from django.db import DatabaseError

        from dhcp_tool.models import AuditEvent, Subnet

        with patch.object(
            AuditEvent.objects, "create", side_effect=DatabaseError("secret database diagnostic")
        ):
            response = self.change("post", "subnets/", {"name": "Biuro", "cidr": "10.0.0.0/24"})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret", response.content.decode())
        self.assertFalse(Subnet.objects.filter(firewall_id=self.fw).exists())
        self.assertEqual(self.client.get(self.base + "draft/").json()["revision"], 1)

    def test_active_filter_and_inactive_validation(self):
        subnet = self.subnet()
        self.assertEqual(
            self.change("patch", f"subnets/{subnet}/", {"active": False}).status_code, 200
        )
        self.assertEqual(
            self.client.get(self.base + "subnets/", {"active": "true"}).json()["count"], 0
        )
        self.assertEqual(
            self.client.get(self.base + "subnets/", {"active": "false"}).json()["count"], 1
        )
        self.assertEqual(
            self.change("patch", f"subnets/{subnet}/", {"gateway": "192.0.2.1"}).status_code, 400
        )

    def test_bad_payloads_and_duplicate_firewall_never_create_rows(self):
        self.assertEqual(
            self.client.post(
                "/api/v1/firewalls/",
                {"name": "fw-draft", "profile": "R81.10"},
                content_type="application/json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/firewalls/", "[]", content_type="application/json"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/firewalls/", "{broken", content_type="application/json"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/firewalls/", "x" * 65537, content_type="application/json"
            ).status_code,
            413,
        )

    def test_validation_errors_identify_fields_without_echoing_values(self):
        response = self.change("post", "subnets/", {"name": "Biuro", "cidr": "not-a-network"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("cidr", response.json()["error"]["fields"])
        self.assertNotIn("not-a-network", response.content.decode())
        response = self.change(
            "post",
            "reservations/",
            {"subnet_id": self.fw, "name": "host", "ip": "bad-ip", "mac": "bad-mac"},
        )
        self.assertIn("ip", response.json()["error"]["fields"])
        self.assertIn("mac", response.json()["error"]["fields"])

    def test_deleting_draft_does_not_remove_version_or_other_firewall_audit(self):
        import hashlib

        from dhcp_tool.models import Artifact, AuditEvent, Firewall, Version

        subnet = self.subnet()
        saved = self.client.get(self.base + "draft/").json()
        version = Version.objects.create(
            firewall_id=self.fw,
            number=1,
            author=self.user,
            description="Pierwsza",
            snapshot=saved,
            profile="R81.10",
            generator_version="test",
        )
        content = b"# historical artifact\n"
        Artifact.objects.create(
            version=version, content=content, sha256=hashlib.sha256(content).hexdigest()
        )
        other = self.client.post(
            "/api/v1/firewalls/",
            {"name": "fw-other", "profile": "R82.10"},
            content_type="application/json",
        ).json()["id"]
        self.assertEqual(self.change("delete", f"subnets/{subnet}/").status_code, 204)
        version.refresh_from_db()
        self.assertEqual(version.snapshot, saved)
        self.assertEqual(bytes(Artifact.objects.get(version=version).content), content)
        self.assertEqual(AuditEvent.objects.filter(firewall_id=other).count(), 1)
        from django.db.models.deletion import ProtectedError

        with self.assertRaises(ProtectedError):
            Firewall.objects.get(pk=self.fw).delete()

    def test_draft_snapshot_queries_do_not_grow_per_subnet(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from dhcp_tool.models import Subnet

        self.subnet()
        with CaptureQueriesContext(connection) as first:
            self.assertEqual(self.client.get(self.base + "draft/").status_code, 200)
        for index in range(1, 4):
            Subnet.objects.create(
                firewall_id=self.fw, name=f"Network {index}", cidr=f"10.0.{index}.0/24"
            )
        with CaptureQueriesContext(connection) as more:
            self.assertEqual(self.client.get(self.base + "draft/").status_code, 200)
        self.assertEqual(len(more), len(first))

    def test_delete_response_is_empty_before_http_server_serialization(self):
        import uuid

        from django.test import RequestFactory

        from dhcp_tool.draft_views import finish
        from dhcp_tool.models import Draft, Firewall

        request = RequestFactory().delete(self.base + "reservations/")
        request.user = self.user
        fw = Firewall.objects.get(pk=self.fw)
        draft = Draft.objects.get(firewall=fw)
        response = finish(request, fw, draft, "reservation", uuid.uuid4(), {}, None)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertEqual(response["X-Config-Revision"], "2")
