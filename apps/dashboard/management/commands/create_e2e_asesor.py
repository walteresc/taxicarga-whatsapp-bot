"""Create E2E test user with Asesor de Ventas role (no superuser)."""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

User = get_user_model()


class Command(BaseCommand):
    help = "Create E2E user with Asesor de Ventas role"

    def handle(self, *args, **options):
        username = 'e2e_asesor'
        password = 'e2e_asesor_pass_123'

        # Create or get user
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': 'e2e_asesor@test.local',
                'is_active': True,
                'is_staff': False,
                'is_superuser': False,
            }
        )

        # Set password
        user.set_password(password)
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.save()

        # Add to Asesor de Ventas group
        try:
            group = Group.objects.get(name='Asesor de Ventas')
            user.groups.add(group)
            group_status = 'Added to Asesor de Ventas group'
        except Group.DoesNotExist:
            group_status = 'ERROR: Asesor de Ventas group does not exist'

        status = 'Created' if created else 'Updated'
        self.stdout.write(
            self.style.SUCCESS(
                f'{status} E2E user: {username}\n'
                f'Password: {password}\n'
                f'is_superuser: False\n'
                f'is_staff: False\n'
                f'{group_status}'
            )
        )
