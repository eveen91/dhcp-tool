"""Manual deployment declarations, revision-safe corrections and scoped audit reads."""

from urllib.parse import urlencode

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from rest_framework import serializers

from .access import firewall_child, scoped_object
from .auth import api_error
from .deployments import ORDER, deployment_data, entries, last_successful_deployment
from .draft import StrictSerializer
from .draft_views import InputError, body, input_errors, method_actions, validated
from .models import AuditEvent, Deployment, Draft, Firewall, Version

STATUSES = ("planned", "successful", "failed", "cancelled")


class ZonedDateTime(serializers.DateTimeField):
    def to_internal_value(self, value):
        try:
            parsed = parse_datetime(value) if isinstance(value, str) else None
        except ValueError:
            parsed = None
        if parsed is None or timezone.is_naive(parsed):
            raise serializers.ValidationError("Podaj czas ze strefą: Z lub ±HH:MM.")
        return super().to_internal_value(value)


class DeploymentSerializer(StrictSerializer):
    version_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=STATUSES)
    occurred_at = ZonedDateTime()
    note = serializers.CharField(max_length=2000, allow_blank=True, default="")
    ticket = serializers.CharField(max_length=150, allow_blank=True, default="")
    supplied_hash = serializers.RegexField(r"\A[0-9a-fA-F]{64}\Z", allow_blank=True, default="")

    def validate_supplied_hash(self, value):
        return value.lower()


class CorrectionSerializer(DeploymentSerializer):
    # A correction may change any declaration field, but cannot change its original author/time.
    version_id = serializers.UUIDField(required=False)
    status = serializers.ChoiceField(choices=STATUSES, required=False)
    occurred_at = ZonedDateTime(required=False)
    note = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    ticket = serializers.CharField(max_length=150, allow_blank=True, required=False)
    supplied_hash = serializers.RegexField(r"\A[0-9a-fA-F]{64}\Z", allow_blank=True, required=False)
    expected_revision = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    correction_reason = serializers.CharField(max_length=2000, allow_blank=False)

    def validate(self, data):
        if not set(data) - {"expected_revision", "correction_reason"}:
            raise serializers.ValidationError({"body": "Wskaż korygowane pola."})
        return data


def validate_event(status, occurred_at):
    if status != "planned" and occurred_at > timezone.now():
        raise serializers.ValidationError({"occurred_at": "Wynik nie może dotyczyć przyszłości."})


def locked_firewall(request):
    fw = Firewall.objects.select_for_update().get(pk=request.firewall.pk)
    if fw.archived:
        raise InputError(api_error("firewall_archived", "Firewall jest zarchiwizowany.", 409))
    return fw


def audit_declaration(request, firewall, entry, before, reason=None):
    after = deployment_data(entry)
    AuditEvent.objects.create(
        firewall=firewall,
        actor=request.user,
        operation="deployment_create" if before is None else "deployment_correct",
        object_type="deployment",
        object_id=entry.pk,
        revision=Draft.objects.get_or_create(firewall=firewall)[0].revision,
        before=before,
        after=after if before is None else {"entry": after, "correction_reason": reason},
    )
    return after


def page_response(request, rows, allowed, serialize):
    if set(request.GET) - allowed or any(len(request.GET.getlist(k)) != 1 for k in request.GET):
        raise serializers.ValidationError({"query": "Niepoprawne parametry."})
    try:
        page, size = int(request.GET.get("page", "1")), int(request.GET.get("page_size", "50"))
        if not 1 <= page <= 2147483647 or not 1 <= size <= 100:
            raise ValueError
    except ValueError:
        raise serializers.ValidationError({"page": "Niepoprawna strona lub rozmiar."}) from None
    count = rows.count()

    def link(value):
        return (
            request.path + "?" + urlencode({**request.GET.dict(), "page": value, "page_size": size})
        )

    return JsonResponse(
        {
            "count": count,
            "next": link(page + 1) if page * size < count else None,
            "previous": link(page - 1) if page > 1 else None,
            "results": [serialize(row) for row in rows[(page - 1) * size : page * size]],
        }
    )


@method_actions(GET="read", POST="deploy")
@firewall_child("version_id", Version, source="query")
@csrf_protect
@require_http_methods(["GET", "POST"])
@input_errors
def deployments(request, firewall_id):
    if request.method == "POST":
        if request.GET:
            raise serializers.ValidationError({"query": "Rejestracja nie przyjmuje filtrów."})
        data = validated(DeploymentSerializer, body(request))
        validate_event(data["status"], data["occurred_at"])
        with transaction.atomic():
            fw = locked_firewall(request)
            version = scoped_object(Version.objects.all(), fw, data.pop("version_id"))
            entry = Deployment.objects.create(version=version, operator=request.user, **data)
            entry = entries(fw).get(pk=entry.pk)
            return JsonResponse(audit_declaration(request, fw, entry, None), status=201)
    rows = entries(request.firewall).order_by(*ORDER)
    if "status" in request.GET:
        if request.GET["status"] not in STATUSES:
            raise serializers.ValidationError({"status": "Niepoprawny wynik."})
        rows = rows.filter(status=request.GET["status"])
    if "version_id" in request.scoped_objects:
        rows = rows.filter(version=request.scoped_objects["version_id"])
    return page_response(
        request, rows, {"page", "page_size", "status", "version_id"}, deployment_data
    )


@method_actions(GET="read", PATCH="deploy")
@firewall_child("deployment_id", Deployment, firewall_lookup="version__firewall_id")
@csrf_protect
@require_http_methods(["GET", "PATCH"])
@input_errors
def deployment_detail(request, firewall_id, deployment_id):
    if request.GET:
        raise serializers.ValidationError({"query": "Niepoprawne parametry."})
    if request.method == "GET":
        return JsonResponse(deployment_data(entries(request.firewall).get(pk=deployment_id)))
    data = validated(CorrectionSerializer, body(request))
    expected, reason = data.pop("expected_revision"), data.pop("correction_reason")
    with transaction.atomic():
        fw = locked_firewall(request)
        # The firewall lock serializes ledger writes without changing draft revisions.
        entry = entries(fw).get(pk=deployment_id)
        if expected != entry.revision:
            return JsonResponse(
                {
                    "error": {
                        "code": "deployment_conflict",
                        "message": "Wpis został skorygowany. Odśwież przed ponownym zapisem.",
                        "current_revision": entry.revision,
                        "fields": {},
                    }
                },
                status=409,
            )
        before = deployment_data(entry)
        if "version_id" in data:
            entry.version = scoped_object(Version.objects.all(), fw, data.pop("version_id"))
        for key, value in data.items():
            setattr(entry, key, value)
        validate_event(entry.status, entry.occurred_at)
        entry.revision += 1
        entry.save()
        entry = entries(fw).get(pk=entry.pk)
        return JsonResponse(audit_declaration(request, fw, entry, before, reason))


@method_actions(GET="read")
@require_http_methods(["GET"])
@input_errors
def latest_deployment(request, firewall_id):
    if request.GET:
        raise serializers.ValidationError({"query": "Niepoprawne parametry."})
    entry = last_successful_deployment(request.firewall)
    return JsonResponse({"deployment": deployment_data(entry) if entry else None})


def audit_data(event, *, detail=False):
    data = {
        "id": str(event.pk),
        "actor": event.actor.get_username() if event.actor else None,
        "created_at": event.created_at.isoformat(),
        "operation": event.operation,
        "object_type": event.object_type,
        "object_id": str(event.object_id),
        "request_id": str(event.request_id),
        "revision": event.revision,
    }
    if detail:
        data.update(before=event.before, after=event.after)
    return data


@method_actions(GET="read")
@require_http_methods(["GET"])
@input_errors
def audit_events(request, firewall_id):
    rows = (
        AuditEvent.objects.filter(firewall=request.firewall)
        .select_related("actor")
        .defer("before", "after")
    )
    for key in ("operation", "object_type"):
        if key in request.GET:
            if not request.GET[key] or len(request.GET[key]) > 32:
                raise serializers.ValidationError({key: "Niepoprawny filtr."})
            rows = rows.filter(**{key: request.GET[key]})
    return page_response(
        request,
        rows.order_by("-created_at", "-id"),
        {"page", "page_size", "operation", "object_type"},
        audit_data,
    )


@method_actions(GET="read")
@firewall_child("audit_id", AuditEvent)
@require_http_methods(["GET"])
@input_errors
def audit_detail(request, firewall_id, audit_id):
    if request.GET:
        raise serializers.ValidationError({"query": "Niepoprawne parametry."})
    return JsonResponse(audit_data(request.scoped_objects["audit_id"], detail=True))
