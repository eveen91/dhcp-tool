"""Immutable version metadata and comparisons independent of live draft rows."""

import difflib

from .deployments import last_successful_deployment

GENERATOR_VERSION = "1.0.0"


def version_data(version, *, detail=False):
    artifact = version.artifact
    metadata_only = hasattr(version, "artifact_length")
    author = (
        (version.snapshot_author or {"id": version.author_id})
        if metadata_only
        else version.snapshot.get("author", {"id": version.author_id})
    )
    name = (
        version.snapshot_name if metadata_only else version.snapshot.get("firewall", {}).get("name")
    )
    revision = version.snapshot_revision if metadata_only else version.snapshot.get("revision")
    result = {
        "id": str(version.pk),
        "firewall_id": str(version.firewall_id),
        "number": version.number,
        "author": author,
        "created_at": version.created_at.isoformat(),
        "description": version.description,
        "profile": version.profile,
        "generator_version": version.generator_version,
        "firewall_name": name,
        "revision": revision,
        "sha256": artifact.sha256,
        "artifact_bytes": version.artifact_length if metadata_only else len(artifact.content),
        "validation": artifact.validation,
    }
    if detail:
        result["snapshot"] = version.snapshot
    return result


def entities(snapshot):
    result = {}
    fw_id = snapshot["firewall_id"]
    result[("settings", fw_id)] = snapshot["settings"]
    result[("firewall", fw_id)] = {
        k: v
        for k, v in snapshot.get("firewall", {}).items()
        if k in {"name", "profile", "description", "location", "management_address"}
    }
    for subnet in snapshot["subnets"]:
        result[("subnet", subnet["id"])] = {
            k: v for k, v in subnet.items() if k not in {"id", "created_at", "pool", "reservations"}
        }
        pool = subnet["pool"]
        if pool:
            result[("pool", pool["id"])] = {
                **{k: v for k, v in pool.items() if k != "id"},
                "subnet_id": subnet["id"],
            }
        for row in subnet["reservations"]:
            result[("reservation", row["id"])] = {
                k: v for k, v in row.items() if k not in {"id", "created_at"}
            }
    return result


def semantic_diff(before, after):
    old, new = entities(before), entities(after)
    changes = []
    for key in sorted(old.keys() | new.keys()):
        kind, identifier = key
        base = {"object_type": kind, "object_id": identifier}
        if key not in old or key not in new:
            changes.append(
                {
                    "kind": "added" if key not in old else "removed",
                    **base,
                    "field": None,
                    "before": old.get(key),
                    "after": new.get(key),
                }
            )
            continue
        for field in sorted(old[key].keys() | new[key].keys()):
            if field not in old[key] or field not in new[key] or old[key][field] != new[key][field]:
                changes.append(
                    {
                        "kind": "changed",
                        **base,
                        "field": field,
                        "before": old[key].get(field),
                        "after": new[key].get(field),
                    }
                )
    return changes


def compare_versions(before, after):
    text = "".join(
        difflib.unified_diff(
            bytes(before.artifact.content).decode("ascii").splitlines(keepends=True),
            bytes(after.artifact.content).decode("ascii").splitlines(keepends=True),
            fromfile=f"version-{before.number}",
            tofile=f"version-{after.number}",
        )
    )
    return {"text": text, "semantic": semantic_diff(before.snapshot, after.snapshot)}


def last_successful_version(firewall):
    event = last_successful_deployment(firewall)
    return event.version if event else None
