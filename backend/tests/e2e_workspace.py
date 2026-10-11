"""Prepare browser fixtures only in the disposable, explicitly separate test database."""

import os
import sys
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.db import connection, transaction  # noqa: E402

from dhcp_tool.models import Account, AuditEvent, Draft, Firewall, Role, Subnet  # noqa: E402

if settings.SETTINGS_MODULE != "config.settings.test":
    raise RuntimeError("Browser fixtures require test settings.")
if not settings.DATABASES["default"]["NAME"].startswith("test_"):
    raise RuntimeError("Browser fixtures require a disposable test database.")
username = os.environ["DHCP_TOOL_E2E_USERNAME"]
if not username.startswith("e2e-workspace-"):
    raise RuntimeError("Invalid browser account prefix.")
with transaction.atomic():
    if sys.argv[1] == "create":
        user = get_user_model().objects.create_user(
            username, password=os.environ["DHCP_TOOL_E2E_PASSWORD"]
        )
        Account.objects.create(user=user, role=Role.ADMIN)
    elif sys.argv[1] == "delete":
        # Test DB history is disposable. TRUNCATE preserves production immutability triggers.
        # Suites run serially; never keep manually prepared data in this test database.
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE dhcp_tool_artifact, dhcp_tool_version CASCADE")
        firewalls = Firewall.objects.filter(name__startswith=os.environ["DHCP_TOOL_E2E_PREFIX"])
        AuditEvent.objects.filter(firewall__in=firewalls).delete()
        Subnet.objects.filter(firewall__in=firewalls).delete()
        Draft.objects.filter(firewall__in=firewalls).delete()
        firewalls.delete()
        get_user_model().objects.filter(username=username).delete()
    else:
        raise RuntimeError("Unknown browser fixture action.")
