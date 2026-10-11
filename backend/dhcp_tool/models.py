"""Persistent security and DHCP configuration domain models."""

import uuid

from django.conf import settings
from django.db import models


class Role(models.TextChoices):
    READER = "reader", "Odczyt"
    EDITOR = "editor", "Edycja"
    OPERATOR = "operator", "Ewidencja wdrożeń"
    ADMIN = "admin", "Administrator"


class Account(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="access_account",
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.READER)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=Role.values), name="account_valid_role"
            )
        ]


class Firewall(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=63, unique=True)
    profile = models.CharField(max_length=6, choices=[("R81.10", "R81.10"), ("R82.10", "R82.10")])
    description = models.CharField(max_length=1000, blank=True)
    location = models.CharField(max_length=150, blank=True)
    management_address = models.GenericIPAddressField(protocol="IPv4", null=True, blank=True)
    archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(profile__in=["R81.10", "R82.10"]), name="firewall_valid_profile"
            )
        ]


class FirewallAccess(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="firewall_access"
    )
    firewall = models.ForeignKey(Firewall, on_delete=models.CASCADE, related_name="access_grants")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "firewall"], name="unique_fw_access")
        ]


class LoginBucket(models.Model):
    # HMAC keys avoid storing usernames or client addresses in the limiter.
    key = models.CharField(max_length=64, primary_key=True)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)


class Draft(models.Model):
    firewall = models.OneToOneField(Firewall, on_delete=models.PROTECT, primary_key=True)
    revision = models.PositiveBigIntegerField(default=1)
    settings = models.JSONField(default=dict)
    base_version = models.ForeignKey("Version", null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(revision__gte=1), name="draft_positive_revision"
            )
        ]


class Subnet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    firewall = models.ForeignKey(Firewall, on_delete=models.PROTECT, related_name="subnets")
    name = models.CharField(max_length=150)
    cidr = models.CharField(max_length=18)
    interface = models.CharField(max_length=63, blank=True)
    description = models.CharField(max_length=1000, blank=True)
    options = models.JSONField(default=dict, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["firewall", "active"])]
        constraints = [
            models.UniqueConstraint(fields=["firewall", "cidr"], name="subnet_unique_cidr")
        ]


class Pool(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subnet = models.OneToOneField(Subnet, on_delete=models.CASCADE, related_name="pool")
    start = models.GenericIPAddressField(protocol="IPv4")
    end = models.GenericIPAddressField(protocol="IPv4")
    description = models.CharField(max_length=1000, blank=True)
    active = models.BooleanField(default=True)


class Reservation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subnet = models.ForeignKey(Subnet, on_delete=models.CASCADE, related_name="reservations")
    name = models.CharField(max_length=63)
    mac = models.CharField(max_length=17)
    ip = models.GenericIPAddressField(protocol="IPv4")
    description = models.CharField(max_length=1000, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["subnet", "active"])]
        constraints = [
            models.UniqueConstraint(fields=["subnet", "ip"], name="reservation_unique_subnet_ip")
        ]


class Version(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    firewall = models.ForeignKey(Firewall, on_delete=models.PROTECT, related_name="versions")
    number = models.PositiveBigIntegerField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField()
    snapshot = models.JSONField()
    profile = models.CharField(max_length=6, choices=Firewall._meta.get_field("profile").choices)
    generator_version = models.CharField(max_length=63)

    class Meta:
        indexes = [models.Index(fields=["firewall", "-created_at"])]
        constraints = [
            models.UniqueConstraint(fields=["firewall", "number"], name="version_unique_number"),
            models.CheckConstraint(
                condition=models.Q(number__gte=1), name="version_positive_number"
            ),
        ]


class Artifact(models.Model):
    version = models.OneToOneField(Version, on_delete=models.PROTECT, primary_key=True)
    content = models.BinaryField()
    sha256 = models.CharField(max_length=64)
    validation = models.JSONField(default=dict)


class Deployment(models.Model):
    revision = models.PositiveBigIntegerField(default=1)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(Version, on_delete=models.PROTECT, related_name="deployments")
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=16, choices=[(s, s) for s in ["planned", "successful", "failed", "cancelled"]]
    )
    confirmation = models.CharField(max_length=63, default="manual")
    note = models.TextField(blank=True)
    ticket = models.CharField(max_length=150, blank=True)
    supplied_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [models.Index(fields=["version", "-occurred_at"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["planned", "successful", "failed", "cancelled"]),
                name="deployment_valid_status",
            )
        ]


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    firewall = models.ForeignKey(Firewall, on_delete=models.PROTECT, related_name="audit_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    operation = models.CharField(max_length=32)
    object_type = models.CharField(max_length=32)
    object_id = models.UUIDField()
    request_id = models.UUIDField(default=uuid.uuid4)
    revision = models.PositiveBigIntegerField()
    before = models.JSONField(null=True)
    after = models.JSONField(null=True)

    class Meta:
        indexes = [models.Index(fields=["firewall", "-created_at"])]
