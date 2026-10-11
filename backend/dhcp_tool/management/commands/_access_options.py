import logging
import uuid

from django.core.management.base import CommandError

from dhcp_tool.models import Account, Firewall, FirewallAccess, Role

logger = logging.getLogger("dhcp_tool.security")


def add_access_arguments(parser):
    parser.add_argument("username")
    parser.add_argument("--role", choices=Role.values, required=True)
    parser.add_argument(
        "--firewall",
        action="append",
        default=None,
        type=uuid.UUID,
        help="Repeat to replace the allowed firewall list.",
    )
    parser.add_argument("--clear-firewalls", action="store_true")


def validate_options(options):
    if options["role"] not in Role.values:
        raise CommandError("Unknown role.")
    identifiers = options["firewall"]
    if identifiers is not None and options["clear_firewalls"]:
        raise CommandError("Choose --firewall or --clear-firewalls.")
    if identifiers is None:
        return [] if options["clear_firewalls"] else None
    try:
        identifiers = {uuid.UUID(str(value)) for value in identifiers}
    except (ValueError, TypeError, AttributeError) as exc:
        raise CommandError("Invalid firewall identifier.") from exc
    firewalls = list(Firewall.objects.filter(pk__in=identifiers))
    if len(firewalls) != len(identifiers):
        raise CommandError("Firewall not found.")
    return firewalls


def apply_access(user, role, firewalls):
    if user.is_superuser and role != Role.ADMIN:
        raise CommandError("A Django superuser always has administrator access.")
    Account.objects.update_or_create(user=user, defaults={"role": role})
    if firewalls is not None:
        FirewallAccess.objects.filter(user=user).delete()
        FirewallAccess.objects.bulk_create(
            [FirewallAccess(user=user, firewall=fw) for fw in firewalls]
        )
    logger.info("Access changed", extra={"event": "access_changed"})
