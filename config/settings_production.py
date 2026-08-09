import os

from .settings import *  # noqa: F403


DEBUG = False
STRICT_ADMIN_OPERATIONS = True
SECRET_KEY = env_value("DJANGO_SECRET_KEY", required=True)  # noqa: F405
ALLOWED_HOSTS = [v.strip() for v in env_value("ALLOWED_HOSTS", required=True).split(",") if v.strip()]  # noqa: F405
CSRF_TRUSTED_ORIGINS = [v.strip() for v in env_value("CSRF_TRUSTED_ORIGINS", required=True).split(",") if v.strip()]  # noqa: F405
database_password = env_value("DATABASE_PASSWORD", required=True)  # noqa: F405
database_url = env_value("DATABASE_URL", required=True)  # noqa: F405
if not database_url.startswith(("postgres://", "postgresql://")):
    raise RuntimeError("Production requires PostgreSQL DATABASE_URL.")
os.environ["DATABASE_URL"] = database_url.replace("{DATABASE_PASSWORD}", database_password)
DATABASES = {"default": dj_database_url.config(default=os.environ["DATABASE_URL"], conn_max_age=600, conn_health_checks=True)}  # noqa: F405
WHATSAPP_API_VERSION = env_value("WHATSAPP_API_VERSION", required=True)  # noqa: F405
STORAGES = {"staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)  # noqa: F405
SECURE_HSTS_SECONDS = int(env_value("SECURE_HSTS_SECONDS", "0"))  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)  # noqa: F405
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)  # noqa: F405
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"sanitize_pii": {"()": "config.logging_filters.SanitizePIIFilter"}},
    "formatters": {"json": {"format": '{{"timestamp":"{asctime}","level":"{levelname}","service":"{name}","message":"{message}"}}', "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json", "filters": ["sanitize_pii"]}},
    "root": {"handlers": ["console"], "level": env_value("LOG_LEVEL", "INFO")},  # noqa: F405
}
