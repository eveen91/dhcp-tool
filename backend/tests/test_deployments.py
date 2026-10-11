import hashlib
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.test import Client, TestCase
from django.utils import timezone

from dhcp_tool.models import (
    Account,
    Artifact,
    AuditEvent,
    Deployment,
    Draft,
    Firewall,
    FirewallAccess,
    Role,
    Version,
)


class DeploymentAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("ledger-operator")
        self.account = Account.objects.create(user=self.user, role=Role.OPERATOR)
        self.fw = Firewall.objects.create(name="ledger-fw", profile="R81.10")
        Draft.objects.create(firewall=self.fw)
        FirewallAccess.objects.create(user=self.user, firewall=self.fw)
        self.versions = [self.make_version(self.fw, n) for n in (1, 2)]
        self.client.force_login(self.user)
        self.base = f"/api/v1/firewalls/{self.fw.pk}/"
        self.now = timezone.now() - timedelta(minutes=10)

    def make_version(self, fw, number):
        v = Version.objects.create(
            firewall=fw,
            number=number,
            profile=fw.profile,
            generator_version="1",
            snapshot={"firewall_id": str(fw.pk), "settings": {}, "subnets": []},
            description="Test",
            author=self.user,
        )
        content = f"# version {number}\n".encode()
        Artifact.objects.create(
            version=v, content=content, sha256=hashlib.sha256(content).hexdigest()
        )
        return v

    def create(self, status="successful", version=None, when=None, **extra):
        return self.client.post(
            self.base + "deployments/",
            {
                "version_id": str((version or self.versions[1]).pk),
                "status": status,
                "occurred_at": (when or self.now).isoformat(),
                "note": "Ręczny wpis",
                **extra,
            },
            content_type="application/json",
        )

    def correct(self, entry, **extra):
        return self.client.patch(
            self.base + f"deployments/{entry['id']}/",
            {
                "expected_revision": entry["revision"],
                "correction_reason": "Poprawa wyniku",
                **extra,
            },
            content_type="application/json",
        )

    def latest(self):
        response = self.client.get(self.base + "deployments/latest/")
        self.assertEqual(response.status_code, 200)
        return response.json()["deployment"]

    def test_registration_and_audit_preserve_manual_origin_and_draft_revision(self):
        response = self.create(ticket="INC-1")
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["operator"], self.user.username)
        self.assertEqual(data["confirmation"], "manual")
        self.assertEqual(data["hash_comparison"], "not_supplied")
        self.assertEqual(data["revision"], 1)
        self.assertGreater(data["created_at"], data["occurred_at"])
        self.assertEqual(data["ticket"], "INC-1")
        event = AuditEvent.objects.get()
        self.assertEqual(event.operation, "deployment_create")
        self.assertIsNone(event.before)
        self.assertEqual(event.after, data)
        self.assertEqual(Draft.objects.get(firewall=self.fw).revision, 1)
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_non_successes_and_download_do_not_declare_a_deployment(self):
        self.assertIsNone(self.latest())
        for status in ("planned", "failed", "cancelled"):
            self.assertEqual(self.create(status).status_code, 201)
            self.assertIsNone(self.latest())
        self.client.get(self.base + f"versions/{self.versions[0].pk}/artifact/")
        self.assertEqual(Deployment.objects.count(), 3)

    def test_backdated_entry_and_reuse_older_artifact_preserve_history(self):
        first = self.create().json()
        self.create(version=self.versions[0], when=self.now - timedelta(days=1))
        self.assertEqual(self.latest()["id"], first["id"])
        response = self.create(version=self.versions[0], when=self.now + timedelta(minutes=1))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.latest()["version_number"], 1)
        self.assertEqual(Version.objects.count(), 2)
        self.assertEqual(Deployment.objects.count(), 3)
        data = self.client.get(self.base + f"diff/?to={self.versions[1].pk}").json()
        self.assertEqual(data["from"]["id"], str(self.versions[0].pk))

    def test_ties_use_entry_time_then_uuid(self):
        first, second = self.create().json(), self.create().json()
        self.assertEqual(self.latest()["id"], second["id"])
        Deployment.objects.all().update(created_at=self.now)
        self.assertEqual(self.latest()["id"], max(first["id"], second["id"]))

    def test_hash_comparison_remains_manual_including_mismatch(self):
        expected = self.versions[1].artifact.sha256
        for supplied, result in ((expected.upper(), "match"), ("0" * 64, "mismatch")):
            response = self.create(supplied_hash=supplied)
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()["supplied_hash"], supplied.lower())
            self.assertEqual(response.json()["hash_comparison"], result)
            self.assertEqual(response.json()["confirmation"], "manual")
        self.assertEqual(self.create(supplied_hash="bad").status_code, 400)

    def test_timestamps_require_timezone_and_only_plans_allow_future(self):
        for value in ("2026-01-01T10:00:00", "bad"):
            self.assertEqual(self.create(occurred_at=value).status_code, 400)
        future = timezone.now() + timedelta(days=1)
        for status in ("successful", "failed", "cancelled"):
            self.assertEqual(self.create(status, when=future).status_code, 400)
        self.assertEqual(self.create("planned", when=future).status_code, 201)

    def test_server_fields_and_limits_are_rejected(self):
        for extra in (
            {"operator": "someone"},
            {"created_at": self.now.isoformat()},
            {"confirmation": "automatic"},
            {"hash_comparison": "match"},
            {"note": "a" * 2001},
            {"ticket": "a" * 151},
        ):
            self.assertEqual(self.create(**extra).status_code, 400)
        self.assertEqual(self.create(status="unknown").status_code, 400)
        self.assertEqual(Deployment.objects.count(), 0)

    def test_roles_scope_archive_and_methods(self):
        for role in (Role.READER, Role.EDITOR, Role.OPERATOR, Role.ADMIN):
            self.account.role = role
            self.account.save()
            self.assertEqual(self.client.get(self.base + "deployments/").status_code, 200)
            self.assertEqual(self.client.get(self.base + "audit/").status_code, 200)
            self.assertEqual(
                self.create().status_code, 201 if role in (Role.OPERATOR, Role.ADMIN) else 403
            )
        self.fw.archived = True
        self.fw.save()
        self.assertEqual(self.create().status_code, 409)
        self.assertEqual(self.client.get(self.base + "deployments/").status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(self.base + "deployments/").status_code, 403)

    def test_cross_firewall_identifiers_even_with_both_grants(self):
        other = Firewall.objects.create(name="other-ledger", profile="R82.10")
        FirewallAccess.objects.create(user=self.user, firewall=other)
        foreign = self.make_version(other, 1)
        self.assertEqual(self.create(version=foreign).status_code, 404)
        self.assertEqual(
            self.client.get(self.base + f"deployments/?version_id={foreign.pk}").status_code, 404
        )
        entry = self.create().json()
        other_base = f"/api/v1/firewalls/{other.pk}/"
        self.assertEqual(
            self.client.get(other_base + f"deployments/{entry['id']}/").status_code, 404
        )
        event = AuditEvent.objects.get()
        self.assertEqual(self.client.get(other_base + f"audit/{event.pk}/").status_code, 404)
        self.assertEqual(self.correct(entry, version_id=str(foreign.pk)).status_code, 404)

    def test_correction_requires_revision_reason_and_keeps_original_operator(self):
        original = self.create().json()
        user = get_user_model().objects.create_user("correcting-admin")
        Account.objects.create(user=user, role=Role.ADMIN)
        self.client.force_login(user)
        response = self.correct(original, status="failed")
        self.assertEqual(response.status_code, 200)
        current = response.json()
        self.assertEqual(current["operator"], self.user.username)
        self.assertEqual(current["created_at"], original["created_at"])
        self.assertEqual(current["revision"], 2)
        self.assertIsNone(self.latest())
        event = AuditEvent.objects.get(operation="deployment_correct")
        self.assertEqual(event.actor, user)
        self.assertEqual(event.before, original)
        self.assertEqual(event.after["entry"], current)
        self.assertEqual(event.after["correction_reason"], "Poprawa wyniku")
        conflict = self.correct(original, status="cancelled")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["error"]["current_revision"], 2)
        self.assertEqual(conflict.json()["error"]["fields"], {})
        self.assertEqual(self.correct(current, correction_reason="").status_code, 400)
        self.assertEqual(self.correct(current).status_code, 400)
        self.assertEqual(AuditEvent.objects.count(), 2)
        self.assertEqual(
            self.client.delete(self.base + f"deployments/{original['id']}/").status_code, 405
        )

    def test_correction_changes_baseline_after_time_and_version_change(self):
        first = self.create(version=self.versions[0], when=self.now - timedelta(hours=1)).json()
        second = self.create().json()
        response = self.correct(second, occurred_at=(self.now - timedelta(days=1)).isoformat())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.latest()["id"], first["id"])
        self.assertEqual(self.correct(first, version_id=str(self.versions[1].pk)).status_code, 200)
        self.assertEqual(self.latest()["version_number"], 2)

    def test_audit_failure_rolls_back_writes(self):
        with patch.object(AuditEvent.objects, "create", side_effect=DatabaseError("private")):
            self.assertEqual(self.create().status_code, 500)
        self.assertEqual(Deployment.objects.count(), 0)
        entry = self.create().json()
        with patch.object(AuditEvent.objects, "create", side_effect=DatabaseError("private")):
            self.assertEqual(self.correct(entry, status="failed").status_code, 500)
        self.assertEqual(self.latest(), entry)
        self.assertEqual(AuditEvent.objects.count(), 1)

    def test_audit_list_detail_pagination_and_read_only_methods(self):
        entry = self.create().json()
        self.correct(entry, status="failed")
        response = self.client.get(self.base + "audit/?operation=deployment_correct&page_size=1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        event = data["results"][0]
        self.assertNotIn("before", event)
        detail = self.client.get(self.base + f"audit/{event['id']}/").json()
        self.assertEqual(detail["before"]["status"], "successful")
        self.assertEqual(detail["after"]["entry"]["status"], "failed")
        for method in (self.client.post, self.client.patch, self.client.delete):
            self.assertEqual(method(self.base + f"audit/{event['id']}/").status_code, 405)
        for query in ("page_size=101", "page=0", "page=1&page=2", "unknown=true"):
            for path in ("audit/", "deployments/"):
                self.assertEqual(self.client.get(self.base + path + "?" + query).status_code, 400)

    def test_csrf_registration_and_correction(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        data = {
            "version_id": str(self.versions[0].pk),
            "status": "failed",
            "occurred_at": self.now.isoformat(),
        }
        self.assertEqual(
            client.post(
                self.base + "deployments/", data, content_type="application/json"
            ).status_code,
            403,
        )
        token = client.get("/api/v1/auth/session/").json()["csrf_token"]
        created = client.post(
            self.base + "deployments/",
            data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(
            client.patch(
                self.base + f"deployments/{created.json()['id']}/",
                {
                    "status": "cancelled",
                    "expected_revision": 1,
                    "correction_reason": "Błąd",
                },
                content_type="application/json",
            ).status_code,
            403,
        )

    def test_correction_roles_and_removed_scope_apply_to_all_read_routes(self):
        entry = self.create().json()
        audit = AuditEvent.objects.get()
        for role in (Role.READER, Role.EDITOR):
            self.account.role = role
            self.account.save()
            self.assertEqual(self.correct(entry, status="failed").status_code, 403)
        FirewallAccess.objects.filter(user=self.user).delete()
        for suffix in (
            "deployments/",
            "deployments/latest/",
            f"deployments/{entry['id']}/",
            "audit/",
            f"audit/{audit.pk}/",
        ):
            self.assertEqual(self.client.get(self.base + suffix).status_code, 404)

    def test_filters_and_schema_describe_real_ledger_and_audit_responses(self):
        entry = self.create().json()
        self.create(status="failed", version=self.versions[0])
        response = self.client.get(
            self.base + f"deployments/?status=successful&version_id={self.versions[1].pk}"
        )
        self.assertEqual(response.json()["results"], [entry])
        schemas = self.client.get("/api/v1/schema/").json()["components"]["schemas"]
        self.assertEqual(set(entry), set(schemas["Deployment"]["required"]))
        audit = AuditEvent.objects.first()
        detail = self.client.get(self.base + f"audit/{audit.pk}/").json()
        self.assertEqual(set(detail), set(schemas["AuditDetail"]["required"]))
