import logging
from io import StringIO

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import path

from config.urls import urlpatterns as existing_urls
from dhcp_tool.access import firewall_action, firewall_child, scoped_object
from dhcp_tool.models import Account, Firewall, FirewallAccess, Role


@firewall_action("edit")
def edit_probe(request, firewall_id):
    request.firewall.name = "edited"
    request.firewall.save(update_fields=["name"])
    return JsonResponse({"saved": True})


@firewall_action("deploy")
def deploy_probe(request, firewall_id):
    return JsonResponse({"allowed": True})


@firewall_action("admin")
def admin_probe(request, firewall_id):
    return JsonResponse({"allowed": True})


def undeclared_probe(request, firewall_id):
    return JsonResponse({"unsafe": True})


@firewall_action("read")
@firewall_child("grant_id", FirewallAccess)
def child_probe(request, firewall_id, grant_id):
    child = scoped_object(FirewallAccess.objects.all(), request.firewall, grant_id)
    return JsonResponse({"user_id": child.user_id})


def unscoped_child_probe(request, firewall_id, grant_id):
    return JsonResponse({"unsafe_child": grant_id})


def query_probe(request, firewall_id):
    return JsonResponse({"unsafe_diff": True})


@firewall_child("from", FirewallAccess, source="query")
@firewall_child("to", FirewallAccess, source="query")
def scoped_query_probe(request, firewall_id):
    return JsonResponse({"allowed_diff": True})


def fault_probe(request):
    raise RuntimeError("RAW-CONFIG-SECRET password=cannot-log-this")


urlpatterns = existing_urls + [
    path("api/v1/firewalls/<uuid:firewall_id>/test-edit/", edit_probe),
    path("api/v1/firewalls/<uuid:firewall_id>/test-deploy/", deploy_probe),
    path("api/v1/firewalls/<uuid:firewall_id>/test-admin/", admin_probe),
    path("api/v1/firewalls/<uuid:firewall_id>/test-undeclared/", undeclared_probe),
    path("api/v1/firewalls/<uuid:firewall_id>/test-children/<int:grant_id>/", child_probe),
    path("api/v1/test-fault/", fault_probe),
    path("api/v1/firewalls/<uuid:firewall_id>/test-scoped-query/", scoped_query_probe),
    path("api/v1/firewalls/<uuid:firewall_id>/test-query/", query_probe),
    path("api/v1/firewalls/<uuid:firewall_id>/test-unscoped/<int:grant_id>/", unscoped_child_probe),
]


@override_settings(ROOT_URLCONF="test_security")
class CapabilityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("scoped", password="test-password")
        self.account = Account.objects.create(user=self.user, role=Role.READER)
        self.first = Firewall.objects.create(name="first", profile="R81.10")
        self.second = Firewall.objects.create(name="second", profile="R82.10")
        self.first_grant = FirewallAccess.objects.create(user=self.user, firewall=self.first)
        self.second_grant = FirewallAccess.objects.create(user=self.user, firewall=self.second)
        self.client.force_login(self.user)

    def test_role_capabilities_are_independent(self):
        allowed = {
            Role.READER: set(),
            Role.EDITOR: {"edit"},
            Role.OPERATOR: {"deploy"},
            Role.ADMIN: {"edit", "deploy", "admin"},
        }
        for role, actions in allowed.items():
            self.account.role = role
            self.account.save()
            for action in ("edit", "deploy", "admin"):
                with self.subTest(role=role, action=action):
                    response = self.client.post(f"/api/v1/firewalls/{self.first.pk}/test-{action}/")
                    self.assertEqual(response.status_code, 200 if action in actions else 403)

    def test_unknown_mutation_is_denied_even_to_administrator(self):
        self.account.role = Role.ADMIN
        self.account.save()
        response = self.client.post(f"/api/v1/firewalls/{self.first.pk}/test-undeclared/")
        self.assertEqual(response.status_code, 403)

    def test_child_handler_without_scope_declaration_is_denied(self):
        response = self.client.get(
            f"/api/v1/firewalls/{self.first.pk}/test-unscoped/{self.second_grant.pk}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_diff_identifiers_without_scope_declarations_are_denied(self):
        self.assertEqual(
            self.client.get(f"/api/v1/firewalls/{self.first.pk}/test-query/").status_code, 200
        )
        response = self.client.get(
            f"/api/v1/firewalls/{self.first.pk}/test-query/",
            {"from": str(self.first_grant.pk), "to": str(self.second_grant.pk)},
        )
        self.assertEqual(response.status_code, 404)

    def test_scoped_comparison_rejects_an_object_from_another_firewall(self):
        url = f"/api/v1/firewalls/{self.first.pk}/test-scoped-query/"
        self.assertEqual(
            self.client.get(
                url, {"from": self.first_grant.pk, "to": self.first_grant.pk}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                url, {"from": self.first_grant.pk, "to": self.second_grant.pk}
            ).status_code,
            404,
        )

    def test_reader_cannot_change_configuration(self):
        response = self.client.post(f"/api/v1/firewalls/{self.first.pk}/test-edit/")
        self.assertEqual(response.status_code, 403)
        self.first.refresh_from_db()
        self.assertEqual(self.first.name, "first")

    def test_child_from_other_firewall_is_rejected_even_when_both_are_accessible(self):
        good = f"/api/v1/firewalls/{self.first.pk}/test-children/{self.first_grant.pk}/"
        wrong = f"/api/v1/firewalls/{self.first.pk}/test-children/{self.second_grant.pk}/"
        self.assertEqual(self.client.get(good).status_code, 200)
        self.assertEqual(self.client.get(wrong).status_code, 404)

    def test_cross_firewall_writes_are_denied_even_to_editor(self):
        self.account.role = Role.EDITOR
        self.account.save()
        self.second_grant.delete()
        response = self.client.post(f"/api/v1/firewalls/{self.second.pk}/test-edit/")
        self.assertEqual(response.status_code, 404)
        self.second.refresh_from_db()
        self.assertEqual(self.second.name, "second")

    def test_archived_firewall_is_readable_but_not_editable(self):
        self.account.role = Role.EDITOR
        self.account.save()
        self.first.archived = True
        self.first.save()
        self.assertEqual(self.client.get(f"/api/v1/firewalls/{self.first.pk}/").status_code, 200)
        self.assertEqual(
            self.client.post(f"/api/v1/firewalls/{self.first.pk}/test-edit/").status_code, 409
        )


@override_settings(ROOT_URLCONF="test_security", DEBUG=True)
class SafeErrorTests(SimpleTestCase):
    def test_api_exception_does_not_expose_debug_page_or_raw_error(self):
        response = Client(raise_request_exception=False).get("/api/v1/test-fault/")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertNotIn(b"RAW-CONFIG-SECRET", response.content)
        self.assertEqual(response.json()["error"]["code"], "internal_error")

    def test_log_formatter_omits_exception_body_cookie_and_credentials(self):
        from config.logging import SafeFormatter

        output = StringIO()
        handler = logging.StreamHandler(output)
        handler.setFormatter(SafeFormatter())
        logger = logging.Logger("isolated-test")
        logger.addHandler(handler)
        try:
            raise ValueError("RAW-CONFIG-SECRET")
        except ValueError:
            logger.exception("password=secret Cookie=session-secret body=raw-config")
        self.assertNotIn("RAW-CONFIG-SECRET", output.getvalue())
        self.assertNotIn("secret", output.getvalue())
        self.assertIn("ERROR", output.getvalue())
