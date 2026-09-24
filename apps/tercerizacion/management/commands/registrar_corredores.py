"""Registra los 40 corredores comerciales (`apps/tercerizacion/fixtures/corredores_40.json`)
como `Corredor`/`CorredorParada`, enlazando cada localidad de la secuencia a
su `Localidad` ya geocodificada (correr `geocodificar_localidades` antes).

No pide nada por red — solo lee el fixture y la tabla `Localidad` ya
poblada. Idempotente: `get_or_create` por `codigo`, nunca toca un corredor
con `modificado_manualmente=True`. El origen y destino de cada corredor
quedan como `Corredor.localidad_origen/destino` (no se duplican como
`CorredorParada`, tal como se pidió).

Un corredor cuya secuencia tenga alguna localidad sin geocodificar (o
`AMBIGUO`) igual se registra — queda en `estado_validacion=PENDIENTE_TRAZADO`
(no bloquea el registro comercial, solo la geometría real, que se resuelve
después con `calcular_tramos_corredores`).

    python manage.py registrar_corredores [--force]
"""
import csv
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.tercerizacion.models import Corredor, CorredorParada, Localidad

FIXTURE_PATH = Path(__file__).resolve().parent.parent.parent / "fixtures" / "corredores_40.json"
LOCALIDADES_CSV = Path(__file__).resolve().parent.parent.parent / "data" / "localidades.csv"


class Command(BaseCommand):
    help = "Registra los 40 corredores comerciales (sin red) desde el fixture."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Reescribe corredores existentes sin modificaciones manuales.")

    def handle(self, *args, **opts):
        force = opts["force"]
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self._buscado_a_geonames_id = self._cargar_mapa_buscado(LOCALIDADES_CSV)

        creados, actualizados, saltados = 0, 0, 0
        localidades_faltantes = set()

        for item in data:
            corredor, created = Corredor.objects.get_or_create(
                codigo=item["codigo"], defaults={"nombre": item["nombre"], "variante": item.get("variante", "")},
            )
            if not created and corredor.modificado_manualmente and not force:
                saltados += 1
                continue

            secuencia = item["secuencia"]
            origen_loc = self._buscar_localidad(secuencia[0])
            destino_loc = self._buscar_localidad(secuencia[-1])
            for nombre in (secuencia[0], secuencia[-1]):
                if self._buscar_localidad(nombre) is None:
                    localidades_faltantes.add(nombre)

            corredor.nombre = item["nombre"]
            corredor.variante = item.get("variante", "")
            corredor.origen_nombre = secuencia[0]
            corredor.destino_nombre = secuencia[-1]
            if origen_loc:
                corredor.localidad_origen = origen_loc
                corredor.origen_lat, corredor.origen_lng = origen_loc.lat, origen_loc.lng
            if destino_loc:
                corredor.localidad_destino = destino_loc
                corredor.destino_lat, corredor.destino_lng = destino_loc.lat, destino_loc.lng
            corredor.save()

            with transaction.atomic():
                intermedias = secuencia[1:-1]
                existentes = {p.nombre: p for p in corredor.paradas.all()}
                for i, nombre in enumerate(intermedias):
                    loc = self._buscar_localidad(nombre)
                    if loc is None:
                        localidades_faltantes.add(nombre)
                    parada = existentes.get(nombre)
                    if parada and parada.modificado_manualmente and not force:
                        continue
                    if loc and loc.lat is not None and loc.lng is not None:
                        CorredorParada.objects.update_or_create(
                            corredor=corredor, nombre=nombre,
                            defaults={
                                "orden": i, "lat": loc.lat, "lng": loc.lng,
                                "radio_km": loc.radio_efectivo_km(), "localidad": loc,
                                "tipo_parada": loc.tipo, "activo": True,
                            },
                        )
                    # Sin coordenadas todavía (AMBIGUO/PENDIENTE): no se crea la
                    # parada — se completa cuando `geocodificar_localidades`
                    # (o una carga manual) resuelva esa localidad.

            if created:
                creados += 1
            else:
                actualizados += 1

        if localidades_faltantes:
            self.stdout.write(self.style.WARNING(
                f"{len(localidades_faltantes)} localidades sin geocodificar todavía (correr geocodificar_localidades): "
                + ", ".join(sorted(localidades_faltantes)),
            ))
        self.stdout.write(self.style.SUCCESS(
            f"Corredores: {len(data)} en el catálogo · creados: {creados} · actualizados: {actualizados} · saltados (modificados a mano): {saltados}",
        ))

    def _cargar_mapa_buscado(self, path):
        """{nombre_buscado (tal como aparece en el fixture): geonames_id} —
        del CSV que ya exportó `geocodificar_localidades`. Necesario porque el
        nombre RESUELTO puede diferir del buscado (p. ej. "Espinar" -> "Yauri",
        "Chala" -> "Chala Viejo") y `Localidad.nombre_normalizado` se deriva
        del nombre resuelto, no del buscado."""
        mapa = {}
        if not path.exists():
            return mapa
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("geonames_id"):
                    mapa[row["nombre_buscado"]] = row["geonames_id"]
        return mapa

    def _buscar_localidad(self, nombre):
        geonames_id = self._buscado_a_geonames_id.get(nombre)
        if geonames_id:
            loc = Localidad.objects.filter(geonames_id=geonames_id).first()
            if loc:
                return loc
        from apps.tercerizacion.corredores import normalizar_nombre
        return Localidad.objects.filter(
            nombre_normalizado=normalizar_nombre(nombre), lat__isnull=False, lng__isnull=False,
        ).first()
