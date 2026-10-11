"""Explicit HTTP mode for the user's trusted LAN/VPN deployment."""

from .production import *  # noqa: F403

# HTTPS remains the default production profile. Select this mode explicitly.
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_PROXY_SSL_HEADER = None
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
