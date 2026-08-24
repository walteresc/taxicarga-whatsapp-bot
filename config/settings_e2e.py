"""E2E/Docker environment - Docker Compose setup with PostgreSQL"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)
load_dotenv(BASE_DIR / ".env.e2e", override=False)

from .settings import *  # noqa

# Database: Use DATABASE_URL env var if provided (Docker), otherwise use components
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    import dj_database_url
    DATABASES = {'default': dj_database_url.config(default=DATABASE_URL, conn_max_age=600)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', os.environ.get('E2E_DB_NAME', 'taxicarga_pg_test')),
            'USER': os.environ.get('DB_USER', os.environ.get('E2E_DB_USER', 'taxicarga')),
            'PASSWORD': os.environ.get('DB_PASSWORD', os.environ.get('E2E_DB_PASSWORD', '')),
            'HOST': os.environ.get('DB_HOST', os.environ.get('E2E_DB_HOST', 'localhost')),
            'PORT': os.environ.get('DB_PORT', os.environ.get('E2E_DB_PORT', '5432')),
            'TEST': {
                'NAME': os.environ.get('DB_NAME', os.environ.get('E2E_DB_NAME', 'taxicarga_pg_test')),
            },
        }
    }

# Redis URL
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

# Allowed hosts from environment
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Debug mode controlled by environment (False in Docker prod)
DEBUG = os.environ.get('DEBUG', 'False').lower() in ['true', '1', 'yes']

# CSRF and security
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8001',
    'http://127.0.0.1:8001',
    'http://localhost:5177',
    'http://127.0.0.1:5177',
    'http://nginx:8001',
]

# Session and CSRF cookies
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ['true', '1', 'yes']
CSRF_COOKIE_SECURE = os.environ.get('CSRF_COOKIE_SECURE', 'False').lower() in ['true', '1', 'yes']

# YCloud Configuration
YCLOUD_WEBHOOK_SECRET = os.environ.get('YCLOUD_WEBHOOK_SECRET', 'test_secret_e2e')
YCLOUD_ENABLED = True

# Static files configuration
# Nginx serves staticfiles directory
STATICFILES_DIRS = [
    BASE_DIR / 'static_build' / 'static',
    BASE_DIR / 'static_build',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'
