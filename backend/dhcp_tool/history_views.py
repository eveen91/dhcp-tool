"""Revision-safe publication, immutable downloads and scoped history."""

import platform
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F, Max
from django.db.models.functions import Length
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from rest_framework import serializers

from .access import ACTIONS, firewall_child, visible_firewalls
from .auth import api_error, role_for
from .draft import OPTION_KEYS, StrictSerializer, generator_config, snapshot, validate_draft
from .draft_views import (
    InputError,
    body,
    firewall_data,
    input_errors,
    locked,
    method_actions,
    validated,
)
from .history import GENERATOR_VERSION, compare_versions, last_successful_version, version_data
from .models import Artifact, AuditEvent, Pool, Reservation, Subnet, Version
from .validation import prepare_artifact


class PublishSerializer(StrictSerializer):
    description = serializers.CharField(max_length=2000, allow_blank=False)


def check_commit_access(request, firewall_id):
    user = get_user_model().objects.filter(pk=request.user.pk).first()
    if (
        user is None
        or not user.is_active
        or user.get_session_auth_hash() != request.user.get_session_auth_hash()
    ):
        raise InputError(api_error("permission_denied", "Sesja nie pozwala na publikację.", 403))
    if not visible_firewalls(user).filter(pk=firewall_id).exists():
        raise InputError(api_error("not_found", "Nie znaleziono zasobu.", 404))
    if role_for(user) not in ACTIONS["edit"]:
        raise InputError(api_error("permission_denied", "Brak uprawnień do publikacji.", 403))


def publication(request):
    data = validated(PublishSerializer, body(request))
    with transaction.atomic():
        fw, draft = locked(request)
        config = generator_config(fw, draft)
        saved = snapshot(fw, draft)
        saved["firewall"] = firewall_data(fw)
        saved["author"] = {"id": request.user.pk, "username": request.user.get_username()}
    identifier = uuid.uuid4()
    content, report = prepare_artifact(
        config, parser_path=settings.DHCPD_PARSER_PATH, version_id=identifier
    )
    if report["syntax_status"] not in ("syntax_checked", "parser_unavailable"):
        status = 400 if report["syntax_status"] == "syntax_error" else 503
        return api_error(report["syntax_status"], "Nie udało się potwierdzić składni.", status)
    report["revision"] = saved["revision"]
    report["environment"] = {"python": platform.python_version(), "system": platform.system()}
    with transaction.atomic():
        check_commit_access(request, fw.pk)
        fw, draft = locked(request)
        number = (
            Version.objects.filter(firewall=fw).aggregate(value=Max("number"))["value"] or 0
        ) + 1
        version = Version.objects.create(
            id=identifier,
            firewall=fw,
            number=number,
            author=request.user,
            description=data["description"],
            snapshot=saved,
            profile=config["profile"],
            generator_version=GENERATOR_VERSION,
        )
        artifact = Artifact.objects.create(
            version=version, content=content, sha256=report["sha256"], validation=report
        )
        version.artifact = artifact
        AuditEvent.objects.create(
            firewall=fw,
            actor=request.user,
            operation="publish",
            object_type="version",
            object_id=version.pk,
            revision=draft.revision,
            before=None,
            after={"version_id": str(version.pk), "number": number, "sha256": report["sha256"]},
        )
        response = JsonResponse(version_data(version), status=201)
        response["Location"] = f"/api/v1/firewalls/{fw.pk}/versions/{version.pk}/"
        response["X-Config-Revision"] = str(draft.revision)
        return response


@method_actions(GET="read", POST="edit")
@input_errors
@csrf_protect
@require_http_methods(["GET", "POST"])
def versions(request, firewall_id):
    if request.method == "POST":
        return publication(request)
    if set(request.GET) - {"page", "page_size", "ordering", "search"}:
        return api_error("validation_error", "Nieobsługiwane parametry.", 400)
    try:
        page, size = int(request.GET.get("page", "1")), int(request.GET.get("page_size", "50"))
        if not 1 <= page <= 2147483647 or not 1 <= size <= 100:
            raise ValueError
    except ValueError:
        return api_error("validation_error", "Niepoprawna paginacja.", 400)
    order = request.GET.get("ordering", "-number")
    if order not in ("number", "-number", "created_at", "-created_at"):
        return api_error("validation_error", "Niepoprawne sortowanie.", 400)
    rows = (
        Version.objects.filter(firewall=request.firewall)
        .select_related("artifact")
        .defer("snapshot", "artifact__content")
        .annotate(
            snapshot_author=F("snapshot__author"),
            snapshot_name=F("snapshot__firewall__name"),
            snapshot_revision=F("snapshot__revision"),
            artifact_length=Length("artifact__content"),
        )
        .order_by(order, "id")
    )
    if "search" in request.GET:
        rows = rows.filter(description__icontains=request.GET["search"][:150])
    count = rows.count()

    def link(number):
        query = request.GET.copy()
        query["page"] = number
        return request.path + "?" + query.urlencode()

    return JsonResponse(
        {
            "count": count,
            "next": link(page + 1) if page * size < count else None,
            "previous": link(page - 1) if page > 1 else None,
            "results": [version_data(v) for v in rows[(page - 1) * size : page * size]],
        }
    )


@method_actions(GET="read")
@firewall_child("version_id", Version)
@require_http_methods(["GET"])
def version_detail(request, firewall_id, version_id):
    return JsonResponse(version_data(request.scoped_objects["version_id"], detail=True))


@method_actions(GET="read")
@firewall_child("version_id", Version)
@require_http_methods(["GET"])
def artifact(request, firewall_id, version_id):
    version = request.scoped_objects["version_id"]
    saved = version.artifact
    response = HttpResponse(bytes(saved.content), content_type="text/plain; charset=us-ascii")
    response["Content-Disposition"] = 'attachment; filename="dhcpd.conf"'
    response["X-Content-SHA256"] = saved.sha256
    response["X-Version-ID"] = str(version.pk)
    response["X-Version-Number"] = str(version.number)
    return response


@method_actions(GET="read")
@firewall_child("from", Version, source="query")
@firewall_child("to", Version, source="query")
@require_http_methods(["GET"])
def diff(request, firewall_id):
    if set(request.GET) - {"from", "to"} or "to" not in request.scoped_objects:
        return api_error("validation_error", "Wymagana wersja docelowa.", 400)
    after = request.scoped_objects["to"]
    before = request.scoped_objects.get("from") or last_successful_version(request.firewall)
    if before is None:
        return JsonResponse(
            {
                "from": None,
                "to": version_data(after),
                "baseline_reason": "no_successful_deployment",
                "manual_deployment": True,
                "text": None,
                "semantic": [],
            }
        )
    return JsonResponse(
        {
            "from": version_data(before),
            "to": version_data(after),
            "baseline_reason": None,
            "manual_deployment": "from" not in request.GET,
            **compare_versions(before, after),
        }
    )


@method_actions(POST="edit")
@firewall_child("version_id", Version)
@input_errors
@csrf_protect
@require_http_methods(["POST"])
def restore(request, firewall_id, version_id):
    validated(StrictSerializer, body(request))
    source = request.scoped_objects["version_id"]
    with transaction.atomic():
        fw, draft = locked(request)
        before = snapshot(fw, draft)
        Subnet.objects.filter(firewall=fw).delete()
        for saved in source.snapshot["subnets"]:
            row = Subnet.objects.create(
                id=saved["id"],
                firewall=fw,
                name=saved["name"],
                cidr=saved["cidr"],
                interface=saved["interface"],
                description=saved["description"],
                active=saved["active"],
                options={key: saved[key] for key in OPTION_KEYS if key in saved},
            )
            if saved["pool"]:
                Pool.objects.create(subnet=row, **saved["pool"])
            for reservation in saved["reservations"]:
                Reservation.objects.create(
                    subnet=row,
                    **{
                        key: value
                        for key, value in reservation.items()
                        if key not in ("subnet_id", "created_at")
                    },
                )
        draft.settings = source.snapshot["settings"]
        validate_draft(fw, draft)
        draft.base_version = source
        draft.revision += 1
        draft.save(update_fields=["settings", "base_version", "revision"])
        after = snapshot(fw, draft)
        AuditEvent.objects.create(
            firewall=fw,
            actor=request.user,
            operation="restore",
            object_type="draft",
            object_id=fw.pk,
            revision=draft.revision,
            before=before,
            after=after,
        )
        response = JsonResponse(after)
        response["X-Config-Revision"] = str(draft.revision)
        return response
