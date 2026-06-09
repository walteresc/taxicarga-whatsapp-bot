import csv
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.cotizador.models import ServicioHistorico


class Command(BaseCommand):
    help = "Importa servicios historicos desde un archivo CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_path",
            nargs="?",
            default="apps/cotizador/data/servicios_historicos_ejemplo.csv",
            help="Ruta del CSV a importar.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Elimina los historicos existentes antes de importar.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        if not csv_path.exists():
            raise CommandError(f"No existe el archivo: {csv_path}")

        if options["clear"]:
            ServicioHistorico.objects.all().delete()

        created = 0
        updated = 0
        with csv_path.open(newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                defaults = {
                    "piso_origen": _int_or_none(row.get("piso_origen")),
                    "piso_destino": _int_or_none(row.get("piso_destino")),
                    "ascensor_origen": _bool(row.get("ascensor_origen")),
                    "ascensor_destino": _bool(row.get("ascensor_destino")),
                    "lista_objetos": row.get("lista_objetos", ""),
                    "objetos_pesados": row.get("objetos_pesados", ""),
                    "modalidad_servicio": row.get("modalidad_servicio", ""),
                    "requiere_desarmado": _bool_or_none(row.get("requiere_desarmado")),
                    "acceso_origen": row.get("acceso_origen", ""),
                    "acceso_destino": row.get("acceso_destino", ""),
                    "camion_llega_origen": _bool_or_none(row.get("camion_llega_origen")),
                    "camion_llega_destino": _bool_or_none(row.get("camion_llega_destino")),
                    "distancia_carga_origen_m": _int_or_none(row.get("distancia_carga_origen_m")),
                    "distancia_carga_destino_m": _int_or_none(row.get("distancia_carga_destino_m")),
                    "peso_carga_kg": _decimal_or_none(row.get("peso_carga_kg")),
                    "volumen_carga_m3": _decimal_or_none(row.get("volumen_carga_m3")),
                    "camion_usado": row.get("camion_usado", ""),
                    "capacidad_camion": row.get("capacidad_camion", ""),
                    "ayudantes": _int_or_none(row.get("ayudantes")) or 2,
                    "precio_cotizado": Decimal(row["precio_cotizado"]),
                    "precio_final": _decimal_or_none(row.get("precio_final")),
                    "cerrado": _bool(row.get("cerrado")),
                    "observaciones": row.get("observaciones", ""),
                }
                _, was_created = ServicioHistorico.objects.update_or_create(
                    fecha=row["fecha"],
                    tipo_servicio=row["tipo_servicio"],
                    distrito_origen=row["distrito_origen"],
                    distrito_destino=row["distrito_destino"],
                    defaults=defaults,
                )
                created += int(was_created)
                updated += int(not was_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Importacion lista. Creados: {created}. Actualizados: {updated}."
            )
        )


def _bool(value):
    return str(value).strip().lower() in {"1", "true", "yes", "si", "on"}


def _bool_or_none(value):
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    return normalized in {"1", "true", "yes", "si", "on"}


def _int_or_none(value):
    return int(value) if str(value or "").strip() else None


def _decimal_or_none(value):
    return Decimal(value) if str(value or "").strip() else None
