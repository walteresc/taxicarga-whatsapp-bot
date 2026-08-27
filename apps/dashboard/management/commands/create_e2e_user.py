"""Create/verify E2E test user in database."""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Create or verify E2E test user"

    def handle(self, *args, **options):
        username = 'e2e_test_user'
        password = 'e2e_test_pass_12345'

        # Create or get user
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': 'e2e@test.local',
                'is_active': True,
                'is_staff': False,
                'is_superuser': False,
            }
        )

        # Set password
        user.set_password(password)
        user.is_active = True
        user.save()

        status = 'Created' if created else 'Updated'
        self.stdout.write(
            self.style.SUCCESS(
                f'{status} E2E user: {username}\n'
                f'Password: {password}\n'
                f'ID: {user.id}\n'
                f'Active: {user.is_active}\n'
                f'PK: {user.pk}'
            )
        )
