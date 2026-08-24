"""E2E environment - isolated BD: taxicarga_pg_e2e"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env.e2e", override=False)

from .settings import *  # noqa

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('E2E_DB_NAME', 'taxicarga_pg_e2e'),
        'USER': os.environ.get('E2E_DB_USER', 'taxicarga'),
        'PASSWORD': os.environ.get('E2E_DB_PASSWORD', ''),
        'HOST': os.environ.get('E2E_DB_HOST', 'localhost'),
        'PORT': os.environ.get('E2E_DB_PORT', '5432'),
        'TEST': {
            'NAME': os.environ.get('E2E_DB_NAME', 'taxicarga_pg_e2e'),
        },
    }
}

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', 'testserver']
DEBUG = True
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:5177',
    'http://127.0.0.1:5177',
]
SESSION_COOKIE_SECURE = False  # Allow HTTP for E2E
CSRF_COOKIE_SECURE = False     # Allow HTTP for E2E

# YCloud E2E Configuration
YCLOUD_WEBHOOK_SECRET = 'test_secret_e2e'
YCLOUD_ENABLED = True

# Serve Vue build from static_build/
# Note: static_build/static/ contains the actual CSS/JS
# But we also need static_build root for favicon, loader.css, etc.
STATICFILES_DIRS = [
    BASE_DIR / 'static_build' / 'static',  # CSS, JS, images from Vue build
    BASE_DIR / 'static_build',             # Root files: favicon, loader.css, logo.png
]
