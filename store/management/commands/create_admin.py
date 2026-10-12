import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the initial Django superuser from ADMIN_* environment variables."

    def handle(self, *args, **options):
        username = os.getenv("ADMIN_USERNAME", "").strip()
        password = os.getenv("ADMIN_PASSWORD", "")
        email = os.getenv("ADMIN_EMAIL", "").strip()

        missing = [
            name
            for name, value in (
                ("ADMIN_USERNAME", username),
                ("ADMIN_PASSWORD", password),
                ("ADMIN_EMAIL", email),
            )
            if not value
        ]
        if missing:
            raise CommandError(
                "Set these environment variables before running create_admin: "
                + ", ".join(missing)
            )

        User = get_user_model()
        existing = User.objects.filter(username=username).first()
        if existing:
            self.stdout.write(
                self.style.WARNING(
                    f"User '{username}' already exists; no changes were made."
                )
            )
            return

        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        self.stdout.write(
            self.style.SUCCESS(f"Superuser '{user.get_username()}' created successfully.")
        )
