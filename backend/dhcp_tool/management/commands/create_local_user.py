import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from ._access_options import add_access_arguments, apply_access, validate_options


class Command(BaseCommand):
    help = "Create a local account; password is read interactively, never from arguments."

    def add_arguments(self, parser):
        add_access_arguments(parser)

    def handle(self, *args, **options):
        firewalls = validate_options(options)
        user = get_user_model()(username=options["username"])
        try:
            user.full_clean(exclude=["password"])
            password = getpass.getpass("Password: ")
            confirmation = getpass.getpass("Confirm password: ")
            if password != confirmation:
                raise CommandError("Passwords do not match.")
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(
                "Invalid username or password; password must be strong and at least 12 characters."
            ) from exc
        except (EOFError, KeyboardInterrupt) as exc:
            raise CommandError("Account creation cancelled.") from exc
        try:
            with transaction.atomic():
                user.set_password(password)
                user.save()
                apply_access(user, options["role"], firewalls or [])
        except IntegrityError as exc:
            raise CommandError("Account could not be created.") from exc
        self.stdout.write("Local account created.")
