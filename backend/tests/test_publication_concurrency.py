from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import Client, TransactionTestCase, override_settings

from dhcp_tool.models import (
    Account,
    Artifact,
    AuditEvent,
    Draft,
    Firewall,
    Pool,
    Role,
    Subnet,
    Version,
)
from dhcp_tool.syntax import SyntaxResult


@override_settings(DHCPD_PARSER_PATH=None)
class PublicationConcurrencyTests(TransactionTestCase):
    def test_two_publishers_get_unique_consecutive_numbers_without_parser_db_lock(self):
        user = get_user_model().objects.create_user("publish-admin")
        Account.objects.create(user=user, role=Role.ADMIN)
        fw = Firewall.objects.create(name="fw-concurrent", profile="R82.10")
        Draft.objects.create(firewall=fw)
        subnet = Subnet.objects.create(firewall=fw, name="LAN", cidr="192.0.2.0/24")
        Pool.objects.create(subnet=subnet, start="192.0.2.100", end="192.0.2.150")
        clients = [Client(), Client()]
        for client in clients:
            client.force_login(user)
        barrier = Barrier(2)

        def parser(content, **kwargs):
            barrier.wait(timeout=10)
            return SyntaxResult("syntax_checked")

        def publish(index):
            try:
                response = clients[index].post(
                    f"/api/v1/firewalls/{fw.pk}/versions/",
                    {"description": f"Publikacja {index}"},
                    content_type="application/json",
                    HTTP_X_CONFIG_REVISION="1",
                )
                return response.status_code, response.json().get("number")
            finally:
                connections.close_all()

        with (
            patch("dhcp_tool.validation.check_syntax", side_effect=parser),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            results = list(executor.map(publish, range(2)))
        self.assertEqual(sorted(results), [(201, 1), (201, 2)])
        self.assertEqual(Version.objects.filter(firewall=fw).count(), 2)
        self.assertEqual(Artifact.objects.count(), 2)
        self.assertEqual(AuditEvent.objects.filter(operation="publish").count(), 2)
        self.assertEqual(Draft.objects.get(firewall=fw).revision, 1)
