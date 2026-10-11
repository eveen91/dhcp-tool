from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.db import connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from dhcp_tool.auth import reserve_attempt
from dhcp_tool.models import LoginBucket


@override_settings(LOGIN_ACCOUNT_LIMIT=2, LOGIN_IP_LIMIT=30)
class LoginLimiterConcurrencyTests(TransactionTestCase):
    def test_concurrent_workers_cannot_exceed_account_budget(self):
        barrier = Barrier(5)

        def attempt(index):
            try:
                barrier.wait(timeout=10)
                return reserve_attempt("shared-account", f"192.0.2.{index + 1}")
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(attempt, range(5)))
        self.assertEqual(results.count(None), 2)
        self.assertTrue(all(value is None or value > 0 for value in results))

    def test_expired_budget_is_reset(self):
        self.assertIsNone(reserve_attempt("account", "192.0.2.10"))
        self.assertIsNone(reserve_attempt("account", "192.0.2.10"))
        self.assertIsNotNone(reserve_attempt("account", "192.0.2.10"))
        LoginBucket.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(reserve_attempt("account", "192.0.2.10"))
