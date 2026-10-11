from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ._access_options import add_access_arguments, apply_access, validate_options


class Command(BaseCommand):
    help = "Set role and optionally replace or revoke a local account firewall scope."

    def add_arguments(self, parser):
        add_access_arguments(parser)

    def handle(self, *args, **options):
        firewalls = validate_options(options)
        with transaction.atomic():
            user = (
                get_user_model()
                .objects.select_for_update()
                .filter(username=options["username"])
                .first()
            )
            if user is None:
                raise CommandError("User not found.")
            apply_access(user, options["role"], firewalls)
        self.stdout.write("Access updated.")
