from django.contrib.auth import get_user_model
from django.test import TestCase

from dhcp_tool.models import Account, Firewall, FirewallAccess, Role


class FirewallAccessAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("reader", password="test-secret-123")
        cls.account = Account.objects.create(user=cls.user, role=Role.READER)
        cls.first = Firewall.objects.create(name="fw-first", profile="R81.10")
        cls.second = Firewall.objects.create(name="fw-second", profile="R82.10")
        cls.grant = FirewallAccess.objects.create(user=cls.user, firewall=cls.first)

    def test_anonymous_cannot_list_firewalls(self):
        self.assertEqual(self.client.get("/api/v1/firewalls/").status_code, 403)

    def test_list_contains_only_assigned_firewalls(self):
        self.client.force_login(self.user)
        response = self.client.get("/api/v1/firewalls/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual([row["id"] for row in response.json()["results"]], [str(self.first.pk)])
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_substituting_firewall_identifier_does_not_expose_other_device(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(f"/api/v1/firewalls/{self.first.pk}/").status_code, 200)
        response = self.client.get(f"/api/v1/firewalls/{self.second.pk}/")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("fw-second", response.content.decode())
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_revoked_grant_is_effective_on_next_request(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(f"/api/v1/firewalls/{self.first.pk}/").status_code, 200)
        self.grant.delete()
        self.assertEqual(self.client.get(f"/api/v1/firewalls/{self.first.pk}/").status_code, 404)

    def test_unassigned_staff_and_account_without_role_do_not_gain_access(self):
        self.user.is_staff = True
        self.user.save()
        self.account.delete()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/api/v1/firewalls/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/v1/firewalls/{self.first.pk}/").status_code, 404)

    def test_administrator_can_read_both_firewalls(self):
        self.account.role = Role.ADMIN
        self.account.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/api/v1/firewalls/").json()["count"], 2)
        self.assertEqual(self.client.get(f"/api/v1/firewalls/{self.second.pk}/").status_code, 200)
