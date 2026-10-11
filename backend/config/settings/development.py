"""Local development only; never deploy with this settings module."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "development-only-insecure-key-not-for-production")

from .base import *  # noqa: F403,E402

DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# The Next.js dev proxy forwards to a different backend host/port.
if not CSRF_TRUSTED_ORIGINS:  # noqa: F405
    CSRF_TRUSTED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
