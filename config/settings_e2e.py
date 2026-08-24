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
    }
}

ALLOWED_HOSTS = ['localhost', '127.0.0.1']
DEBUG = True
