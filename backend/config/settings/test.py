"""Automated tests: no external database needed for database-free tests."""

import os

from django.core.exceptions import ImproperlyConfigured

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-insecure-key-not-for-production")

from .base import *  # noqa: F403,E402

ALLOWED_HOSTS = ["testserver"]
DATABASES["default"]["NAME"] = os.environ.get("POSTGRES_TEST_DB", "test_dhcp_tool")  # noqa: F405
DATABASES["default"]["TEST"] = {"NAME": DATABASES["default"]["NAME"]}  # noqa: F405
if not DATABASES["default"]["NAME"].startswith("test_"):  # noqa: F405
    raise ImproperlyConfigured("Automated tests require a database name starting with test_.")
