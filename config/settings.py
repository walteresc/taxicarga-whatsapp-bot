from pathlib import Path

import dj_database_url
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    value = config(name, default=str(default))
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def env_value(name, default="", required=False):
    file_name = config(f"{name}_FILE", default="").strip()
    value = Path(file_name).read_text(encoding="utf-8").strip() if file_name else config(name, default=default)
    if required and not str(value).strip():
        raise RuntimeError(f"{name} or {name}_FILE is required.")
    return value


SECRET_KEY = env_value("DJANGO_SECRET_KEY", default=config("SECRET_KEY", default="django-insecure-dev-only-change-me"))
DEBUG = env_bool("DJANGO_DEBUG", default=True)
STRICT_ADMIN_OPERATIONS = env_bool("STRICT_ADMIN_OPERATIONS", default=False)
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
    "apps.whatsapp_bot_v4",
]

LOGIN_URL = "/dashboard/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/dashboard/login/"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
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
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "datos_privados" / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
}

OPENAI_API_KEY = env_value("OPENAI_API_KEY")
OPENAI_MODEL = config("OPENAI_MODEL", default="gpt-4.1-mini")
AI_PROVIDER = config("AI_PROVIDER", default="openai").strip().lower()
AI_EXTRACTION_PROVIDER = config("AI_EXTRACTION_PROVIDER", default="").strip().lower() or AI_PROVIDER
AI_CONVERSATION_PROVIDER = config("AI_CONVERSATION_PROVIDER", default="").strip().lower() or AI_PROVIDER
AI_DELTA_EXTRACTION_ENABLED = env_bool("AI_DELTA_EXTRACTION_ENABLED", default=False)
AI_DELTA_SHADOW_MODE = env_bool("AI_DELTA_SHADOW_MODE", default=True)
OPENAI_EXTRACTION_MODEL = config("OPENAI_EXTRACTION_MODEL", default="").strip() or OPENAI_MODEL
OPENAI_CONVERSATION_MODEL = config("OPENAI_CONVERSATION_MODEL", default="").strip() or OPENAI_MODEL
DEEPSEEK_API_KEY = env_value("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = config("DEEPSEEK_MODEL", default="deepseek-v4-flash")
DEEPSEEK_EXTRACTION_MODEL = config("DEEPSEEK_EXTRACTION_MODEL", default="").strip() or DEEPSEEK_MODEL
DEEPSEEK_CONVERSATION_MODEL = config("DEEPSEEK_CONVERSATION_MODEL", default="").strip() or DEEPSEEK_MODEL
DEEPSEEK_BASE_URL = config("DEEPSEEK_BASE_URL", default="https://api.deepseek.com").rstrip("/")
AI_REQUEST_TIMEOUT_SECONDS = config("AI_REQUEST_TIMEOUT_SECONDS", default=30, cast=float)
OPENAI_INPUT_USD_PER_MILLION = config("OPENAI_INPUT_USD_PER_MILLION", default=0, cast=float)
OPENAI_OUTPUT_USD_PER_MILLION = config("OPENAI_OUTPUT_USD_PER_MILLION", default=0, cast=float)
DEEPSEEK_INPUT_USD_PER_MILLION = config("DEEPSEEK_INPUT_USD_PER_MILLION", default=0, cast=float)
DEEPSEEK_OUTPUT_USD_PER_MILLION = config("DEEPSEEK_OUTPUT_USD_PER_MILLION", default=0, cast=float)
WHATSAPP_VERIFY_TOKEN = env_value("META_VERIFY_TOKEN", default=config("WHATSAPP_VERIFY_TOKEN", default=""))
WHATSAPP_ACCESS_TOKEN = env_value("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = config("WHATSAPP_PHONE_NUMBER_ID", default="")
WHATSAPP_API_VERSION = config("WHATSAPP_API_VERSION", default="v20.0")
WHATSAPP_BOT_COLLECTING_TIMEOUT_HOURS = int(config("WHATSAPP_BOT_COLLECTING_TIMEOUT_HOURS", default="6"))

CHATWOOT_INTEGRATION_ENABLED = env_bool("CHATWOOT_INTEGRATION_ENABLED", default=False)
CHATWOOT_SHADOW_SYNC_ENABLED = env_bool("CHATWOOT_SHADOW_SYNC_ENABLED", default=False)
CHATWOOT_AGENT_OUTBOUND_ENABLED = env_bool("CHATWOOT_AGENT_OUTBOUND_ENABLED", default=False)
META_OUTBOX_ENABLED = env_bool("META_OUTBOX_ENABLED", default=False)
BOT_GENERATION_LEASE_ENABLED = env_bool("BOT_GENERATION_LEASE_ENABLED", default=False)
CHATWOOT_RETURN_TO_BOT_ENABLED = env_bool("CHATWOOT_RETURN_TO_BOT_ENABLED", default=False)

CHATWOOT_ENABLED = env_bool("CHATWOOT_ENABLED", default=False)
CHATWOOT_SYNC_ENABLED = env_bool("CHATWOOT_SYNC_ENABLED", default=False)
CHATWOOT_BASE_URL = config("CHATWOOT_BASE_URL", default="").rstrip("/")
CHATWOOT_API_ACCESS_TOKEN = env_value("CHATWOOT_API_ACCESS_TOKEN")
CHATWOOT_ACCOUNT_ID = config("CHATWOOT_ACCOUNT_ID", default="")
CHATWOOT_INBOX_ID = config("CHATWOOT_INBOX_ID", default="")
CHATWOOT_CONNECT_TIMEOUT = float(config("CHATWOOT_CONNECT_TIMEOUT", default="3"))
CHATWOOT_READ_TIMEOUT = float(config("CHATWOOT_READ_TIMEOUT", default="10"))
CHATWOOT_WEBHOOK_ENABLED = env_bool("CHATWOOT_WEBHOOK_ENABLED", default=False)
CHATWOOT_WEBHOOK_SECRET = env_value("CHATWOOT_WEBHOOK_SECRET")
CHATWOOT_WEBHOOK_MAX_AGE_SECONDS = int(config("CHATWOOT_WEBHOOK_MAX_AGE_SECONDS", default="300"))
CHATWOOT_HUMAN_TAKEOVER_ENABLED = env_bool("CHATWOOT_HUMAN_TAKEOVER_ENABLED", default=False)
CHATWOOT_AGENT_TO_WHATSAPP_ENABLED = env_bool("CHATWOOT_AGENT_TO_WHATSAPP_ENABLED", default=False)
CHATWOOT_LIVE_SYNC_ENABLED = env_bool("CHATWOOT_LIVE_SYNC_ENABLED", default=False)
CHATWOOT_COMMERCIAL_LABELS_ENABLED = env_bool("CHATWOOT_COMMERCIAL_LABELS_ENABLED", default=False)
BOT_CONTEXT_MAX_MESSAGES = int(config("BOT_CONTEXT_MAX_MESSAGES", default="40"))
BOT_CONTEXT_MAX_CHARACTERS = int(config("BOT_CONTEXT_MAX_CHARACTERS", default="12000"))
PAYMENT_INFORMATION = config("PAYMENT_INFORMATION", default="").strip()
PAYMENT_ACCOUNT_HOLDER_INFORMATION = config(
    "PAYMENT_ACCOUNT_HOLDER_INFORMATION", default=""
).strip()

DJANGO_LOG_LEVEL = config("DJANGO_LOG_LEVEL", default="DEBUG")

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
            "level": DJANGO_LOG_LEVEL,
            "propagate": True,
        },
        "apps.whatsapp": {
            "handlers": ["console", "file"],
            "level": DJANGO_LOG_LEVEL,
            "propagate": True,
        },
    },
}

CHANNEL_SCHEDULE_BYPASS_FOR_TESTING = [
    int(ch.strip())
    for ch in config("CHANNEL_SCHEDULE_BYPASS_FOR_TESTING", default="7").split(",")
    if ch.strip()
]
