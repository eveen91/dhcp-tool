import hashlib
import socket
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext

from dhcp_tool.models import Account, Artifact, AuditEvent, Draft, Firewall, Role, Version


class ListBoundsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("review-admin")
        Account.objects.create(user=self.user, role=Role.ADMIN)
        self.fw = Firewall.objects.create(name="review-fw", profile="R81.10")
        Draft.objects.create(firewall=self.fw)
        self.client.force_login(self.user)
        self.base = f"/api/v1/firewalls/{self.fw.pk}/"
        content = b"# frozen\n"
        self.version = Version.objects.create(
            firewall=self.fw,
            number=1,
            profile="R81.10",
            generator_version="1",
            snapshot={
                "firewall": {"name": "review-fw"},
                "author": {"id": self.user.pk, "username": self.user.username},
                "revision": 1,
            },
        )
        Artifact.objects.create(
            version=self.version, content=content, sha256=hashlib.sha256(content).hexdigest()
        )
        AuditEvent.objects.create(
            firewall=self.fw,
            actor=self.user,
            operation="update",
            object_type="draft",
            object_id=self.fw.pk,
            revision=1,
            before={"secret": "private-old"},
            after={"secret": "private-new"},
        )

    def test_version_list_does_not_select_artifact_bytes_or_entire_snapshot(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.base + "versions/")
        self.assertEqual(response.status_code, 200)
        row = response.json()["results"][0]
        self.assertEqual(row["artifact_bytes"], 9)
        self.assertEqual(row["author"]["username"], self.user.username)
        self.assertEqual(row["firewall_name"], "review-fw")
        selects = [
            q["sql"]
            for q in queries
            if 'FROM "dhcp_tool_version"' in q["sql"] and "COUNT(" not in q["sql"]
        ]
        self.assertEqual(len(selects), 1)
        # Metadata may use length(content) / JSON extraction, but never fetch these columns.
        self.assertNotIn(', "dhcp_tool_artifact"."content"', selects[0])
        self.assertNotIn(', "dhcp_tool_version"."snapshot",', selects[0])

    def test_audit_list_never_fetches_before_after_snapshots(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.base + "audit/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"private-old", response.content)
        selects = [
            q["sql"]
            for q in queries
            if 'FROM "dhcp_tool_auditevent"' in q["sql"] and "COUNT(" not in q["sql"]
        ]
        self.assertEqual(len(selects), 1)
        self.assertNotIn('"dhcp_tool_auditevent"."before"', selects[0])
        self.assertNotIn('"dhcp_tool_auditevent"."after"', selects[0])

    def test_all_lists_reject_duplicate_and_excessive_query_inputs(self):
        for path in (
            "/api/v1/firewalls/",
            self.base + "versions/",
            self.base + "subnets/",
            self.base + "reservations/",
            self.base + "deployments/",
            self.base + "audit/",
        ):
            for query in (
                "page=1&page=2",
                "search=" + "x" * 2050,
                "page_size=101",
                "page=2147483648",
            ):
                with self.subTest(path=path, query=query[:40]):
                    response = self.client.get(path + "?" + query)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response["Cache-Control"], "no-store")


class DatabaseOutageTests(TransactionTestCase):
    def test_connection_outage_returns_safe_uncached_json_and_no_partial_publication(self):
        user = get_user_model().objects.create_user("outage-admin")
        Account.objects.create(user=user, role=Role.ADMIN)
        fw = Firewall.objects.create(name="outage-fw", profile="R81.10")
        Draft.objects.create(firewall=fw)
        self.client.raise_request_exception = False
        self.client.force_login(user)
        with socket.socket() as unused:
            unused.bind(("127.0.0.1", 0))
            port = unused.getsockname()[1]
            # Bound, non-listening port refuses connections without disrupting PostgreSQL.
            connection.close()
            with patch.dict(connection.settings_dict, {"HOST": "127.0.0.1", "PORT": str(port)}):
                response = self.client.post(
                    f"/api/v1/firewalls/{fw.pk}/versions/",
                    {"description": "must not publish"},
                    content_type="application/json",
                    HTTP_X_CONFIG_REVISION="1",
                )
            connection.close()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "internal_error")
        self.assertEqual(response["Cache-Control"], "no-store")
        for forbidden in (b"traceback", b"password", b"psycopg", b"OperationalError"):
            self.assertNotIn(forbidden, response.content)
        self.assertEqual(Version.objects.count(), 0)
        self.assertEqual(Artifact.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 0)
