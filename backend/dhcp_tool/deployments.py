"""Manual ledger queries and presentation; no device verification is implied."""

from django.db.models import F

from .models import Deployment

ORDER = ("-occurred_at", "-created_at", "-id")


def entries(firewall):
    # Select the hash without loading the potentially large artifact content.
    return (
        Deployment.objects.filter(version__firewall=firewall)
        .select_related("version", "operator")
        .defer("version__snapshot")
        .annotate(artifact_hash=F("version__artifact__sha256"))
    )


def deployment_data(entry):
    expected = entry.artifact_hash
    return {
        "id": str(entry.pk),
        "version_id": str(entry.version_id),
        "version_number": entry.version.number,
        "profile": entry.version.profile,
        "operator": entry.operator.get_username() if entry.operator else None,
        "occurred_at": entry.occurred_at.isoformat(),
        "created_at": entry.created_at.isoformat(),
        "revision": entry.revision,
        "status": entry.status,
        "confirmation": "manual",
        "note": entry.note,
        "ticket": entry.ticket,
        "supplied_hash": entry.supplied_hash,
        "artifact_sha256": expected,
        "hash_comparison": (
            "not_supplied"
            if not entry.supplied_hash
            else "match"
            if entry.supplied_hash == expected
            else "mismatch"
        ),
    }


def last_successful_deployment(firewall):
    return entries(firewall).filter(status="successful").order_by(*ORDER).first()
