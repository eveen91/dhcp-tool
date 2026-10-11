import json
from pathlib import Path

from django.http import JsonResponse
from django.urls import path
from django.views.decorators.http import require_GET

from dhcp_tool import csv_config_views
from dhcp_tool.auth import session
from dhcp_tool.backup_views import latest_backup
from dhcp_tool.csv_views import apply_csv, export_csv, preview_csv
from dhcp_tool.deployment_views import (
    audit_detail,
    audit_events,
    deployment_detail,
    deployments,
    latest_deployment,
)
from dhcp_tool.draft_views import (
    draft_detail,
    firewall_detail,
    pool_detail,
    reservation_detail,
    reservations,
    subnet_detail,
    subnets,
)
from dhcp_tool.history_views import artifact, diff, restore, version_detail, versions
from dhcp_tool.validation_views import preview, validation
from dhcp_tool.views import firewalls


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


@require_GET
def schema(request):
    document = json.loads(Path(__file__).with_name("openapi.json").read_text())
    return JsonResponse(document)


urlpatterns = [
    path("api/v1/firewalls/<uuid:firewall_id>/csv/config/export/", csv_config_views.export_csv),
    path("api/v1/firewalls/<uuid:firewall_id>/csv/config/preview/", csv_config_views.preview_csv),
    path("api/v1/firewalls/<uuid:firewall_id>/csv/config/apply/", csv_config_views.apply_csv),
    path("api/v1/firewalls/<uuid:firewall_id>/csv/export/", export_csv),
    path("api/v1/firewalls/<uuid:firewall_id>/csv/preview/", preview_csv),
    path("api/v1/firewalls/<uuid:firewall_id>/csv/apply/", apply_csv),
    path("api/v1/backups/latest/download/", latest_backup),
    path("api/v1/firewalls/<uuid:firewall_id>/deployments/", deployments),
    path("api/v1/firewalls/<uuid:firewall_id>/deployments/latest/", latest_deployment),
    path(
        "api/v1/firewalls/<uuid:firewall_id>/deployments/<uuid:deployment_id>/", deployment_detail
    ),
    path("api/v1/firewalls/<uuid:firewall_id>/audit/", audit_events),
    path("api/v1/firewalls/<uuid:firewall_id>/audit/<uuid:audit_id>/", audit_detail),
    path("api/v1/firewalls/<uuid:firewall_id>/versions/", versions),
    path("api/v1/firewalls/<uuid:firewall_id>/versions/<uuid:version_id>/", version_detail),
    path("api/v1/firewalls/<uuid:firewall_id>/versions/<uuid:version_id>/artifact/", artifact),
    path("api/v1/firewalls/<uuid:firewall_id>/versions/<uuid:version_id>/restore/", restore),
    path("api/v1/firewalls/<uuid:firewall_id>/diff/", diff),
    path("api/v1/firewalls/<uuid:firewall_id>/validation/", validation),
    path("api/v1/firewalls/<uuid:firewall_id>/preview/", preview),
    path("api/v1/firewalls/<uuid:firewall_id>/draft/", draft_detail),
    path("api/v1/firewalls/<uuid:firewall_id>/subnets/", subnets),
    path("api/v1/firewalls/<uuid:firewall_id>/subnets/<uuid:subnet_id>/", subnet_detail),
    path("api/v1/firewalls/<uuid:firewall_id>/subnets/<uuid:subnet_id>/pool/", pool_detail),
    path("api/v1/firewalls/<uuid:firewall_id>/reservations/", reservations),
    path(
        "api/v1/firewalls/<uuid:firewall_id>/reservations/<uuid:reservation_id>/",
        reservation_detail,
    ),
    path("api/v1/firewalls/", firewalls, name="firewalls"),
    path("api/v1/firewalls/<uuid:firewall_id>/", firewall_detail, name="firewall-detail"),
    path("api/v1/auth/session/", session, name="session"),
    path("api/v1/health/", health, name="health"),
    path("api/v1/schema/", schema, name="schema"),
]
