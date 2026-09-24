"""Calcula la geometría real de los tramos (nodo a nodo) de los corredores
registrados, vía Mapbox Directions v5 — mismo proveedor que ya usa el
frontend (`configuracion/corredores/index.vue`, `QuoteSummaryPanel.vue`),
ahora también server-side (`settings.MAPBOX_TOKEN`, mismo token público).

Por cada par CONSECUTIVO de localidades en la secuencia de un corredor
(incluyendo origen/destino, no solo las paradas intermedias): si el
`TramoVial` para ese par de nodos (en cualquier sentido) ya existe y tiene
`estado_validacion=TRAZADO_CALCULADO`, se REUTILIZA (así es como dos
corredores que comparten el mismo tramo terminan apuntando a la misma fila,
sin pedirle a Mapbox lo mismo dos veces). Si no existe, se pide la ruta real
a Mapbox y se crea. Nunca se edita la geometría de un tramo ya usado por más
de un corredor (`corredores.count() > 1`) — evita romper otro corredor sin
aviso; si hace falta corregirlo, desactivarlo (`activo=False`) y correr de
nuevo (crea uno nuevo).

Al final de cada corredor, llama a `recalcular_trazado` para poblar
`Corredor.trazado`/`distancia_total_km`/`estado_validacion` — nunca
promueve a VALIDADO (eso es una revisión humana desde el CRUD).

    python manage.py calcular_tramos_corredores [--codigo N05] [--grupo "Costa Norte"]
"""
import json
from decimal import Decimal
from pathlib import Path

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.tercerizacion.corredores import recalcular_trazado
from apps.tercerizacion.models import Corredor, CorredorTramo, TramoVial

FIXTURE_PATH = Path(__file__).resolve().parent.parent.parent / "fixtures" / "corredores_40.json"
DIRECTIONS_URL = "https://api.mapbox.com/directions/v5/mapbox/driving/{coords}"


class Command(BaseCommand):
    help = "Calcula la geometría real (Mapbox Directions) de los tramos de los corredores registrados."

    def add_arguments(self, parser):
        parser.add_argument("--codigo", help="Solo este corredor (por código, p. ej. N05).")
        parser.add_argument("--grupo", help="Solo los corredores de este grupo (p. ej. 'Costa Norte').")

    def handle(self, *args, **opts):
        if not settings.MAPBOX_TOKEN:
            raise CommandError("Falta MAPBOX_TOKEN en el entorno del backend.")

        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        if opts.get("codigo"):
            data = [d for d in data if d["codigo"] == opts["codigo"]]
        if opts.get("grupo"):
            data = [d for d in data if d["grupo"] == opts["grupo"]]
        if not data:
            raise CommandError("Ningún corredor coincide con el filtro.")

        n_tramos_nuevos, n_tramos_reusados, n_tramos_error = 0, 0, 0
        n_corredores_ok, n_corredores_incompletos = 0, 0

        for item in data:
            try:
                corredor = Corredor.objects.get(codigo=item["codigo"])
            except Corredor.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"{item['codigo']}: no está registrado (correr registrar_corredores primero)."))
                continue

            # Se leen las FK ya resueltas por `registrar_corredores`
            # (`localidad_origen`/`destino`, `CorredorParada.localidad`) en
            # vez de re-derivar por nombre acá — esa es la fuente de verdad
            # única; volver a buscar por nombre repetiría el mismo problema
            # que ya se resolvió ahí (el nombre RESUELTO puede diferir del
            # buscado, p. ej. "Espinar" -> "Yauri").
            paradas = list(corredor.paradas.order_by("orden"))
            localidades = [corredor.localidad_origen] + [p.localidad for p in paradas] + [corredor.localidad_destino]
            if any(loc is None for loc in localidades):
                faltantes = [n for n, loc in zip(item["secuencia"], localidades) if loc is None]
                self.stdout.write(self.style.WARNING(
                    f"{item['codigo']} {item['nombre']}: sin geocodificar {faltantes} — tramos parciales, corredor queda PENDIENTE_TRAZADO.",
                ))
                n_corredores_incompletos += 1

            CorredorTramo.objects.filter(corredor=corredor).delete()
            orden = 0
            algun_error = False
            for a, b in zip(localidades, localidades[1:]):
                if a is None or b is None:
                    algun_error = True
                    continue
                tramo, sentido, nuevo = self._obtener_o_crear_tramo(a, b)
                if tramo.estado_validacion == TramoVial.ESTADO_ERROR:
                    n_tramos_error += 1
                    algun_error = True
                elif nuevo:
                    n_tramos_nuevos += 1
                else:
                    n_tramos_reusados += 1
                CorredorTramo.objects.create(corredor=corredor, tramo=tramo, orden=orden, sentido=sentido)
                orden += 1

            recalcular_trazado(corredor)
            if algun_error and corredor.estado_validacion == Corredor.ESTADO_TRAZADO_CALCULADO:
                # `recalcular_trazado` solo mira los tramos que SÍ se crearon
                # — si faltó una localidad en medio, la secuencia queda
                # cortada antes de llegar al destino real (ver docstring del
                # comando), aunque los tramos que sí existen estén bien. Eso
                # NO es un trazado completo: nunca declarar validado por
                # geometría cuando de verdad está incompleto.
                corredor.estado_validacion = Corredor.ESTADO_PENDIENTE_TRAZADO
                corredor.save(update_fields=["estado_validacion", "actualizado_en"])
            if not algun_error and corredor.estado_validacion == Corredor.ESTADO_TRAZADO_CALCULADO:
                n_corredores_ok += 1
            self.stdout.write(f"{item['codigo']} {item['nombre']}: {corredor.estado_validacion}, {orden} tramos, {corredor.distancia_total_km or 0} km")

        self.stdout.write(self.style.SUCCESS(
            f"Corredores con trazado completo: {n_corredores_ok} · incompletos (localidad sin geocodificar): {n_corredores_incompletos} · "
            f"tramos nuevos: {n_tramos_nuevos} · reusados (compartidos): {n_tramos_reusados} · con error: {n_tramos_error}",
        ))

    def _obtener_o_crear_tramo(self, a, b):
        """(tramo, sentido, es_nuevo) para el par consecutivo (a, b) en la
        dirección de avance del corredor. Reusa el TramoVial exacto si existe
        en cualquier sentido (a->b o b->a) — es lo que hace que dos
        corredores compartan la misma fila."""
        existente = TramoVial.objects.filter(nodo_inicio=a, nodo_fin=b, activo=True).first()
        if existente:
            return existente, CorredorTramo.SENTIDO_IDA, False
        existente = TramoVial.objects.filter(nodo_inicio=b, nodo_fin=a, activo=True).first()
        if existente:
            return existente, CorredorTramo.SENTIDO_VUELTA, False

        geom, distancia_km = self._rutear(a, b)
        tramo = TramoVial.objects.create(
            nodo_inicio=a, nodo_fin=b,
            geometria=geom or [], distancia_km=distancia_km,
            estado_validacion=TramoVial.ESTADO_CALCULADO if geom else TramoVial.ESTADO_ERROR,
            fuente_geografica="mapbox",
        )
        return tramo, CorredorTramo.SENTIDO_IDA, True

    def _rutear(self, a, b):
        coords = f"{a.lng},{a.lat};{b.lng},{b.lat}"
        url = DIRECTIONS_URL.format(coords=coords)
        try:
            with httpx.Client(timeout=30) as client:
                r = client.get(url, params={
                    "geometries": "geojson", "overview": "full", "access_token": settings.MAPBOX_TOKEN,
                })
                r.raise_for_status()
                data = r.json()
            ruta = (data.get("routes") or [None])[0]
            if not ruta:
                return None, None
            return ruta["geometry"]["coordinates"], Decimal(str(round(ruta["distance"] / 1000, 2)))
        except Exception as e:  # noqa: BLE001 - cualquier fallo de red/formato -> tramo en error, nunca inventar geometría
            self.stdout.write(self.style.WARNING(f"  Mapbox Directions {a.nombre}->{b.nombre} falló: {e}"))
            return None, None
