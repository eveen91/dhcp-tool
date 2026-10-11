"""Production requires explicit credentials and hostnames; no fallbacks."""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

for name in ("DJANGO_ALLOWED_HOSTS", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
    if not os.environ.get(name):
        raise ImproperlyConfigured(f"{name} must be set in production")

if not CSRF_TRUSTED_ORIGINS:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS must be set in production")

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# Nginx overwrites this header; Gunicorn listens only on loopback.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
