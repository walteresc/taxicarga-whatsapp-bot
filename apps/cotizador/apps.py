from django.apps import AppConfig


class CotizadorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cotizador"

    def ready(self):
        import apps.cotizador.signals  # noqa: F401
