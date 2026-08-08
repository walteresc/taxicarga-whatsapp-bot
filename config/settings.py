from pathlib import Path

import dj_database_url
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    value = config(name, default=str(default))
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = config("SECRET_KEY", default="django-insecure-dev-only-change-me")
DEBUG = env_bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1,testserver").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.clientes",
    "apps.leads",
    "apps.cotizador",
    "apps.whatsapp",
    "apps.ia",
    "apps.dashboard",
    "apps.servicios",
    "apps.campo",
    "apps.flota",
    "apps.integrations",
]

LOGIN_URL = "/dashboard/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/dashboard/login/"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
"context_processors": [
                 "django.template.context_processors.request",
                 "django.contrib.auth.context_processors.auth",
                 "django.contrib.messages.context_processors.messages",
                 "apps.dashboard.context_processors.user_roles",
             ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-pe"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_ROOT = BASE_DIR / "datos_privados" / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
}

OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
OPENAI_MODEL = config("OPENAI_MODEL", default="gpt-4.1-mini")
WHATSAPP_VERIFY_TOKEN = config("WHATSAPP_VERIFY_TOKEN", default="")
WHATSAPP_ACCESS_TOKEN = config("WHATSAPP_ACCESS_TOKEN", default="")
WHATSAPP_PHONE_NUMBER_ID = config("WHATSAPP_PHONE_NUMBER_ID", default="")
WHATSAPP_API_VERSION = config("WHATSAPP_API_VERSION", default="v20.0")

CHATWOOT_INTEGRATION_ENABLED = env_bool("CHATWOOT_INTEGRATION_ENABLED", default=False)
CHATWOOT_SHADOW_SYNC_ENABLED = env_bool("CHATWOOT_SHADOW_SYNC_ENABLED", default=False)
CHATWOOT_AGENT_OUTBOUND_ENABLED = env_bool("CHATWOOT_AGENT_OUTBOUND_ENABLED", default=False)
META_OUTBOX_ENABLED = env_bool("META_OUTBOX_ENABLED", default=False)
BOT_GENERATION_LEASE_ENABLED = env_bool("BOT_GENERATION_LEASE_ENABLED", default=False)
CHATWOOT_RETURN_TO_BOT_ENABLED = env_bool("CHATWOOT_RETURN_TO_BOT_ENABLED", default=False)

CHATWOOT_ENABLED = env_bool("CHATWOOT_ENABLED", default=False)
CHATWOOT_BASE_URL = config("CHATWOOT_BASE_URL", default="").rstrip("/")
CHATWOOT_API_ACCESS_TOKEN = config("CHATWOOT_API_ACCESS_TOKEN", default="")
CHATWOOT_ACCOUNT_ID = config("CHATWOOT_ACCOUNT_ID", default="")
CHATWOOT_INBOX_ID = config("CHATWOOT_INBOX_ID", default="")
CHATWOOT_CONNECT_TIMEOUT = float(config("CHATWOOT_CONNECT_TIMEOUT", default="3"))
CHATWOOT_READ_TIMEOUT = float(config("CHATWOOT_READ_TIMEOUT", default="10"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{levelname}] {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": "django_debug.log",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": True,
        },
        "apps.whatsapp": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": True,
        },
    },
}
