"""
Setup local development admin user.

Only runs when LOCAL_SETUP_ADMIN environment variable is set to 'true'.
Creates or updates a test admin user idempotently.

Usage:
    export LOCAL_SETUP_ADMIN=true
    export LOCAL_ADMIN_USERNAME=testadmin
    export LOCAL_ADMIN_PASSWORD=testpass123
    python manage.py setup_local_admin
"""

import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Setup local development admin user (only when LOCAL_SETUP_ADMIN=true)"

    def handle(self, *args, **options):
        # Only run if explicitly authorized
        if os.environ.get("LOCAL_SETUP_ADMIN", "").lower() != "true":
            self.stdout.write(
                self.style.WARNING(
                    "LOCAL_SETUP_ADMIN not set. Skipping admin user setup.\n"
                    "To enable: export LOCAL_SETUP_ADMIN=true"
                )
            )
            return

        username = os.environ.get("LOCAL_ADMIN_USERNAME", "testadmin")
        password = os.environ.get("LOCAL_ADMIN_PASSWORD")

        if not password:
            raise CommandError(
                "LOCAL_ADMIN_PASSWORD environment variable not set"
            )

        # Create or update user idempotently
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": f"{username}@localhost",
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f"✓ Created user: {username}")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"✓ User exists: {username}")
            )

        # Update password
        user.set_password(password)
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"✓ Admin user {username} configured (password updated)"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "\nNOTE: Credentials are for development only.\n"
                "Do NOT use in production without changing password."
            )
        )
