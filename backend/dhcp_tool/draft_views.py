"""Scoped HTTP operations; every mutation locks the firewall before its draft."""

import json

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from rest_framework import serializers

from .access import firewall_child, scoped_object
from .auth import api_error, role_for
from .draft import (
    OPTION_KEYS,
    FirewallSerializer,
    OptionsSerializer,
    PoolSerializer,
    ReservationSerializer,
    SubnetSerializer,
    normalize_subnet,
    pool_data,
    reservation_data,
    snapshot,
    subnet_data,
    validate_draft,
)
from .generator import ConfigurationError
from .models import AuditEvent, Draft, Firewall, Pool, Reservation, Role, Subnet


class InputError(Exception):
    def __init__(self, response):
        self.response = response


def body(request):
    if request.content_type != "application/json":
        raise InputError(api_error("validation_error", "Wymagany JSON.", 400))
    raw = request.read(65537)
    if len(raw) > 65536:
        raise InputError(api_error("request_too_large", "Zbyt duże żądanie.", 413))
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, UnicodeDecodeError):
        raise InputError(api_error("validation_error", "Niepoprawny JSON.", 400)) from None


def validated(serializer_class, data, *, partial=False):
    serializer = serializer_class(data=data, partial=partial)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def input_errors(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except InputError as exc:
            return exc.response
        except (
            serializers.ValidationError,
            ValidationError,
            ConfigurationError,
            IntegrityError,
        ) as exc:
            response = api_error("validation_error", "Niepoprawne dane konfiguracji.", 400)
            # Never echo values, SQL or raw generator/parser messages.
            response_data = json.loads(response.content)
            if isinstance(exc, serializers.ValidationError) and isinstance(exc.detail, dict):
                keys = list(exc.detail)
            elif isinstance(exc, ValidationError) and hasattr(exc, "message_dict"):
                keys = list(exc.message_dict)
            elif isinstance(exc, ConfigurationError):
                keys = [str(exc).split(":", 1)[0]]
            else:
                keys = ["body"]
            response_data["error"]["fields"] = {
                key: [{"code": "invalid", "message": "Sprawdź pole i powiązania konfiguracji."}]
                for key in keys
            }
            return JsonResponse(response_data, status=400)

    return wrapped


def method_actions(**actions):
    def decorate(view):
        view.firewall_action = actions
        return view

    return decorate


def audit(request, fw, draft, kind, identifier, before, after):
    AuditEvent.objects.create(
        firewall=fw,
        actor=request.user,
        revision=draft.revision,
        object_type=kind,
        object_id=identifier,
        operation="create" if before is None else "delete" if after is None else "update",
        before=before,
        after=after,
    )


def revision(request, draft):
    raw = request.headers.get("X-Config-Revision", "")
    if not raw.isascii() or not raw.isdecimal() or len(raw) > 19 or int(raw) < 1:
        raise InputError(
            api_error("validation_error", "Wymagana poprawna rewizja konfiguracji.", 400)
        )
    if int(raw) != draft.revision:
        response = api_error(
            "revision_conflict", "Konfiguracja została zmieniona. Odśwież dane.", 409
        )
        value = json.loads(response.content)
        value["error"]["current_revision"] = draft.revision
        raise InputError(JsonResponse(value, status=409))


def locked(request):
    fw = Firewall.objects.select_for_update().get(pk=request.firewall.pk)
    draft, _ = Draft.objects.get_or_create(firewall=fw)
    revision(request, draft)
    if fw.archived and request.method != "GET" and request.path != f"/api/v1/firewalls/{fw.pk}/":
        raise InputError(api_error("firewall_archived", "Firewall jest zarchiwizowany.", 409))
    return fw, draft


def finish(request, fw, draft, kind, identifier, before, after, status=200):
    validate_draft(fw, draft)
    draft.revision += 1
    draft.save(update_fields=["revision", "settings"])
    audit(request, fw, draft, kind, identifier, before, after)
    response = (
        JsonResponse(after, status=status) if after is not None else JsonResponse({}, status=204)
    )
    if response.status_code == 204:
        response.content = b""
    response["X-Config-Revision"] = str(draft.revision)
    if status == 201:
        suffix = f"{kind}s/{identifier}/" if kind in ("subnet", "reservation") else ""
        response["Location"] = f"/api/v1/firewalls/{fw.pk}/" + suffix
    return response


def firewall_data(fw):
    return {
        "id": str(fw.pk),
        "name": fw.name,
        "profile": fw.profile,
        "description": fw.description,
        "location": fw.location,
        "management_address": fw.management_address,
        "archived": fw.archived,
        "created_at": fw.created_at.isoformat(),
    }


@input_errors
@csrf_protect
@require_http_methods(["POST"])
def create_firewall(request):
    if role_for(request.user) != Role.ADMIN:
        return api_error("permission_denied", "Wymagana rola administratora.", 403)
    data = validated(FirewallSerializer, body(request))
    with transaction.atomic():
        fw = Firewall(**data)
        fw.full_clean()
        fw.save()
        draft = Draft.objects.create(firewall=fw)
        audit(request, fw, draft, "firewall", fw.pk, None, firewall_data(fw))
        response = JsonResponse(firewall_data(fw), status=201)
        response["Location"] = f"/api/v1/firewalls/{fw.pk}/"
        response["X-Config-Revision"] = "1"
        return response


@method_actions(GET="read", PATCH="admin")
@input_errors
@csrf_protect
@require_http_methods(["GET", "PATCH"])
def firewall_detail(request, firewall_id):
    if request.method == "GET":
        return JsonResponse(firewall_data(request.firewall))
    data = validated(FirewallSerializer, body(request), partial=True)
    with transaction.atomic():
        fw, draft = locked(request)
        before = firewall_data(fw)
        for key, value in data.items():
            setattr(fw, key, value)
        fw.full_clean()
        fw.save()
        return finish(request, fw, draft, "firewall", fw.pk, before, firewall_data(fw))


@method_actions(GET="read", PATCH="edit")
@input_errors
@csrf_protect
@require_http_methods(["GET", "PATCH"])
def draft_detail(request, firewall_id):
    if request.method == "GET":
        # A short lock makes metadata and child rows a coherent snapshot.
        with transaction.atomic():
            fw = Firewall.objects.select_for_update().get(pk=firewall_id)
            draft, _ = Draft.objects.get_or_create(firewall=fw)
            return JsonResponse(snapshot(fw, draft))
    data = validated(OptionsSerializer, body(request), partial=True)
    with transaction.atomic():
        fw, draft = locked(request)
        before = dict(draft.settings)
        for key, value in data.items():
            if value is None:
                draft.settings.pop(key, None)
            else:
                draft.settings[key] = value
        return finish(request, fw, draft, "draft", fw.pk, before, draft.settings)


def paginated(request, queryset, serialize, allowed, search_fields):
    from django.db.models import Q

    if set(request.GET) - {"page", "page_size", "search", "active", "ordering", *allowed}:
        return api_error("validation_error", "Nieobsługiwany parametr.", 400)
    try:
        page = int(request.GET.get("page", "1"))
        size = int(request.GET.get("page_size", "50"))
        if not 1 <= page <= 2147483647 or not 1 <= size <= 100:
            raise ValueError
    except ValueError:
        return api_error("validation_error", "Niepoprawna paginacja.", 400)
    if "active" in request.GET:
        value = request.GET["active"]
        if value not in ("true", "false"):
            return api_error("validation_error", "Niepoprawny filtr.", 400)
        queryset = queryset.filter(active=value == "true")
    if "subnet_id" in request.GET:
        queryset = queryset.filter(subnet_id=request.scoped_objects["subnet_id"].pk)
    if "search" in request.GET:
        term = request.GET["search"][:150]
        condition = Q()
        for field in search_fields:
            condition |= Q(**{f"{field}__icontains": term})
        queryset = queryset.filter(condition)
    order = request.GET.get("ordering", "name")
    order_fields = {"name", "created_at"} | (
        {"ip", "mac"} if queryset.model == Reservation else set()
    )
    if order.removeprefix("-") not in order_fields:
        return api_error("validation_error", "Niepoprawne sortowanie.", 400)
    queryset = queryset.order_by(order, "id")
    count = queryset.count()

    def link(number):
        params = request.GET.copy()
        params["page"] = number
        return request.path + "?" + params.urlencode()

    return JsonResponse(
        {
            "count": count,
            "next": link(page + 1) if page * size < count else None,
            "previous": link(page - 1) if page > 1 else None,
            "results": [serialize(r) for r in queryset[(page - 1) * size : page * size]],
        }
    )


def set_values(row, data):
    for key, value in data.items():
        if isinstance(row, Subnet) and key in OPTION_KEYS:
            if value is None:
                row.options.pop(key, None)
            else:
                row.options[key] = value
        else:
            setattr(row, key, value)
    if isinstance(row, Subnet):
        normalize_subnet(row)
    row.full_clean()
    row.save()


@method_actions(GET="read", POST="edit")
@input_errors
@csrf_protect
@require_http_methods(["GET", "POST"])
def subnets(request, firewall_id):
    if request.method == "GET":
        return paginated(
            request,
            Subnet.objects.filter(firewall=request.firewall),
            subnet_data,
            set(),
            ["name", "cidr"],
        )
    data = validated(SubnetSerializer, body(request))
    with transaction.atomic():
        fw, draft = locked(request)
        row = Subnet(firewall=fw)
        set_values(row, data)
        return finish(request, fw, draft, "subnet", row.pk, None, subnet_data(row), 201)


@method_actions(GET="read", PATCH="edit", DELETE="edit")
@firewall_child("subnet_id", Subnet)
@input_errors
@csrf_protect
@require_http_methods(["GET", "PATCH", "DELETE"])
def subnet_detail(request, firewall_id, subnet_id):
    if request.method == "GET":
        return JsonResponse(subnet_data(request.scoped_objects["subnet_id"], children=True))
    data = (
        validated(SubnetSerializer, body(request), partial=True)
        if request.method == "PATCH"
        else None
    )
    with transaction.atomic():
        fw, draft = locked(request)
        row = scoped_object(Subnet.objects.all(), fw, subnet_id)
        before = subnet_data(row, children=True)
        if data is None:
            row.delete()
            after = None
        else:
            set_values(row, data)
            after = subnet_data(row, children=True)
        return finish(request, fw, draft, "subnet", subnet_id, before, after)


@method_actions(GET="read", PUT="edit", DELETE="edit")
@firewall_child("subnet_id", Subnet)
@input_errors
@csrf_protect
@require_http_methods(["GET", "PUT", "DELETE"])
def pool_detail(request, firewall_id, subnet_id):
    if request.method == "GET":
        row = Pool.objects.filter(subnet_id=subnet_id).first()
        if row is None:
            raise Http404
        return JsonResponse(pool_data(row))
    data = validated(PoolSerializer, body(request)) if request.method == "PUT" else None
    with transaction.atomic():
        fw, draft = locked(request)
        subnet = scoped_object(Subnet.objects.all(), fw, subnet_id)
        row = Pool.objects.filter(subnet=subnet).first()
        before = pool_data(row) if row else None
        if data is None:
            if row is None:
                raise Http404
            identifier = row.pk
            row.delete()
            after = None
        else:
            row = row or Pool(subnet=subnet)
            set_values(row, data)
            identifier, after = row.pk, pool_data(row)
        return finish(request, fw, draft, "pool", identifier, before, after)


@method_actions(GET="read", POST="edit")
@firewall_child("subnet_id", Subnet, source="query")
@input_errors
@csrf_protect
@require_http_methods(["GET", "POST"])
def reservations(request, firewall_id):
    if request.method == "GET":
        return paginated(
            request,
            Reservation.objects.filter(subnet__firewall=request.firewall),
            reservation_data,
            {"subnet_id"},
            ["name", "mac", "ip"],
        )
    data = validated(ReservationSerializer, body(request))
    with transaction.atomic():
        fw, draft = locked(request)
        subnet = scoped_object(Subnet.objects.all(), fw, data.pop("subnet_id"))
        row = Reservation(subnet=subnet)
        set_values(row, data)
        return finish(request, fw, draft, "reservation", row.pk, None, reservation_data(row), 201)


@method_actions(GET="read", PATCH="edit", DELETE="edit")
@firewall_child("reservation_id", Reservation, firewall_lookup="subnet__firewall_id")
@input_errors
@csrf_protect
@require_http_methods(["GET", "PATCH", "DELETE"])
def reservation_detail(request, firewall_id, reservation_id):
    if request.method == "GET":
        return JsonResponse(reservation_data(request.scoped_objects["reservation_id"]))
    data = (
        validated(ReservationSerializer, body(request), partial=True)
        if request.method == "PATCH"
        else None
    )
    with transaction.atomic():
        fw, draft = locked(request)
        row = scoped_object(
            Reservation.objects.all(), fw, reservation_id, firewall_lookup="subnet__firewall_id"
        )
        before = reservation_data(row)
        if data is None:
            row.delete()
            after = None
        else:
            if "subnet_id" in data:
                row.subnet = scoped_object(Subnet.objects.all(), fw, data.pop("subnet_id"))
            set_values(row, data)
            after = reservation_data(row)
        return finish(request, fw, draft, "reservation", reservation_id, before, after)
