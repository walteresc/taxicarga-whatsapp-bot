"""Carga una tabla de tarifas de arranque para carga nacional PARCIAL/consolidada
(peso × destino → precio + días estimados). Idempotente (no toca nada si ya hay
tarifas cargadas). El negocio la ajusta después desde el panel Configuración →
Publicaciones → Tarifas de carga parcial, o el admin.

    python manage.py seed_tarifas_parciales [--force]

Precio por kg más bajo cuanto más pesada la carga (economías de escala del
camión consolidado); el mínimo evita que un paquete de 2 kg salga gratis.
Los destinos son ciudades/regiones típicas de ruta nacional desde Lima; el
tramo general ("") cubre cualquier otro destino que no tenga tabla propia.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.tercerizacion.models import TarifaCargaParcial

# (destino, peso_desde_kg, peso_hasta_kg|None, precio_por_kg, monto_minimo, dias_estimados)
TARIFAS = [
    # -- Tramo general (cualquier destino sin tabla propia) --
    ("", 0, 50, Decimal("6.00"), Decimal("40"), 6),
    ("", 50, 200, Decimal("4.50"), Decimal("40"), 6),
    ("", 200, None, Decimal("3.50"), Decimal("40"), 7),
    # -- Rutas de alto tráfico desde Lima (más frecuencia, más económico) --
    ("arequipa", 0, 50, Decimal("5.00"), Decimal("35"), 4),
    ("arequipa", 50, 200, Decimal("3.80"), Decimal("35"), 4),
    ("arequipa", 200, None, Decimal("3.00"), Decimal("35"), 5),
    ("trujillo", 0, 50, Decimal("4.80"), Decimal("35"), 3),
    ("trujillo", 50, 200, Decimal("3.60"), Decimal("35"), 3),
    ("trujillo", 200, None, Decimal("2.80"), Decimal("35"), 4),
    ("chiclayo", 0, 50, Decimal("5.20"), Decimal("35"), 4),
    ("chiclayo", 50, 200, Decimal("4.00"), Decimal("35"), 4),
    ("chiclayo", 200, None, Decimal("3.10"), Decimal("35"), 5),
    ("cusco", 0, 50, Decimal("5.50"), Decimal("40"), 5),
    ("cusco", 50, 200, Decimal("4.20"), Decimal("40"), 5),
    ("cusco", 200, None, Decimal("3.30"), Decimal("40"), 6),
    ("piura", 0, 50, Decimal("5.20"), Decimal("35"), 4),
    ("piura", 50, 200, Decimal("4.00"), Decimal("35"), 4),
    ("piura", 200, None, Decimal("3.10"), Decimal("35"), 5),
]


class Command(BaseCommand):
    help = "Carga inicial de la tabla de tarifas de carga nacional parcial/consolidada."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Borra las tarifas existentes y vuelve a cargar la tabla base.",
        )

    def handle(self, *a, **o):
        if TarifaCargaParcial.objects.exists() and not o["force"]:
            self.stdout.write(self.style.WARNING(
                f"Ya hay {TarifaCargaParcial.objects.count()} tarifas. Nada que hacer "
                f"(usá --force para reemplazarlas)."))
            return
        if o["force"]:
            TarifaCargaParcial.objects.all().delete()
        TarifaCargaParcial.objects.bulk_create([
            TarifaCargaParcial(
                destino=destino, peso_desde_kg=Decimal(desde),
                peso_hasta_kg=None if hasta is None else Decimal(hasta),
                precio_por_kg=precio, monto_minimo=minimo,
                dias_estimados=dias, activo=True,
            )
            for destino, desde, hasta, precio, minimo, dias in TARIFAS
        ])
        self.stdout.write(self.style.SUCCESS(
            f"Tabla de tarifas de carga parcial cargada: {len(TARIFAS)} tramos."))
