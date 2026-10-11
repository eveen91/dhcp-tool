"""Create/remove a random Playwright account in the explicitly separate test DB."""

import os
import sys
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.db import transaction  # noqa: E402

from dhcp_tool.models import Account, Role  # noqa: E402

if settings.SETTINGS_MODULE != "config.settings.test":
    raise RuntimeError("E2E accounts require test settings.")
if not settings.DATABASES["default"]["NAME"].startswith("test_"):
    raise RuntimeError("E2E accounts require a separate test database.")
username = os.environ["DHCP_TOOL_E2E_USERNAME"]
if not username.startswith("e2e-"):
    raise RuntimeError("Invalid E2E account prefix.")
with transaction.atomic():
    if sys.argv[1] == "create":
        user = get_user_model().objects.create_user(
            username, password=os.environ["DHCP_TOOL_E2E_PASSWORD"]
        )
        Account.objects.create(user=user, role=Role.READER)
    elif sys.argv[1] == "delete":
        get_user_model().objects.filter(username=username).delete()
    else:
        raise RuntimeError("Unknown E2E action.")
