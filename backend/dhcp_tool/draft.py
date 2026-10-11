"""Draft snapshots and validation shared by transactional editing services."""

from django.db.models import Prefetch
from rest_framework import serializers

from .generator import ConfigurationError, _mac, _network, validate_configuration
from .models import Pool, Reservation

OPTION_KEYS = {
    "gateway",
    "interface_address",
    "gaia_host_name_fallback",
    "default_lease_time",
    "max_lease_time",
    "domain",
    "dns",
}


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or data.keys() - self.fields.keys():
            raise serializers.ValidationError({"body": "Nieobsługiwane pola lub format danych."})
        return super().to_internal_value(data)


class OptionsSerializer(StrictSerializer):
    default_lease_time = serializers.IntegerField(
        min_value=1, max_value=2147483647, required=False, allow_null=True
    )
    max_lease_time = serializers.IntegerField(
        min_value=1, max_value=2147483647, required=False, allow_null=True
    )
    domain = serializers.CharField(max_length=253, required=False, allow_null=True)
    dns = serializers.ListField(
        child=serializers.IPAddressField(protocol="IPv4"),
        min_length=1,
        max_length=3,
        required=False,
        allow_null=True,
    )


class FirewallSerializer(StrictSerializer):
    name = serializers.RegexField(r"^[A-Za-z][A-Za-z0-9_-]{0,62}$", max_length=63)
    profile = serializers.ChoiceField(choices=["R81.10", "R82.10"])
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    location = serializers.CharField(max_length=150, required=False, allow_blank=True)
    management_address = serializers.IPAddressField(
        protocol="IPv4", required=False, allow_null=True
    )
    archived = serializers.BooleanField(required=False)


class InterfaceAddressesField(serializers.ListField):
    """Accept historical scalar values as well as bounded lists of IPv4 addresses."""

    def to_internal_value(self, data):
        if isinstance(data, str):
            return self.child.run_validation(data)
        return super().to_internal_value(data)


class SubnetSerializer(OptionsSerializer):
    name = serializers.CharField(max_length=150)
    cidr = serializers.CharField(max_length=18)
    interface = serializers.CharField(max_length=63, required=False, allow_blank=True)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    active = serializers.BooleanField(required=False)
    gateway = serializers.IPAddressField(protocol="IPv4", required=False, allow_null=True)
    interface_address = InterfaceAddressesField(
        child=serializers.IPAddressField(protocol="IPv4"),
        min_length=1,
        max_length=64,
        required=False,
        allow_null=True,
    )
    gaia_host_name_fallback = serializers.BooleanField(required=False, allow_null=True)


class PoolSerializer(StrictSerializer):
    start = serializers.IPAddressField(protocol="IPv4")
    end = serializers.IPAddressField(protocol="IPv4")
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    active = serializers.BooleanField(required=False)


class ReservationSerializer(StrictSerializer):
    subnet_id = serializers.UUIDField()
    name = serializers.RegexField(r"^[A-Za-z][A-Za-z0-9_-]{0,62}$", max_length=63)
    ip = serializers.IPAddressField(protocol="IPv4")
    mac = serializers.CharField(max_length=17)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    active = serializers.BooleanField(required=False)

    def validate_mac(self, value):
        try:
            return _mac(value, "mac")
        except ConfigurationError:
            raise serializers.ValidationError("Niepoprawny adres MAC.") from None


def pool_data(pool):
    return {
        key: str(getattr(pool, key)) if key == "id" else getattr(pool, key)
        for key in ["id", "start", "end", "description", "active"]
    }


def reservation_data(row):
    return {
        "id": str(row.pk),
        "subnet_id": str(row.subnet_id),
        "name": row.name,
        "mac": row.mac,
        "ip": row.ip,
        "description": row.description,
        "active": row.active,
        "created_at": row.created_at.isoformat(),
    }


def subnet_data(row, *, children=False):
    result = {
        "id": str(row.pk),
        "name": row.name,
        "cidr": row.cidr,
        "interface": row.interface,
        "description": row.description,
        "active": row.active,
        "created_at": row.created_at.isoformat(),
        **row.options,
    }
    if children:
        try:
            result["pool"] = pool_data(row.pool)
        except Pool.DoesNotExist:
            result["pool"] = None
        result["reservations"] = [reservation_data(r) for r in row.reservations.all()]
    return result


def snapshot(firewall, draft):
    rows = (
        firewall.subnets.order_by("id")
        .select_related("pool")
        .prefetch_related(Prefetch("reservations", queryset=Reservation.objects.order_by("id")))
    )
    return {
        "firewall_id": str(firewall.pk),
        "revision": draft.revision,
        "base_version_id": str(draft.base_version_id) if draft.base_version_id else None,
        "settings": draft.settings,
        "subnets": [subnet_data(row, children=True) for row in rows],
    }


def generator_config(firewall, draft):
    config = {
        "firewall": firewall.name,
        "profile": firewall.profile,
        **draft.settings,
        "subnets": [],
    }
    for row in (
        firewall.subnets.order_by("id")
        .select_related("pool")
        .prefetch_related(Prefetch("reservations", queryset=Reservation.objects.order_by("id")))
    ):
        subnet = {
            "cidr": row.cidr,
            "active": row.active,
            **row.options,
            "pools": [],
            "reservations": [],
        }
        try:
            pool = row.pool
            subnet["pools"] = [{"start": pool.start, "end": pool.end, "active": pool.active}]
        except Pool.DoesNotExist:
            pass
        subnet["reservations"] = [
            {"id": r.name, "mac": r.mac, "ip": r.ip, "active": r.active}
            for r in row.reservations.all()
        ]
        config["subnets"].append(subnet)
    return config


def validate_draft(firewall, draft):
    """Allow incomplete drafts, but never bypass validation by deactivating data."""
    validate_configuration(generator_config(firewall, draft), complete=False)


def normalize_subnet(row):
    row.cidr = str(_network(row.cidr, "cidr"))
