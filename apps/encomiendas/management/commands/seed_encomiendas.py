"""Zonas de reparto de Lima + tabla de tarifas de arranque. Idempotente.

    python manage.py seed_encomiendas [--force]

Precios de ejemplo — el negocio los ajusta en Configuración → Tarifas de zona
o en el admin.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.encomiendas.models import Envio, TarifaZona, ZonaReparto

ZONAS = {
    "Lima Centro": ["lima", "cercado de lima", "breña", "la victoria", "rimac", "san luis"],
    "Lima Moderna": ["miraflores", "san isidro", "surco", "santiago de surco", "barranco",
                     "san borja", "la molina", "jesus maria", "lince", "magdalena",
                     "magdalena del mar", "pueblo libre", "san miguel"],
    "Lima Norte": ["los olivos", "san martin de porres", "independencia", "comas",
                   "carabayllo", "puente piedra", "ancon", "santa rosa"],
    "Lima Sur": ["chorrillos", "san juan de miraflores", "villa maria del triunfo",
                 "villa el salvador", "lurin", "pachacamac"],
    "Lima Este": ["ate", "santa anita", "el agustino", "san juan de lurigancho",
                  "la molina este", "chaclacayo", "lurigancho", "chosica", "cieneguilla"],
    "Callao": ["callao", "bellavista", "la perla", "la punta", "carmen de la legua",
               "ventanilla", "mi peru"],
    "Balnearios": ["punta hermosa", "punta negra", "san bartolo", "santa maria del mar", "pucusana"],
}

# (origen, destino, express_base, standard_base) — misma zona = local; distinta = interzonal.
_LOCAL = (12, 9)
_VECINA = (16, 11)
_LEJANA = (22, 15)


class Command(BaseCommand):
    help = "Carga zonas de reparto de Lima y tarifas de encomiendas."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Reemplaza zonas y tarifas.")

    def handle(self, *a, **o):
        if ZonaReparto.objects.exists() and not o["force"]:
            self.stdout.write(self.style.WARNING("Ya hay zonas cargadas (--force para reemplazar)."))
            return
        if o["force"]:
            if Envio.objects.exists():
                self.stdout.write(self.style.ERROR("Hay envíos: no se puede --force."))
                return
            TarifaZona.objects.all().delete()
            ZonaReparto.objects.all().delete()

        zonas = {}
        for i, (nombre, distritos) in enumerate(ZONAS.items()):
            zonas[nombre] = ZonaReparto.objects.create(nombre=nombre, distritos=distritos, orden=i)

        vecinas = {
            "Lima Centro": {"Lima Moderna", "Lima Este", "Lima Sur", "Lima Norte"},
            "Lima Moderna": {"Lima Centro", "Lima Sur", "Lima Este"},
            "Lima Norte": {"Lima Centro", "Callao"},
            "Lima Sur": {"Lima Centro", "Lima Moderna", "Balnearios"},
            "Lima Este": {"Lima Centro", "Lima Moderna"},
            "Callao": {"Lima Centro", "Lima Norte", "Lima Moderna"},
            "Balnearios": {"Lima Sur"},
        }
        n = 0
        for o_name, o_zona in zonas.items():
            for d_name, d_zona in zonas.items():
                if o_name == d_name:
                    exp, std = _LOCAL
                elif d_name in vecinas.get(o_name, set()):
                    exp, std = _VECINA
                else:
                    exp, std = _LEJANA
                for nivel, base, eta in ((TarifaZona.NIVEL_EXPRESS, exp, 6), (TarifaZona.NIVEL_STANDARD, std, 24)):
                    TarifaZona.objects.create(
                        origen=o_zona, destino=d_zona, nivel=nivel,
                        precio_base=Decimal(base), incluye_kg=Decimal(5),
                        precio_kg_extra=Decimal("1.50"), eta_horas=eta,
                    )
                    n += 1
        self.stdout.write(self.style.SUCCESS(f"{len(zonas)} zonas y {n} tarifas cargadas."))
