from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client, TestCase, override_settings
from django.utils import timezone


class SessionAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("operator", password="test-secret-123")

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def token(self):
        response = self.client.get("/api/v1/auth/session/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        return response.json()["csrf_token"]

    def login(self, **changes):
        data = {"username": "operator", "password": "test-secret-123", **changes}
        return self.client.post(
            "/api/v1/auth/session/",
            data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.token(),
        )

    def test_anonymous_bootstrap_has_no_user_or_session_cookie(self):
        response = self.client.get("/api/v1/auth/session/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["user"])
        self.assertNotIn("sessionid", response.cookies)
        self.assertTrue(response.cookies["csrftoken"]["httponly"])
        self.assertTrue(response.cookies["csrftoken"]["secure"])
        self.assertEqual(response.cookies["csrftoken"]["samesite"], "Lax")

    @override_settings(LOGIN_IP_LIMIT=1)
    def test_blocked_ip_does_not_create_buckets_for_new_usernames(self):
        from dhcp_tool.models import LoginBucket

        self.assertEqual(self.login(username="first-attempt").status_code, 403)
        count = LoginBucket.objects.count()
        self.assertEqual(self.login(username="different-attempt").status_code, 429)
        self.assertEqual(LoginBucket.objects.count(), count)

    def test_invalid_username_is_rejected_before_database_authentication(self):
        self.assertEqual(self.login(username="invalid\x00username").status_code, 400)

    def test_login_current_user_and_logout(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "operator")
        self.assertNotIn("password", response.json()["user"])
        cookie = response.cookies["sessionid"]
        self.assertTrue(cookie["httponly"])
        self.assertTrue(cookie["secure"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(
            self.client.get("/api/v1/auth/session/").json()["user"]["id"], self.user.pk
        )
        token = response.json()["csrf_token"]
        response = self.client.delete("/api/v1/auth/session/", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.client.get("/api/v1/auth/session/").json()["user"])

    def test_login_requires_csrf_even_without_an_authenticated_session(self):
        response = self.client.post(
            "/api/v1/auth/session/",
            {"username": "operator", "password": "test-secret-123"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response.json()["error"]["code"], "csrf_failed")

    def test_logout_requires_csrf(self):
        self.assertEqual(self.login().status_code, 200)
        response = self.client.delete("/api/v1/auth/session/")
        self.assertEqual(response.status_code, 403)
        self.assertIsNotNone(self.client.get("/api/v1/auth/session/").json()["user"])

    def test_invalid_unknown_and_inactive_accounts_have_same_public_error(self):
        invalid = self.login(password="wrong").json()
        unknown = self.login(username="missing").json()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        inactive = self.login().json()
        self.assertEqual(invalid, unknown)
        self.assertEqual(invalid, inactive)
        self.assertEqual(invalid["error"]["code"], "invalid_credentials")

    def test_login_rotates_session_identifier(self):
        session = self.client.session
        session["preauth"] = True
        session.save()
        old_key = session.session_key
        self.assertEqual(self.login().status_code, 200)
        self.assertNotEqual(self.client.cookies["sessionid"].value, old_key)
        other = Client()
        other.cookies["sessionid"] = old_key
        self.assertIsNone(other.get("/api/v1/auth/session/").json()["user"])

    def test_cross_origin_login_and_logout_are_rejected(self):
        token = self.token()
        response = self.client.post(
            "/api/v1/auth/session/",
            {"username": "operator", "password": "test-secret-123"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
            HTTP_ORIGIN="https://untrusted.example",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.login().status_code, 200)
        response = self.client.delete(
            "/api/v1/auth/session/",
            HTTP_X_CSRFTOKEN=self.token(),
            HTTP_ORIGIN="https://untrusted.example",
        )
        self.assertEqual(response.status_code, 403)

    def test_expired_session_does_not_authenticate(self):
        self.assertEqual(self.login().status_code, 200)
        Session.objects.update(expire_date=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(self.client.get("/api/v1/auth/session/").json()["user"])

    def test_password_change_invalidates_session(self):
        self.assertEqual(self.login().status_code, 200)
        self.user.set_password("new-test-secret-123")
        self.user.save()
        self.assertIsNone(self.client.get("/api/v1/auth/session/").json()["user"])

    def test_malformed_and_oversized_login_are_rejected(self):
        for body in (
            "{",
            "[]",
            '{"username":123,"password":"x"}',
            '{"username":"operator","password":"' + "x" * 5000 + '"}',
        ):
            with self.subTest(body_length=len(body)):
                response = self.client.post(
                    "/api/v1/auth/session/",
                    body,
                    content_type="application/json",
                    HTTP_X_CSRFTOKEN=self.token(),
                )
                self.assertIn(response.status_code, (400, 413))
                self.assertEqual(response["Cache-Control"], "no-store")

    @override_settings(LOGIN_ACCOUNT_LIMIT=2)
    def test_login_attempts_are_limited_across_clients(self):
        self.assertEqual(self.login(password="wrong").status_code, 403)
        self.client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.login(password="wrong").status_code, 403)
        response = self.login()
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response["Retry-After"]), 0)
        self.assertIsNone(self.client.get("/api/v1/auth/session/").json()["user"])

    @override_settings(LOGIN_IP_LIMIT=2)
    def test_ip_limit_cannot_be_bypassed_by_changing_username_or_forwarded_header(self):
        self.assertEqual(self.login(username="one").status_code, 403)
        self.assertEqual(self.login(username="two").status_code, 403)
        response = self.client.post(
            "/api/v1/auth/session/",
            {"username": "three", "password": "wrong"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.token(),
            HTTP_X_FORWARDED_FOR="203.0.113.10",
        )
        self.assertEqual(response.status_code, 429)
