from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.db import connection
import os


class Command(BaseCommand):
    help = "Setup E2E environment for FASE 5B"

    def handle(self, *args, **options):
        # Verify we're on E2E database
        current_db = connection.settings_dict.get('NAME', '')
        if 'e2e' not in current_db.lower():
            self.stderr.write(f"ERROR: Not E2E database ({current_db}). Refusing to proceed.")
            return

        self.stdout.write(f"Setting up FASE 5B E2E on {current_db}")

        # Create/update user
        password = os.environ.get('E2E_TEST_PASSWORD', 'e2e_test_pass')
        user, created = User.objects.get_or_create(
            username='e2e_test',
            defaults={'is_active': True, 'is_staff': True, 'email': 'e2e@local'}
        )
        user.set_password(password)
        user.save()

        self.stdout.write(f"User e2e_test: {'created' if created else 'updated'}")

        # Add to Administrador group
        admin_group, _ = Group.objects.get_or_create(name='Administrador')
        user.groups.add(admin_group)

        self.stdout.write("✓ FASE 5B E2E environment ready")
