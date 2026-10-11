from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import Client, TransactionTestCase
from django.utils import timezone

from dhcp_tool.models import (
    Account,
    Artifact,
    AuditEvent,
    Deployment,
    Draft,
    Firewall,
    Role,
    Version,
)


class DeploymentConcurrencyTests(TransactionTestCase):
    def test_two_corrections_commit_one_and_preserve_audit_and_draft(self):
        user = get_user_model().objects.create_user("concurrent-operator")
        Account.objects.create(user=user, role=Role.ADMIN)
        fw = Firewall.objects.create(name="concurrent-ledger", profile="R81.10")
        Draft.objects.create(firewall=fw)
        version = Version.objects.create(
            firewall=fw, number=1, profile=fw.profile, generator_version="1", snapshot={}
        )
        Artifact.objects.create(version=version, content=b"# test\n", sha256="a" * 64)
        entry = Deployment.objects.create(
            version=version, operator=user, occurred_at=timezone.now(), status="successful"
        )
        clients = [Client(), Client()]
        for client in clients:
            client.force_login(user)
        barrier = Barrier(2)

        def write(index):
            try:
                barrier.wait(timeout=10)
                return (
                    clients[index]
                    .patch(
                        f"/api/v1/firewalls/{fw.pk}/deployments/{entry.pk}/",
                        {
                            "expected_revision": 1,
                            "correction_reason": "Korekta wyniku",
                            "status": ["failed", "cancelled"][index],
                        },
                        content_type="application/json",
                    )
                    .status_code
                )
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(write, range(2)))
        self.assertEqual(sorted(results), [200, 409])
        entry.refresh_from_db()
        self.assertEqual(entry.revision, 2)
        event = AuditEvent.objects.get()
        self.assertEqual(event.before["status"], "successful")
        self.assertEqual(event.after["entry"]["status"], entry.status)
        self.assertEqual(Draft.objects.get(firewall=fw).revision, 1)
