from django.apps import AppConfig


class AgenteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.agente"
    verbose_name = "Agente — capacidades"

    def ready(self):
        # Importa los módulos de capacidades para que el decorador @capacidad
        # las registre en el catálogo global.
        from . import capacidades  # noqa: F401
