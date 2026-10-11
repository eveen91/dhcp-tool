from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from dhcp_tool.models import Account, Firewall, FirewallAccess, Role


class AccountCommandsTests(TestCase):
    def test_new_local_user_has_validated_password_role_and_explicit_scope(self):
        firewall = Firewall.objects.create(name="command-fw", profile="R81.10")
        with patch("getpass.getpass", return_value="strong-Test-command-8347"):
            call_command(
                "create_local_user",
                "new-user",
                role="editor",
                firewall=[firewall.pk],
                stdout=StringIO(),
            )
        user = get_user_model().objects.get(username="new-user")
        self.assertTrue(user.check_password("strong-Test-command-8347"))
        self.assertFalse(user.is_superuser)
        self.assertEqual(Account.objects.get(user=user).role, Role.EDITOR)
        self.assertTrue(FirewallAccess.objects.filter(user=user, firewall=firewall).exists())

    def test_weak_password_does_not_create_account(self):
        with patch("getpass.getpass", return_value="123"), self.assertRaises(CommandError):
            call_command("create_local_user", "weak-user", role="reader", stdout=StringIO())
        self.assertFalse(get_user_model().objects.filter(username="weak-user").exists())

    def test_invalid_firewall_does_not_partially_update_role(self):
        user = get_user_model().objects.create_user("existing")
        Account.objects.create(user=user, role=Role.READER)
        with self.assertRaises(CommandError):
            call_command(
                "set_user_access",
                "existing",
                role="admin",
                firewall=["00000000-0000-0000-0000-000000000000"],
                stdout=StringIO(),
            )
        self.assertEqual(Account.objects.get(user=user).role, Role.READER)

    def test_access_replacement_and_revocation(self):
        user = get_user_model().objects.create_user("existing")
        first = Firewall.objects.create(name="one", profile="R81.10")
        second = Firewall.objects.create(name="two", profile="R82.10")
        FirewallAccess.objects.create(user=user, firewall=first)
        call_command(
            "set_user_access", "existing", role="operator", firewall=[second.pk], stdout=StringIO()
        )
        self.assertEqual(
            list(FirewallAccess.objects.filter(user=user).values_list("firewall_id", flat=True)),
            [second.pk],
        )
        call_command(
            "set_user_access", "existing", role="reader", clear_firewalls=True, stdout=StringIO()
        )
        self.assertFalse(FirewallAccess.objects.filter(user=user).exists())
