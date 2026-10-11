"""Scoped reservation CSV, with signed previews and atomic, revision-checked imports."""

import copy
import csv
import io
import uuid

from django.core import signing
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from rest_framework import serializers

from .auth import api_error
from .draft import ReservationSerializer, generator_config, snapshot, validate_draft
from .draft_views import InputError, body, input_errors, locked, method_actions, validated
from .generator import validate_configuration
from .models import AuditEvent, Reservation

COLUMNS = ["action", "id", "subnet_cidr", "name", "ip", "mac", "description", "active"]
SALT = "dhcp-tool.csv-reservations.v1"
MAX_CSV_BYTES = 32768
MAX_ROWS = 500


def text_cell(value):
    value = str(value)
    if value.lstrip().startswith(("=", "+", "-", "@", "'")):
        return "'" + value
    return value


def unescape(value):
    if value.startswith("'") and value[1:].lstrip().startswith(("=", "+", "-", "@", "'")):
        return value[1:]
    return value


def bad_csv(row=None):
    key = "csv" if row is None else f"csv.row.{row}"
    raise serializers.ValidationError({key: "Niepoprawny format lub powiązania CSV."})


def plan(fw, draft, csv_text, *, new_ids=None):
    if not isinstance(csv_text, str):
        bad_csv()
    try:
        size = len(csv_text.encode("utf-8"))
    except UnicodeEncodeError:
        bad_csv()
    if "\x00" in csv_text:
        bad_csv()
    if size > MAX_CSV_BYTES:
        raise InputError(api_error("request_too_large", "CSV może mieć maksymalnie 32 KiB.", 413))
    new_ids = dict(new_ids or {})
    original = snapshot(fw, draft)
    subnets = {s["cidr"]: s for s in original["subnets"]}
    existing = {r["id"]: r for s in subnets.values() for r in s["reservations"]}
    proposed = copy.deepcopy(existing)
    reader = csv.DictReader(io.StringIO(csv_text.removeprefix("\ufeff")), strict=True)
    try:
        if reader.fieldnames != COLUMNS:
            bad_csv()
    except csv.Error:
        bad_csv()
    changes = []
    commands = []
    counts = {"create": 0, "update": 0, "delete": 0, "unchanged": 0}
    seen = set()
    try:
        for line, row in enumerate(reader, 2):
            if line > MAX_ROWS + 1 or None in row or any(v is None for v in row.values()):
                bad_csv(line)
            row = {key: unescape(value) for key, value in row.items()}
            identifier = row["id"].strip()
            action = row["action"]
            if action not in ("upsert", "delete"):
                bad_csv(line)
            if identifier:
                try:
                    identifier = str(uuid.UUID(identifier))
                except ValueError:
                    bad_csv(line)
                if identifier not in existing:
                    bad_csv(line)
            else:
                if action == "delete":
                    bad_csv(line)
                identifier = new_ids.setdefault(str(line), str(uuid.uuid4()))
            if identifier in seen:
                bad_csv(line)
            seen.add(identifier)
            before = existing.get(identifier)
            if action == "delete":
                proposed.pop(identifier)
                after = None
                kind = "delete"
                data = None
            else:
                subnet = subnets.get(row["subnet_cidr"])
                if not subnet or row["active"] not in ("true", "false"):
                    bad_csv(line)
                data = validated(
                    ReservationSerializer,
                    {
                        "subnet_id": subnet["id"],
                        "name": row["name"],
                        "ip": row["ip"],
                        "mac": row["mac"],
                        "description": row["description"],
                        "active": row["active"] == "true",
                    },
                )
                data["subnet_id"] = str(data["subnet_id"])
                after = {"id": identifier, **data}
                proposed[identifier] = after
                previous = {k: before[k] for k in after} if before else None
                kind = (
                    "create" if before is None else "unchanged" if previous == after else "update"
                )
            counts[kind] += 1
            if kind != "unchanged":

                def display(value):
                    if value is None:
                        return None
                    cidr = next(c for c, s in subnets.items() if s["id"] == value["subnet_id"])
                    return {**value, "subnet_cidr": cidr}

                changes.append(
                    {
                        "row": line,
                        "operation": kind,
                        "before": display(before),
                        "after": display(after),
                    }
                )
                commands.append({"id": identifier, "operation": kind, "data": data})
    except csv.Error:
        bad_csv()
    if not seen:
        bad_csv()
    config = generator_config(fw, draft)
    for subnet in config["subnets"]:
        sid = subnets[subnet["cidr"]]["id"]
        subnet["reservations"] = [
            {"id": r["name"], "mac": r["mac"], "ip": r["ip"], "active": r["active"]}
            for r in proposed.values()
            if r["subnet_id"] == sid
        ]
    validate_configuration(config, complete=False)
    return original, commands, changes, counts, new_ids


@method_actions(GET="read")
@require_http_methods(["GET"])
def export_csv(request, firewall_id):
    if request.GET:
        return api_error("validation_error", "Eksport nie przyjmuje parametrów.", 400)
    with transaction.atomic():
        from .models import Draft, Firewall

        fw = Firewall.objects.select_for_update().get(pk=firewall_id)
        draft = Draft.objects.get(firewall=fw)
        data = snapshot(fw, draft)
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for subnet in sorted(data["subnets"], key=lambda s: s["cidr"]):
        for row in sorted(subnet["reservations"], key=lambda r: (r["name"], r["id"])):
            writer.writerow(
                [
                    text_cell(v)
                    for v in [
                        "upsert",
                        row["id"],
                        subnet["cidr"],
                        row["name"],
                        row["ip"],
                        row["mac"],
                        row["description"],
                        str(row["active"]).lower(),
                    ]
                ]
            )
    response = HttpResponse("\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="reservations.csv"'
    response["X-Config-Revision"] = str(draft.revision)
    return response


@method_actions(POST="edit")
@input_errors
@csrf_protect
@require_http_methods(["POST"])
def preview_csv(request, firewall_id):
    data = body(request)
    if set(data) != {"csv"}:
        bad_csv()
    with transaction.atomic():
        fw, draft = locked(request)
        _, _, changes, counts, new_ids = plan(fw, draft, data["csv"])
        token = signing.dumps(
            {
                "csv": data["csv"],
                "new_ids": new_ids,
                "revision": draft.revision,
                "firewall": str(fw.pk),
                "user": str(request.user.pk),
            },
            salt=SALT,
            compress=True,
        )
    return JsonResponse(
        {"token": token, "revision": draft.revision, "counts": counts, "changes": changes}
    )


@method_actions(POST="edit")
@input_errors
@csrf_protect
@require_http_methods(["POST"])
def apply_csv(request, firewall_id):
    data = body(request)
    if set(data) - {"token", "confirm_deletions"} or not isinstance(data.get("token"), str):
        bad_csv()
    try:
        saved = signing.loads(data["token"], salt=SALT, max_age=600)
    except signing.BadSignature:
        return api_error(
            "invalid_preview", "Podgląd wygasł lub jest niepoprawny. Wykonaj nowy.", 400
        )
    if saved["user"] != str(request.user.pk) or saved["firewall"] != str(firewall_id):
        return api_error("invalid_preview", "Podgląd nie dotyczy tego konta lub firewalla.", 400)
    with transaction.atomic():
        fw, draft = locked(request)
        if saved["revision"] != draft.revision:
            return api_error("revision_conflict", "Podgląd jest nieaktualny. Wykonaj nowy.", 409)
        before, commands, _, counts, _ = plan(fw, draft, saved["csv"], new_ids=saved["new_ids"])
        if counts["delete"] and data.get("confirm_deletions") is not True:
            return api_error(
                "deletion_confirmation_required", "Potwierdź każde usunięcie z podglądu.", 400
            )
        for command in commands:
            rows = Reservation.objects.filter(subnet__firewall=fw, pk=command["id"])
            if command["operation"] == "delete":
                rows.delete()
            elif command["operation"] == "create":
                Reservation.objects.create(id=command["id"], **command["data"])
            else:
                rows.update(**command["data"])
        validate_draft(fw, draft)
        draft.revision += 1
        draft.save(update_fields=["revision"])
        after = snapshot(fw, draft)
        AuditEvent.objects.create(
            firewall=fw,
            actor=request.user,
            operation="csv_import",
            object_type="draft",
            object_id=fw.pk,
            revision=draft.revision,
            before=before,
            after=after,
        )
    response = JsonResponse(after)
    response["X-Config-Revision"] = str(draft.revision)
    return response
