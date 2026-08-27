"""
Test-only settings: Uses postgres superuser for test database creation.
Imported via: python manage.py test --settings=config.settings_test
"""
from .settings import *

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "test_taxicarga_pg_test",
        "USER": "postgres",
        "PASSWORD": "postgres",
        "HOST": "localhost",
        "PORT": "5432",
        "CONN_MAX_AGE": 0,
        "ATOMIC_REQUESTS": True,
    }
}

# Disable migrations for faster test runs (optional)
# class DisableMigrations:
#     def __contains__(self, item):
#         return True
#     def __getitem__(self, item):
#         return None
#
# MIGRATION_MODULES = DisableMigrations()
