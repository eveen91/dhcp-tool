from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import Client, TransactionTestCase

from dhcp_tool.models import Account, AuditEvent, Draft, Role


class DraftConcurrencyTests(TransactionTestCase):
    def test_two_writers_same_revision_commit_exactly_one_change(self):
        user = get_user_model().objects.create_user("concurrent-admin")
        Account.objects.create(user=user, role=Role.ADMIN)
        client = Client()
        client.force_login(user)
        fw = client.post(
            "/api/v1/firewalls/",
            {"name": "fw-concurrent", "profile": "R81.10"},
            content_type="application/json",
        ).json()["id"]
        clients = [Client(), Client()]
        for worker in clients:
            worker.force_login(user)
        barrier = Barrier(2)

        def write(index):
            try:
                barrier.wait(timeout=10)
                response = clients[index].patch(
                    f"/api/v1/firewalls/{fw}/draft/",
                    {"domain": ["first.example", "second.example"][index]},
                    content_type="application/json",
                    HTTP_X_CONFIG_REVISION="1",
                )
                return response.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(write, range(2)))
        self.assertEqual(sorted(results), [200, 409])
        draft = Draft.objects.get(firewall_id=fw)
        self.assertEqual(draft.revision, 2)
        self.assertIn(draft.settings["domain"], ["first.example", "second.example"])
        self.assertEqual(AuditEvent.objects.filter(firewall_id=fw).count(), 2)
