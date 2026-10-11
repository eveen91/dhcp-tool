"""Readonly, revision-bound validation and preview of the persisted draft."""

import json
import re

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from .auth import api_error
from .draft import StrictSerializer, generator_config, snapshot
from .draft_views import body, input_errors, method_actions, revision, validated
from .generator import ConfigurationError
from .models import Draft, Firewall
from .validation import prepare_artifact


def object_field(path, data):
    """Convert generator indices to stable persisted object identifiers."""
    match = re.match(r"subnets\[(\d+)\](.*)", path)
    if not match:
        return path
    index, remainder = int(match[1]), match[2]
    if index >= len(data["subnets"]):
        return "subnets"
    subnet = data["subnets"][index]
    base = f"subnets.{subnet['id']}"
    child = re.match(r"\.reservations\[(\d+)\](.*)", remainder)
    if child and int(child[1]) < len(subnet["reservations"]):
        row = subnet["reservations"][int(child[1])]
        return base + f".reservations.{row['id']}" + child[2]
    child = re.match(r"\.pools\[0\](.*)", remainder)
    if child and subnet["pool"]:
        return base + f".pool.{subnet['pool']['id']}" + child[1]
    return base + remainder


def evaluate(request, firewall_id, *, preview):
    validated(StrictSerializer, body(request))
    # Capture coherent data, then release the DB lock before starting a process.
    with transaction.atomic():
        fw = Firewall.objects.select_for_update().get(pk=firewall_id)
        draft = Draft.objects.get(firewall=fw)
        revision(request, draft)
        config = generator_config(fw, draft)
        data = snapshot(fw, draft)
        current_revision = draft.revision
    try:
        content, report = prepare_artifact(config, parser_path=settings.DHCPD_PARSER_PATH)
    except ConfigurationError as exc:
        response = api_error(
            "validation_error", "Konfiguracja nie jest gotowa do generowania.", 400
        )
        value = json.loads(response.content)
        field = object_field(str(exc).split(":", 1)[0], data)
        value["error"]["fields"] = {
            field: [
                {"code": "invalid", "message": "Sprawdź pole i powiązane elementy konfiguracji."}
            ]
        }
        return JsonResponse(value, status=400)
    report["revision"] = current_revision
    status = report["syntax_status"]
    http_status = 200
    if status not in ("syntax_checked", "parser_unavailable"):
        http_status = 400 if status == "syntax_error" else 503
        report["error"] = {
            "code": status,
            "message": "Nie udało się potwierdzić składni konfiguracji.",
            "fields": {},
        }
    elif preview:
        report["content"] = content.decode("ascii")
    response = JsonResponse(report, status=http_status)
    response["X-Config-Revision"] = str(current_revision)
    return response


@method_actions(POST="read")
@input_errors
@csrf_protect
@require_http_methods(["POST"])
def validation(request, firewall_id):
    return evaluate(request, firewall_id, preview=False)


@method_actions(POST="read")
@input_errors
@csrf_protect
@require_http_methods(["POST"])
def preview(request, firewall_id):
    return evaluate(request, firewall_id, preview=True)
