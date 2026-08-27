#!/bin/bash
# Setup E2E test user with known password

docker exec taxicarga-api python manage.py shell -c '
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_e2e")
import django
django.setup()

from django.contrib.auth.models import User

# Create/update test user
user, created = User.objects.get_or_create(username="e2e_test")
user.set_password("e2e_test_password")
user.is_staff = True
user.is_superuser = True
user.save()

if created:
    print("CREATED:e2e_test")
else:
    print("UPDATED:e2e_test")

print(f"PASSWORD_SET")
'
