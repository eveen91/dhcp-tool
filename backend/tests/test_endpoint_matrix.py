"""Capabilities are exercised on actual routes, not permission probes."""

import hashlib
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from dhcp_tool.models import (
    Account,
    Artifact,
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


@override_settings(DHCPD_PARSER_PATH=None)
class EndpointMatrixTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("matrix-user")
        self.account = Account.objects.create(user=self.user, role=Role.READER)
        self.fw = Firewall.objects.create(name="matrix-fw", profile="R81.10")
        Draft.objects.create(firewall=self.fw)
        FirewallAccess.objects.create(user=self.user, firewall=self.fw)
        self.net = Subnet.objects.create(firewall=self.fw, name="Net", cidr="192.0.2.0/24")
        Pool.objects.create(subnet=self.net, start="192.0.2.100", end="192.0.2.150")
        self.row = Reservation.objects.create(
            subnet=self.net, name="printer", mac="02:00:00:00:00:01", ip="192.0.2.10"
        )
        version = Version.objects.create(
            firewall=self.fw, number=1, profile="R81.10", generator_version="1", snapshot={}
        )
        Artifact.objects.create(
            version=version, content=b"# fixed\n", sha256=hashlib.sha256(b"# fixed\n").hexdigest()
        )
        self.entry = Deployment.objects.create(
            version=version,
            operator=self.user,
            status="planned",
            occurred_at=timezone.now() - timedelta(days=1),
        )
        self.client.force_login(self.user)
        self.base = f"/api/v1/firewalls/{self.fw.pk}/"

    def test_write_capabilities_on_real_handlers(self):
        routes = [
            ("patch", "", {"location": "Test"}, {Role.ADMIN}, 200),
            ("patch", "draft/", {"domain": "example.test"}, {Role.EDITOR, Role.ADMIN}, 200),
            (
                "post",
                "subnets/",
                {"name": "Other", "cidr": "198.51.100.0/24"},
                {Role.EDITOR, Role.ADMIN},
                201,
            ),
            ("patch", f"subnets/{self.net.pk}/", {"name": "New"}, {Role.EDITOR, Role.ADMIN}, 200),
            (
                "put",
                f"subnets/{self.net.pk}/pool/",
                {"start": "192.0.2.110", "end": "192.0.2.160"},
                {Role.EDITOR, Role.ADMIN},
                200,
            ),
            (
                "patch",
                f"reservations/{self.row.pk}/",
                {"ip": "192.0.2.11"},
                {Role.EDITOR, Role.ADMIN},
                200,
            ),
            ("post", "versions/", {"description": "Publication"}, {Role.EDITOR, Role.ADMIN}, 201),
            (
                "patch",
                f"deployments/{self.entry.pk}/",
                {"status": "cancelled", "expected_revision": 1, "correction_reason": "Test"},
                {Role.OPERATOR, Role.ADMIN},
                200,
            ),
        ]
        for role in Role.values:
            self.account.role = role
            self.account.save()
            for method, path, data, allowed, success in routes:
                with self.subTest(role=role, path=path), transaction.atomic():
                    response = getattr(self.client, method)(
                        self.base + path,
                        data,
                        content_type="application/json",
                        HTTP_X_CONFIG_REVISION="1",
                    )
                    self.assertEqual(response.status_code, success if role in allowed else 403)
                    transaction.set_rollback(True)

    def test_actual_writes_require_csrf_for_every_role(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for role in Role.values:
            self.account.role = role
            self.account.save()
            for path in ("draft/", "versions/", "deployments/", f"subnets/{self.net.pk}/pool/"):
                with self.subTest(role=role, path=path):
                    response = client.post(self.base + path, {}, content_type="application/json")
                    self.assertEqual(response.status_code, 403)

    def test_directive_injection_through_http_never_changes_draft(self):
        self.account.role = Role.EDITOR
        self.account.save()
        for payload in (
            'x"; include "/etc/passwd";',
            "example.test\nallow booting;",
            "${shell}",
            "x; option routers 1.1.1.1;",
        ):
            response = self.client.patch(
                self.base + "draft/",
                {"domain": payload},
                content_type="application/json",
                HTTP_X_CONFIG_REVISION="1",
            )
            self.assertEqual(response.status_code, 400)
        draft = Draft.objects.get(firewall=self.fw)
        self.assertEqual(draft.settings, {})
        self.assertEqual(draft.revision, 1)
