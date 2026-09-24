"""Cobertura de Carga Compartida/Consolidada por corredor (ruta troncal).

Antes de esto, "¿se ofrece Compartida?" era un simple match de texto contra
`TarifaCargaParcial.destino` (`apps.tercerizacion.services.existe_tarifa_especifica`).
Este módulo agrega una capa geométrica: dado un destino con coordenadas,
decide si cae en el radio de una ciudad atendida (`CorredorParada`), sobre el
eje de la ruta sin ciudad propia, o se desvía de ella (y hasta qué parada
llega la Compartida en ese caso) — ver `resolver_corredor`.

Sin librerías geo nuevas (no PostGIS/shapely): toda la matemática es plana,
apoyada en `haversine_km` (`apps.leads.geo`) como única primitiva de
distancia real."""
from decimal import Decimal

from apps.leads.geo import haversine_km


def _proyectar_en_segmento(lat, lng, lat1, lng1, lat2, lng2):
    """(distancia_km, t, lat_proy, lng_proy): distancia del punto (lat,lng) al
    segmento A(lat1,lng1)-B(lat2,lng2), la fracción t∈[0,1] donde cae la
    proyección sobre el segmento, y el lat/lng de esa proyección.

    Proyección plana (equirrectangular, centrada en el segmento) SOLO para
    hallar el pie de la perpendicular — a la escala de un corredor (cientos
    de km) el error de no usar geodésicas ahí es despreciable, y evita traer
    una librería geo nueva. La distancia que se devuelve siempre se
    recalcula con `haversine_km` sobre el punto proyectado, para no tener dos
    métricas de distancia distintas en la app."""
    import math

    lat, lng, lat1, lng1, lat2, lng2 = (float(v) for v in (lat, lng, lat1, lng1, lat2, lng2))
    lat_ref = math.radians((lat1 + lat2) / 2)
    km_por_grado_lat = 111.32
    km_por_grado_lng = 111.32 * math.cos(lat_ref)

    ax, ay = 0.0, 0.0
    bx, by = (lng2 - lng1) * km_por_grado_lng, (lat2 - lat1) * km_por_grado_lat
    px, py = (lng - lng1) * km_por_grado_lng, (lat - lat1) * km_por_grado_lat

    bb = bx * bx + by * by
    t = 0.0 if bb == 0 else max(0.0, min(1.0, (px * bx + py * by) / bb))

    proy_x, proy_y = t * bx, t * by
    lat_proy = lat1 + (proy_y / km_por_grado_lat if km_por_grado_lat else 0)
    lng_proy = lng1 + (proy_x / km_por_grado_lng if km_por_grado_lng else 0)

    return haversine_km(lat, lng, lat_proy, lng_proy), t, lat_proy, lng_proy


def distancia_a_trazado_km(lat, lng, trazado):
    """(distancia_min_km, posicion_km): distancia mínima del punto (lat,lng) a
    TODO el `trazado` ([[lng,lat], ...], formato GeoJSON) — recorre cada
    segmento consecutivo, se queda con el de menor distancia, y devuelve
    también la posición acumulada (km recorridos desde el origen del
    corredor, siguiendo el trazado, hasta el punto de proyección).

    (None, None) si `trazado` tiene menos de 2 puntos (corredor sin trazado
    calculado todavía) — el llamador lo trata como "sin datos de eje", no
    como error."""
    if not trazado or len(trazado) < 2:
        return None, None

    acumulado_km = 0.0
    mejor = None  # (distancia_km, posicion_km)

    for i in range(len(trazado) - 1):
        lng1, lat1 = trazado[i]
        lng2, lat2 = trazado[i + 1]
        distancia_km, t, _, _ = _proyectar_en_segmento(lat, lng, lat1, lng1, lat2, lng2)
        longitud_segmento_km = haversine_km(lat1, lng1, lat2, lng2)
        posicion_km = acumulado_km + t * longitud_segmento_km
        if mejor is None or distancia_km < mejor[0]:
            mejor = (distancia_km, posicion_km)
        acumulado_km += longitud_segmento_km

    return mejor


def resolver_corredor(lat, lng):
    """Recorre los `Corredor.objects.filter(activo=True)` (con sus paradas
    activas) y devuelve la mejor cobertura de Compartida para (lat,lng), o
    `None` si ninguno lo cubre (→ solo Exclusivo).

    Devuelve:
        {
            "corredor_nombre": str, "parada_nombre": str,   # destino a pasarle a resolver_tarifa_parcial
            "destino_exacto": bool,   # True = compartida hasta el destino real; False = truncada
            "motivo": None | "eje" | "desvio",
            "distancia_km": float,   # informativo
        }

    Prioridad:
      1) El punto cae dentro del `radio_km` de alguna parada activa (de
         cualquier corredor, no hace falta trazado) → esa parada,
         destino_exacto=True. Empate → gana la de menor distancia.
      2) Si no, por cada corredor CON trazado calculado: distancia al eje
         (`distancia_a_trazado_km`).
           - distancia ≤ tolerancia_eje_km → motivo="eje" (sobre la ruta,
             sin parada propia — p. ej. un punto entre dos ciudades).
           - tolerancia_eje_km < distancia ≤ desvio_maximo_km →
             motivo="desvio" (se desvía de la ruta troncal, p. ej. Lunahuaná).
         En ambos casos la parada a tarifar es la ÚLTIMA parada activa cuya
         posición proyectada sobre el trazado sea ≤ la posición proyectada
         del punto (dirección de avance origen→destino) — no existe tarifa
         lineal por km (ver docstring de TarifaCargaParcial), así que un
         punto sin ciudad propia y un punto desviado del eje terminan en el
         mismo lugar: Compartida hasta la última parada conocida, Exclusiva
         al punto real (eso no cambia, se resuelve aparte). Si ninguna
         parada tiene posición ≤ la del punto (cae antes de la primera
         parada del corredor), este corredor no cubre nada acá.
         Entre corredores que matchean (eje o desvío), gana el de menor
         distancia al eje.
      3) Nada matchea → None."""
    from apps.tercerizacion.models import Corredor

    corredores = list(Corredor.objects.filter(activo=True).prefetch_related("paradas"))

    # Prioridad 1: radio de alguna parada, de cualquier corredor.
    mejor_parada = None  # (distancia_km, corredor, parada)
    for corredor in corredores:
        for parada in corredor.paradas.all():
            if not parada.activo:
                continue
            distancia_km = haversine_km(lat, lng, parada.lat, parada.lng)
            if distancia_km <= float(parada.radio_km):
                if mejor_parada is None or distancia_km < mejor_parada[0]:
                    mejor_parada = (distancia_km, corredor, parada)
    if mejor_parada:
        distancia_km, corredor, parada = mejor_parada
        return {
            "corredor_nombre": corredor.nombre, "parada_nombre": parada.nombre,
            "destino_exacto": True, "motivo": None, "distancia_km": distancia_km,
        }

    # Prioridad 2: eje del corredor (sobre la ruta o desviado de ella).
    mejor_eje = None  # (distancia_km, corredor, parada_nombre, motivo)
    for corredor in corredores:
        distancia_km, posicion_km = distancia_a_trazado_km(lat, lng, corredor.trazado)
        if distancia_km is None or distancia_km > float(corredor.desvio_maximo_km):
            continue

        paradas_activas = [p for p in corredor.paradas.all() if p.activo]
        if not paradas_activas:
            continue

        # Posición de cada parada a lo largo del MISMO trazado — ni el centro
        # de una ciudad cae exactamente sobre la carretera.
        candidatas = []
        for parada in paradas_activas:
            _, pos_parada_km = distancia_a_trazado_km(parada.lat, parada.lng, corredor.trazado)
            if pos_parada_km is not None and pos_parada_km <= posicion_km:
                candidatas.append((pos_parada_km, parada))
        if not candidatas:
            continue  # el punto cae antes de la primera parada del corredor

        _, parada_mas_cercana = max(candidatas, key=lambda c: c[0])
        motivo = "eje" if distancia_km <= float(corredor.tolerancia_eje_km) else "desvio"
        if mejor_eje is None or distancia_km < mejor_eje[0]:
            mejor_eje = (distancia_km, corredor, parada_mas_cercana.nombre, motivo)

    if mejor_eje:
        distancia_km, corredor, parada_nombre, motivo = mejor_eje
        return {
            "corredor_nombre": corredor.nombre, "parada_nombre": parada_nombre,
            "destino_exacto": False, "motivo": motivo, "distancia_km": distancia_km,
        }

    return None


# ---------------------------------------------------------------------------
# Grafo de corredores compartidos (catálogo de 40 corredores, 2026-09).
#
# `resolver_corredor`/`distancia_a_trazado_km` de arriba NO cambian — siguen
# operando solo sobre `Corredor.trazado`/`CorredorParada`, sin saber nada de
# `Localidad`/`TramoVial`/`CorredorTramo`. Lo de acá abajo es una capa nueva,
# de solo consulta, para responder "¿qué corredores comparten este tramo, en
# qué orden y en qué sentido?" (ver Corredor.estado_validacion) sin comparar
# nombres de ciudad ni geometrías crudas: la igualdad es relacional (dos
# corredores que referencian el MISMO CorredorTramo.tramo_id), y el punto de
# divergencia es, literalmente, la primera posición donde sus secuencias
# dejan de compartir esa fila.
# ---------------------------------------------------------------------------

def normalizar_nombre(texto):
    """Mismo criterio que `Localidad.save()` — sin tildes, minúsculas,
    recortado. Función de módulo (no método) para poder usarla también sobre
    texto que todavía no es una `Localidad` (p. ej. el destino que escribió
    un cliente)."""
    import unicodedata

    s = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def resolver_localidad(nombre, departamento=None, lat=None, lng=None, radio_km=15):
    """Resuelve texto libre a una `Localidad` activa:
      1) match exacto de `nombre_normalizado` (+ `departamento` si se dio,
         para desambiguar homónimos entre departamentos).
      2) si no matchea y hay lat/lng, la `Localidad` activa con lat/lng
         cargado más cercana dentro de `radio_km` (reusa `haversine_km`).
      3) `None` si nada matchea — el llamador decide (nunca bloquea)."""
    from apps.tercerizacion.models import Localidad

    nombre_norm = normalizar_nombre(nombre)
    if not nombre_norm:
        return None
    qs = Localidad.objects.filter(activo=True, nombre_normalizado=nombre_norm)
    if departamento:
        con_depto = qs.filter(departamento__iexact=departamento.strip())
        if con_depto.exists():
            qs = con_depto
    localidad = qs.first()
    if localidad:
        return localidad

    if lat is not None and lng is not None:
        mejor = None
        for cand in Localidad.objects.filter(activo=True, lat__isnull=False, lng__isnull=False):
            d = haversine_km(lat, lng, cand.lat, cand.lng)
            if d <= radio_km and (mejor is None or d < mejor[0]):
                mejor = (d, cand)
        if mejor:
            return mejor[1]
    return None


def tramos_de_corredor(corredor):
    """Lista de (CorredorTramo, TramoVial) ordenada por `orden`, con la
    geometría de cada tramo ya orientada en el sentido de avance de ESTE
    corredor (invierte `tramo.geometria` cuando `sentido="vuelta"`)."""
    filas = list(corredor.tramos.select_related("tramo", "tramo__nodo_inicio", "tramo__nodo_fin").order_by("orden"))
    out = []
    for ct in filas:
        geom = ct.tramo.geometria or []
        if ct.sentido == "vuelta":
            geom = list(reversed(geom))
        out.append((ct, ct.tramo, geom))
    return out


def detectar_corredores_compartidos(localidad_origen, localidad_destino):
    """Dado un par de `Localidad`, responde qué corredores comparten ese
    trayecto y en qué condiciones — las preguntas de "detección de
    corredores compartidos": qué corredores contienen el tramo, en qué
    orden, en qué sentido, si requiere desvío, si es candidato a Compartida.

    Solo considera corredores con `estado_validacion` en
    (TRAZADO_CALCULADO, VALIDADO) — sin geometría real no hay nada que
    "detectar", sería adivinar por nombre (justo lo que se pidió evitar).

    Devuelve una lista de dicts:
        {
            "corredor": Corredor, "orden_origen": int, "orden_destino": int,
            "tramo_completo": bool,   # origen y destino en la secuencia, en
                                       # el MISMO sentido de avance (nunca al revés)
            "requiere_desvio": bool,  # alguna CorredorParada intermedia entre
                                       # origen y destino tiene requiere_desvio=True
            "candidato_a_compartida": bool,
        }
    Vacía si ninguno matchea (nunca bloquea al llamador)."""
    from apps.tercerizacion.models import Corredor, CorredorParada

    resultados = []
    corredores = Corredor.objects.filter(
        activo=True, estado_validacion__in=[Corredor.ESTADO_TRAZADO_CALCULADO, Corredor.ESTADO_VALIDADO],
    ).prefetch_related("tramos__tramo__nodo_inicio", "tramos__tramo__nodo_fin", "paradas")

    for corredor in corredores:
        # Posición (orden de CorredorTramo) de cada Localidad en la secuencia
        # de este corredor — un nodo puede ser el inicio de un tramo (su
        # `orden`) o el fin del último tramo (orden + 1, el nodo final del
        # corredor). Recorrido explícito en el sentido de avance de ESTE
        # corredor, para no depender de nodo_inicio/nodo_fin "crudos" del
        # TramoVial (que son fijos, no relativos a un corredor en particular).
        tramos = list(corredor.tramos.select_related("tramo__nodo_inicio", "tramo__nodo_fin").order_by("orden"))
        posiciones = {}
        for ct in tramos:
            if ct.sentido == "ida":
                a, b = ct.tramo.nodo_inicio_id, ct.tramo.nodo_fin_id
            else:
                a, b = ct.tramo.nodo_fin_id, ct.tramo.nodo_inicio_id
            posiciones.setdefault(a, ct.orden)
            posiciones.setdefault(b, ct.orden + 1)

        pos_origen = posiciones.get(localidad_origen.id)
        pos_destino = posiciones.get(localidad_destino.id)
        if pos_origen is None or pos_destino is None:
            continue

        tramo_completo = pos_origen < pos_destino
        requiere_desvio = CorredorParada.objects.filter(
            corredor=corredor, requiere_desvio=True,
        ).exists() if tramo_completo else False

        resultados.append({
            "corredor": corredor, "orden_origen": pos_origen, "orden_destino": pos_destino,
            "tramo_completo": tramo_completo, "requiere_desvio": requiere_desvio,
            "candidato_a_compartida": tramo_completo,
        })
    return resultados


def recalcular_trazado(corredor):
    """Reconstruye `Corredor.trazado`/`distancia_total_km` concatenando la
    geometría de sus `CorredorTramo` ordenados (ver `tramos_de_corredor`).
    Solo tiene efecto si el corredor TIENE tramos — si no, no toca `trazado`
    (puede seguir siendo el que un admin cargó a mano con "Calcular
    trazado"). Se llama explícitamente (comando de seed/backfill, o un
    futuro botón "Recalcular" en el CRUD) — nunca automático vía signal, para
    que el momento del recálculo quede siempre auditable.

    Actualiza también `estado_validacion`: TRAZADO_CALCULADO si todos los
    tramos tienen geometría real, PENDIENTE_TRAZADO si falta alguno,
    ERROR_TRAZADO si algún tramo quedó en error. Nunca promueve a VALIDADO
    (eso es una revisión humana, explícita, desde el CRUD)."""
    from apps.tercerizacion.models import Corredor, TramoVial

    filas = tramos_de_corredor(corredor)
    if not filas:
        return

    trazado = []
    distancia_km = Decimal("0")
    hay_error = False
    hay_pendiente = False
    for ct, tramo, geom in filas:
        if tramo.estado_validacion == TramoVial.ESTADO_ERROR:
            hay_error = True
        elif tramo.estado_validacion != TramoVial.ESTADO_CALCULADO or not geom:
            hay_pendiente = True
        else:
            if trazado and geom and trazado[-1] == geom[0]:
                trazado.extend(geom[1:])
            else:
                trazado.extend(geom)
            if tramo.distancia_km is not None:
                distancia_km += tramo.distancia_km

    corredor.trazado = trazado
    corredor.distancia_total_km = distancia_km if distancia_km > 0 else None
    if hay_error:
        corredor.estado_validacion = Corredor.ESTADO_ERROR_TRAZADO
    elif hay_pendiente or not trazado:
        corredor.estado_validacion = Corredor.ESTADO_PENDIENTE_TRAZADO
    else:
        corredor.estado_validacion = Corredor.ESTADO_TRAZADO_CALCULADO
    corredor.save(update_fields=["trazado", "distancia_total_km", "estado_validacion", "actualizado_en"])
