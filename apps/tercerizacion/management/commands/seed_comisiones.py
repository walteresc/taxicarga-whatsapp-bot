"""Carga una tabla de comisiones de tercerización de arranque. Idempotente
(no toca nada si ya hay tramos cargados). El negocio la ajusta después desde
el panel Configuración → Comisiones o el admin.

    python manage.py seed_comisiones [--force]

La comisión baja a medida que sube el monto del servicio, y las mudanzas
pagan un poco más (servicio más intensivo en gente y coordinación).
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.tercerizacion.models import TramoComision

# (categoria, desde, hasta|None, porcentaje)
TRAMOS = [
    # -- Tabla general (cualquier categoría sin tabla propia) --
    ("", 0, 500, 25),
    ("", 500, 1500, 20),
    ("", 1500, 4000, 16),
    ("", 4000, 10000, 12),
    ("", 10000, None, 9),
    # -- Mudanzas (muebles / electrodomésticos: más operarios y coordinación) --
    ("mudanza", 0, 1500, 30),
    ("mudanza", 1500, 5000, 24),
    ("mudanza", 5000, None, 18),
]


class Command(BaseCommand):
    help = "Carga inicial de la tabla de comisiones de tercerización."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Borra los tramos existentes y vuelve a cargar la tabla base.",
        )

    def handle(self, *a, **o):
        if TramoComision.objects.exists() and not o["force"]:
            self.stdout.write(self.style.WARNING(
                f"Ya hay {TramoComision.objects.count()} tramos. Nada que hacer "
                f"(usá --force para reemplazarlos)."))
            return
        if o["force"]:
            TramoComision.objects.all().delete()
        TramoComision.objects.bulk_create([
            TramoComision(
                categoria=cat, monto_desde=Decimal(d),
                monto_hasta=None if h is None else Decimal(h),
                porcentaje=Decimal(p), activo=True,
            )
            for cat, d, h, p in TRAMOS
        ])
        self.stdout.write(self.style.SUCCESS(
            f"Tabla de comisiones cargada: {len(TRAMOS)} tramos."))
