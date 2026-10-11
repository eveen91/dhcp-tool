"""Full configuration CSV: signed, scoped previews and transactional imports."""

import copy
import csv
import io
import json
import uuid

from django.core import signing
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from .auth import api_error, role_for
from .csv_views import MAX_CSV_BYTES, MAX_ROWS, bad_csv, text_cell, unescape
from .draft import (
    OPTION_KEYS,
    FirewallSerializer,
    OptionsSerializer,
    PoolSerializer,
    ReservationSerializer,
    SubnetSerializer,
    snapshot,
    validate_draft,
)
from .draft_views import InputError, body, input_errors, locked, method_actions, validated
from .generator import validate_configuration
from .models import AuditEvent, Draft, Firewall, Pool, Reservation, Subnet

COLUMNS = [
    "kind",
    "action",
    "id",
    "subnet_cidr",
    "name",
    "start",
    "end",
    "ip",
    "mac",
    "description",
    "interface",
    "active",
    "options",
]
SALT = "dhcp-tool.csv-configuration.v1"


def records(fw, draft):
    data = snapshot(fw, draft)
    rows = {}

    def add(kind, identifier, **values):
        rows[(kind, identifier)] = dict.fromkeys(COLUMNS, "") | {
            "kind": kind,
            "action": "upsert",
            "id": identifier,
            **values,
        }

    add(
        "firewall",
        str(fw.pk),
        name=fw.name,
        description=fw.description,
        options=json.dumps(
            {k: getattr(fw, k) for k in ("profile", "location", "management_address")},
            sort_keys=True,
        ),
    )
    add("settings", "", options=json.dumps(draft.settings, sort_keys=True))
    for subnet in data["subnets"]:
        common = {"subnet_cidr": subnet["cidr"], "active": str(subnet["active"]).lower()}
        add(
            "subnet",
            subnet["id"],
            **common,
            name=subnet["name"],
            interface=subnet["interface"],
            description=subnet["description"],
            options=json.dumps({k: subnet[k] for k in OPTION_KEYS if k in subnet}, sort_keys=True),
        )
        pool = subnet["pool"]
        if pool:
            add(
                "pool",
                pool["id"],
                subnet_cidr=subnet["cidr"],
                start=pool["start"],
                end=pool["end"],
                description=pool["description"],
                active=str(pool["active"]).lower(),
            )
        for r in subnet["reservations"]:
            add(
                "reservation",
                r["id"],
                subnet_cidr=subnet["cidr"],
                name=r["name"],
                ip=r["ip"],
                mac=r["mac"],
                description=r["description"],
                active=str(r["active"]).lower(),
            )
    return data, rows


def plan(fw, draft, text, user, new_ids=None):
    if not isinstance(text, str) or "\x00" in text:
        bad_csv()
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        bad_csv()
    if size > MAX_CSV_BYTES:
        raise InputError(api_error("request_too_large", "CSV może mieć maksymalnie 32 KiB.", 413))
    before, original = records(fw, draft)
    proposed = copy.deepcopy(original)
    new_ids = dict(new_ids or {})
    reader = csv.DictReader(io.StringIO(text.removeprefix("\ufeff")), strict=True)
    commands = []
    seen = set()
    try:
        if reader.fieldnames != COLUMNS:
            bad_csv()
        for line, raw in enumerate(reader, 2):
            if line > MAX_ROWS + 1 or None in raw or any(v is None for v in raw.values()):
                bad_csv(line)
            row = {k: unescape(v) for k, v in raw.items()}
            kind, identifier = row["kind"], row["id"]
            if kind not in ("firewall", "settings", "subnet", "pool", "reservation"):
                bad_csv(line)
            allowed = {
                "firewall": {"name", "description", "options"},
                "settings": {"options"},
                "subnet": {"subnet_cidr", "name", "description", "interface", "active", "options"},
                "pool": {"subnet_cidr", "start", "end", "description", "active"},
                "reservation": {"subnet_cidr", "name", "ip", "mac", "description", "active"},
            }[kind] | {"kind", "action", "id"}
            if any(value for key, value in row.items() if key not in allowed):
                bad_csv(line)
            if row["action"] not in ("upsert", "delete"):
                bad_csv(line)
            if kind == "settings":
                if identifier or row["action"] == "delete":
                    bad_csv(line)
            elif identifier:
                try:
                    identifier = str(uuid.UUID(identifier))
                except ValueError:
                    bad_csv(line)
                if (kind, identifier) not in original:
                    bad_csv(line)
            elif kind == "firewall" or row["action"] == "delete":
                bad_csv(line)
            else:
                identifier = new_ids.setdefault(str(line), str(uuid.uuid4()))
            key = (kind, identifier)
            if key in seen or (kind == "firewall" and row["action"] == "delete"):
                bad_csv(line)
            seen.add(key)
            row["id"] = identifier
            if row["action"] == "delete":
                proposed.pop(key)
            else:
                if kind in ("subnet", "pool", "reservation") and row["active"] not in (
                    "true",
                    "false",
                ):
                    bad_csv(line)
                proposed[key] = row
            commands.append((key, row))
    except csv.Error:
        bad_csv()
    if not commands:
        bad_csv()
    # Cascades are explicit preview entries, including children omitted from the file.
    removed_cidrs = {
        original[key]["subnet_cidr"]
        for key, row in commands
        if key[0] == "subnet" and row["action"] == "delete"
    }
    for key, row in commands:
        if (
            key[0] in ("pool", "reservation")
            and row["action"] == "upsert"
            and row["subnet_cidr"] in removed_cidrs
        ):
            bad_csv()
    for key, row in list(proposed.items()):
        if key[0] in ("pool", "reservation") and row["subnet_cidr"] in removed_cidrs:
            proposed.pop(key)

    def options(row):
        try:
            value = json.loads(row["options"] or "{}")
        except (ValueError, TypeError):
            bad_csv()
        if not isinstance(value, dict):
            bad_csv()
        return value

    fwrow = proposed[("firewall", str(fw.pk))]
    meta = validated(
        FirewallSerializer,
        {"name": fwrow["name"], "description": fwrow["description"], **options(fwrow)},
    )
    if set(meta) - {"name", "description", "profile", "location", "management_address"}:
        bad_csv()
    if any(getattr(fw, k) != v for k, v in meta.items()) and role_for(user) != "admin":
        raise InputError(
            api_error("forbidden", "Zmiana metadanych firewalla wymaga roli admin.", 403)
        )
    candidate_fw = copy.copy(fw)
    for key, value in meta.items():
        setattr(candidate_fw, key, value)
    candidate_fw.full_clean()
    settings = {
        k: v
        for k, v in validated(OptionsSerializer, options(proposed[("settings", "")])).items()
        if v is not None
    }
    subnets = {}
    pools = []
    reservations = []
    for (kind, identifier), row in proposed.items():
        if kind != "subnet":
            continue
        if options(row).keys() - OPTION_KEYS:
            bad_csv()
        value = validated(
            SubnetSerializer,
            {
                "name": row["name"],
                "cidr": row["subnet_cidr"],
                "interface": row["interface"],
                "description": row["description"],
                "active": row["active"] == "true",
                **options(row),
            },
        )
        obj = Subnet(
            id=identifier,
            firewall=fw,
            **{k: v for k, v in value.items() if k not in OPTION_KEYS},
            options={k: v for k, v in value.items() if k in OPTION_KEYS and v is not None},
        )
        from .draft import normalize_subnet

        normalize_subnet(obj)
        if obj.cidr in subnets:
            bad_csv()
        subnets[obj.cidr] = obj
    occupied = set()
    for (kind, identifier), row in proposed.items():
        if kind not in ("pool", "reservation"):
            continue
        subnet = subnets.get(row["subnet_cidr"])
        if not subnet:
            bad_csv()
        common = {"description": row["description"], "active": row["active"] == "true"}
        if kind == "pool":
            if subnet.pk in occupied:
                bad_csv()
            occupied.add(subnet.pk)
            values = validated(PoolSerializer, {**common, "start": row["start"], "end": row["end"]})
            pools.append(Pool(id=identifier, subnet=subnet, **values))
        else:
            values = validated(
                ReservationSerializer,
                {
                    **common,
                    "subnet_id": subnet.pk,
                    "name": row["name"],
                    "ip": row["ip"],
                    "mac": row["mac"],
                },
            )
            reservations.append(Reservation(id=identifier, **values))
    config = {"firewall": meta["name"], "profile": meta["profile"], **settings, "subnets": []}
    for s in subnets.values():
        config["subnets"].append(
            {
                "cidr": s.cidr,
                "active": s.active,
                **s.options,
                "pools": [
                    {"start": p.start, "end": p.end, "active": p.active}
                    for p in pools
                    if p.subnet_id == s.pk
                ],
                "reservations": [
                    {"id": r.name, "ip": r.ip, "mac": r.mac, "active": r.active}
                    for r in reservations
                    if r.subnet_id == s.pk
                ],
            }
        )
    validate_configuration(config, complete=False)
    # Database uniqueness also applies to disabled reservations.
    if len({(r.subnet_id, r.ip) for r in reservations}) != len(reservations):
        bad_csv()
    changes = []
    counts = dict.fromkeys(("create", "update", "delete", "unchanged"), 0)
    for key in sorted(original.keys() | proposed.keys()):
        previous, after = original.get(key), proposed.get(key)
        operation = (
            "create"
            if previous is None
            else "delete"
            if after is None
            else "unchanged"
            if previous == after
            else "update"
        )
        counts[operation] += 1
        if operation != "unchanged":
            changes.append(
                {
                    "row": len(changes) + 1,
                    "kind": key[0],
                    "operation": operation,
                    "before": previous,
                    "after": after,
                }
            )
    return (
        before,
        meta,
        settings,
        list(subnets.values()),
        pools,
        reservations,
        changes,
        counts,
        new_ids,
    )


@method_actions(GET="read")
@require_http_methods(["GET"])
def export_csv(request, firewall_id):
    if request.GET:
        return api_error("validation_error", "Eksport nie przyjmuje parametrów.", 400)
    with transaction.atomic():
        fw = Firewall.objects.select_for_update().get(pk=firewall_id)
        draft = Draft.objects.get(firewall=fw)
        _, rows = records(fw, draft)
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for row in rows.values():
        writer.writerow([text_cell(row[k]) for k in COLUMNS])
    response = HttpResponse("\ufeff" + out.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="configuration.csv"'
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
        *_, changes, counts, new_ids = plan(fw, draft, data["csv"], request.user)
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
        return api_error("invalid_preview", "Wykonaj nowy podgląd CSV.", 400)
    if saved["user"] != str(request.user.pk) or saved["firewall"] != str(firewall_id):
        return api_error("invalid_preview", "Wykonaj nowy podgląd CSV.", 400)
    with transaction.atomic():
        fw, draft = locked(request)
        if saved["revision"] != draft.revision:
            return api_error("revision_conflict", "Wykonaj nowy podgląd CSV.", 409)
        old_meta = {
            k: getattr(fw, k)
            for k in ("name", "description", "profile", "location", "management_address")
        }
        before, meta, settings, subnets, pools, reservations, _, counts, _ = plan(
            fw, draft, saved["csv"], request.user, saved["new_ids"]
        )
        if counts["delete"] and data.get("confirm_deletions") is not True:
            return api_error(
                "deletion_confirmation_required", "Potwierdź każde usunięcie z podglądu.", 400
            )
        old_dates = {s["id"]: s["created_at"] for s in before["subnets"]}
        old_dates.update(
            {r["id"]: r["created_at"] for s in before["subnets"] for r in s["reservations"]}
        )
        for key, value in meta.items():
            setattr(fw, key, value)
        fw.full_clean()
        fw.save(update_fields=list(meta))
        fw.subnets.all().delete()
        Subnet.objects.bulk_create(subnets)
        Pool.objects.bulk_create(pools)
        Reservation.objects.bulk_create(reservations)
        for model, rows in ((Subnet, subnets), (Reservation, reservations)):
            preserved = []
            for row in rows:
                if str(row.pk) in old_dates:
                    row.created_at = parse_datetime(old_dates[str(row.pk)])
                    preserved.append(row)
            model.objects.bulk_update(preserved, ["created_at"])
        draft.settings = settings
        draft.revision += 1
        draft.save(update_fields=["settings", "revision"])
        validate_draft(fw, draft)
        after = snapshot(fw, draft)
        AuditEvent.objects.create(
            firewall=fw,
            actor=request.user,
            operation="csv_import",
            object_type="draft",
            object_id=fw.pk,
            revision=draft.revision,
            before={"firewall": old_meta, "draft": before},
            after={"firewall": meta, "draft": after},
        )
    response = JsonResponse(after)
    response["X-Config-Revision"] = str(draft.revision)
    return response
