"""Create the one application account without putting passwords in arguments."""

import getpass
import sys
from pathlib import Path
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Create the single owner. Read password from --password-file, stdin, or a hidden prompt."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--password-file")

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.exists():
            raise CommandError(
                "An account already exists; bootstrap never changes existing accounts."
            )
        if options["password_file"]:
            password = Path(options["password_file"]).read_text().rstrip("\r\n")
        elif not sys.stdin.isatty():
            password = sys.stdin.readline().rstrip("\r\n")
        else:
            password = getpass.getpass("New owner password: ")
            if password != getpass.getpass("Repeat password: "):
                raise CommandError("Passwords do not match.")
        owner = User(username=options["username"])
        try:
            validate_password(password, owner)
            owner.full_clean(exclude=["password"])
        except Exception as exc:
            raise CommandError(
                "Owner details or password do not meet validation requirements."
            ) from exc
        owner.set_password(password)
        owner.save()
        self.stdout.write(
            self.style.SUCCESS("Owner created. Complete your profile after signing in.")
        )
