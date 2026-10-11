"""Reverse proxy scheme and explicit LAN settings must keep authentication usable."""

import json
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings


class RuntimeSettingsTests(SimpleTestCase):
    def module(self, name):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import importlib,json; m=importlib.import_module('"
                + name
                + "'); print(json.dumps({k:getattr(m,k,None) for k in ['SECURE_SSL_REDIRECT','SECURE_PROXY_SSL_HEADER','SESSION_COOKIE_SECURE','CSRF_COOKIE_SECURE']}))",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return SimpleNamespace(**json.loads(result.stdout))

    def environment(self, scheme):
        return patch.dict(
            os.environ,
            {
                "DJANGO_ALLOWED_HOSTS": "192.168.1.32",
                "DJANGO_CSRF_TRUSTED_ORIGINS": f"{scheme}://192.168.1.32:8080",
                "POSTGRES_DB": "test_runtime_settings",
                "POSTGRES_USER": "test_runtime_settings",
                "POSTGRES_PASSWORD": "test-only-password",
            },
        )

    def test_https_proxy_does_not_redirect_back_to_itself(self):
        with self.environment("https"):
            module = self.module("config.settings.production")
        with override_settings(
            ALLOWED_HOSTS=["192.168.1.32"],
            SECURE_SSL_REDIRECT=module.SECURE_SSL_REDIRECT,
            SECURE_PROXY_SSL_HEADER=getattr(module, "SECURE_PROXY_SSL_HEADER", None),
        ):
            response = self.client.get(
                "/api/v1/health/", HTTP_HOST="192.168.1.32", HTTP_X_FORWARDED_PROTO="https"
            )
        self.assertEqual(response.status_code, 200)

    def test_http_lan_serves_api_without_https_redirect(self):
        with self.environment("http"):
            module = self.module("config.settings.lan")
        with override_settings(
            ALLOWED_HOSTS=["192.168.1.32"],
            SECURE_SSL_REDIRECT=module.SECURE_SSL_REDIRECT,
            SESSION_COOKIE_SECURE=module.SESSION_COOKIE_SECURE,
            CSRF_COOKIE_SECURE=module.CSRF_COOKIE_SECURE,
        ):
            response = self.client.get("/api/v1/auth/session/", HTTP_HOST="192.168.1.32")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.cookies["csrftoken"]["secure"])

    def test_default_production_cookies_remain_secure(self):
        with self.environment("https"):
            module = self.module("config.settings.production")
        self.assertTrue(module.SESSION_COOKIE_SECURE)
        self.assertTrue(module.CSRF_COOKIE_SECURE)

    def test_install_preparation_refuses_public_http_host(self):
        import tempfile
        from pathlib import Path

        script = Path(__file__).resolve().parents[2] / "scripts/prepare-install.py"
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(script), "--output", directory, "--host", "8.8.8.8"],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("private_lan_required", result.stderr)
            self.assertFalse((Path(directory) / "backend.env").exists())

    def test_install_preparation_keeps_secrets_private_and_renders_full_panel(self):
        import tempfile
        from pathlib import Path

        script = Path(__file__).resolve().parents[2] / "scripts/prepare-install.py"
        with tempfile.TemporaryDirectory() as directory, self.environment("http"):
            result = subprocess.run(
                [sys.executable, str(script), "--output", directory], capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("test-only-password", result.stdout + result.stderr)
            environment = Path(directory) / "backend.env"
            self.assertEqual(environment.stat().st_mode & 0o777, 0o600)
            self.assertIn('DJANGO_SETTINGS_MODULE="config.settings.lan"', environment.read_text())
            self.assertIn('POSTGRES_PASSWORD="test-only-password"', environment.read_text())
            self.assertNotIn("@HOST@", (Path(directory) / "nginx.conf").read_text())

    def test_environment_runner_preserves_literal_values_without_shell_execution(self):
        import tempfile
        from pathlib import Path

        script = Path(__file__).resolve().parents[2] / "scripts/run-with-env.py"
        with tempfile.TemporaryDirectory() as directory:
            environment = Path(directory) / "backend.env"
            environment.write_text('VALUE="literal $HOME $(echo bad) spaces \\"quoted\\""\n')
            environment.chmod(0o600)
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    str(environment),
                    sys.executable,
                    "-c",
                    "import os; print(os.environ['VALUE'])",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'literal $HOME $(echo bad) spaces "quoted"')
