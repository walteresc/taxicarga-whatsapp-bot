"""Assign WhatsApp permission role to E2E user."""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Assign WhatsApp permissions to E2E test user"

    def handle(self, *args, **options):
        user = User.objects.filter(username='e2e_test_user').first()
        if not user:
            self.stdout.write(self.style.ERROR("E2E user not found"))
            return

        # Set as superuser to grant all permissions
        user.is_superuser = True
        user.is_staff = True
        user.save()

        self.stdout.write(
            self.style.SUCCESS(
                f'Assigned WhatsApp permissions to {user.username}\n'
                f'is_superuser: True\n'
                f'is_staff: True'
            )
        )
