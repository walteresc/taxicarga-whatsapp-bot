"""Encomiendas P1 — cotizar, crear, asignar y mover el estado de un envío
door-to-door express. Reusa la flota de transportistas afiliados; el pago del
remitente y la contra-entrega llegan en fases posteriores.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    ConfiguracionEncomiendas, Envio, EventoTracking, RendicionCaja, RutaReparto,
    TarifaZona, ZonaReparto,
)

_Q = Decimal("0.01")


def _dec(v):
    if v in (None, ""):
        return Decimal(0)
    return v if isinstance(v, Decimal) else Decimal(str(v))


# --------------------------------------------------------------------------- #
#  Cotización
# --------------------------------------------------------------------------- #

def cotizar(*, origen_distrito, destino_distrito, nivel=Envio.NIVEL_EXPRESS, peso_kg=1):
    """Devuelve {'price', 'level', 'etaHours', 'zoneFrom', 'zoneTo'} o lanza
    ValidationError si no hay cobertura / tarifa."""
    zo = ZonaReparto.para_distrito(origen_distrito)
    zd = ZonaReparto.para_distrito(destino_distrito)
    if not zo:
        raise ValidationError({"origen": f"Sin cobertura en {origen_distrito}."})
    if not zd:
        raise ValidationError({"destino": f"Sin cobertura en {destino_distrito}."})

    tarifa = TarifaZona.objects.filter(origen=zo, destino=zd, nivel=nivel, activo=True).first()
    if not tarifa:
        raise ValidationError("No hay tarifa configurada para esa ruta y nivel de servicio.")

    peso = _dec(peso_kg)
    precio = _dec(tarifa.precio_base)
    if peso > tarifa.incluye_kg:
        extra_kg = (peso - _dec(tarifa.incluye_kg))
        precio += (extra_kg * _dec(tarifa.precio_kg_extra)).quantize(_Q, ROUND_HALF_UP)
    return {
        "price": float(precio.quantize(_Q)),
        "level": nivel,
        "etaHours": tarifa.eta_horas,
        "zoneFrom": zo.nombre,
        "zoneTo": zd.nombre,
    }


# --------------------------------------------------------------------------- #
#  Alta
# --------------------------------------------------------------------------- #

@transaction.atomic
def crear_envio(data, *, usuario=None):
    """`data` = dict con los campos del Envio (nombres del modelo). Cotiza solo
    si no viene `precio`."""
    campos = {
        f.name: data[f.name]
        for f in Envio._meta.get_fields()
        if getattr(f, "attname", None) and f.name in data and f.name not in ("id", "codigo", "token")
    }
    nivel = campos.get("nivel") or Envio.NIVEL_EXPRESS
    campos["nivel"] = nivel

    if not campos.get("precio"):
        cot = cotizar(
            origen_distrito=campos.get("origen_distrito", ""),
            destino_distrito=campos.get("destino_distrito", ""),
            nivel=nivel, peso_kg=campos.get("peso_kg", 1),
        )
        campos["precio"] = cot["price"]

    if campos.get("es_contraentrega") and not campos.get("monto_contraentrega"):
        raise ValidationError({"monto_contraentrega": "Indicá el monto a cobrar contra entrega."})

    envio = Envio.objects.create(creado_por=usuario, **campos)
    _evento(envio, Envio.ESTADO_REGISTRADO, "Envío registrado.", usuario=usuario)
    return envio


# --------------------------------------------------------------------------- #
#  Estado / eventos
# --------------------------------------------------------------------------- #

_TRANSICIONES = {
    Envio.ESTADO_REGISTRADO: {Envio.ESTADO_ASIGNADO, Envio.ESTADO_CANCELADO},
    Envio.ESTADO_ASIGNADO: {Envio.ESTADO_RECOGIDO, Envio.ESTADO_EN_RUTA, Envio.ESTADO_REGISTRADO, Envio.ESTADO_CANCELADO},
    Envio.ESTADO_RECOGIDO: {Envio.ESTADO_EN_RUTA, Envio.ESTADO_ENTREGADO, Envio.ESTADO_FALLIDO},
    Envio.ESTADO_EN_RUTA: {Envio.ESTADO_ENTREGADO, Envio.ESTADO_FALLIDO, Envio.ESTADO_DEVUELTO},
    Envio.ESTADO_FALLIDO: {Envio.ESTADO_EN_RUTA, Envio.ESTADO_DEVUELTO},
    Envio.ESTADO_ENTREGADO: set(),
    Envio.ESTADO_DEVUELTO: set(),
    Envio.ESTADO_CANCELADO: set(),
}


def _evento(envio, estado, descripcion="", *, ubicacion="", usuario=None):
    return EventoTracking.objects.create(
        envio=envio, estado=estado, descripcion=descripcion or "",
        ubicacion=ubicacion or "", creado_por=usuario,
    )


@transaction.atomic
def asignar_envio(envio, transportista, *, vehiculo=None, usuario=None):
    if envio.estado not in (Envio.ESTADO_REGISTRADO, Envio.ESTADO_ASIGNADO):
        raise ValidationError("El envío ya no se puede reasignar.")
    if vehiculo is not None and vehiculo.transportista_id != transportista.id:
        raise ValidationError({"vehicleId": "El vehículo no es de ese transportista."})
    envio.transportista = transportista
    envio.transportista_vehiculo = vehiculo
    envio.estado = Envio.ESTADO_ASIGNADO
    envio.save(update_fields=["transportista", "transportista_vehiculo", "estado", "actualizado_en"])
    _evento(envio, Envio.ESTADO_ASIGNADO, f"Asignado a {transportista.nombre}.", usuario=usuario)
    return envio


def _calc_cod_a_remitir(cobrado):
    """Lo que la plataforma le debe al remitente: lo cobrado, menos el envío (si
    va incluido) y menos la comisión COD."""
    cfg = ConfiguracionEncomiendas.get_solo()
    cobrado = _dec(cobrado)
    fee = (cobrado * _dec(cfg.comision_cod_porcentaje) / Decimal(100)).quantize(_Q, ROUND_HALF_UP)
    return cobrado, fee, cfg.envio_incluido_en_cod


@transaction.atomic
def registrar_evento(envio, estado, *, descripcion="", ubicacion="", recibido_por="",
                     prueba_foto=None, prueba_firma="", motivo_fallo="",
                     cod_cobrado=None, cod_medio="", cod_comprobante=None, usuario=None):
    if estado not in dict(Envio.ESTADOS):
        raise ValidationError({"state": "Estado no válido."})
    if estado not in _TRANSICIONES.get(envio.estado, set()):
        raise ValidationError(
            f"No se puede pasar de «{envio.get_estado_display()}» a «{dict(Envio.ESTADOS)[estado]}»."
        )

    # Validación de COD antes de mutar nada.
    cod_monto = None
    if estado == Envio.ESTADO_ENTREGADO and envio.es_contraentrega:
        cod_monto = _dec(cod_cobrado if cod_cobrado not in (None, "") else envio.monto_contraentrega)
        if cod_monto <= 0:
            raise ValidationError({"codCollected": "Registrá cuánto cobraste contra entrega."})
        if cod_medio and cod_medio not in dict(Envio.COD_MEDIOS):
            raise ValidationError({"codMethod": "Medio de cobro no válido."})

    ahora = timezone.now()
    campos = ["estado", "actualizado_en"]
    envio.estado = estado
    if estado == Envio.ESTADO_RECOGIDO:
        envio.recogido_en = ahora
        campos.append("recogido_en")
    elif estado == Envio.ESTADO_ENTREGADO:
        envio.entregado_en = ahora
        envio.recibido_por = recibido_por or ""
        if prueba_foto is not None:
            envio.prueba_foto = prueba_foto
        if prueba_firma:
            envio.prueba_firma = prueba_firma
        campos += ["entregado_en", "recibido_por", "prueba_foto", "prueba_firma"]
        if envio.es_contraentrega:
            cobrado, fee, incluye_envio = _calc_cod_a_remitir(cod_monto)
            a_remitir = cobrado - fee - (_dec(envio.precio) if incluye_envio else Decimal(0))
            envio.cod_cobrado = cobrado
            envio.cod_medio = cod_medio or Envio.COD_EFECTIVO
            envio.cod_cobrado_en = ahora
            envio.cod_a_remitir = max(a_remitir, Decimal(0)).quantize(_Q)
            if cod_comprobante is not None:
                envio.cod_comprobante = cod_comprobante
            campos += ["cod_cobrado", "cod_medio", "cod_cobrado_en", "cod_a_remitir", "cod_comprobante"]
    elif estado == Envio.ESTADO_FALLIDO:
        envio.motivo_fallo = motivo_fallo or descripcion or "No entregado"
        envio.intentos_entrega = (envio.intentos_entrega or 0) + 1
        campos += ["motivo_fallo", "intentos_entrega"]
    envio.save(update_fields=campos)

    _evento(envio, estado, descripcion or dict(Envio.ESTADOS)[estado],
            ubicacion=ubicacion, usuario=usuario)

    if estado in (Envio.ESTADO_ENTREGADO, Envio.ESTADO_FALLIDO) and envio.ruta_id:
        _cerrar_ruta_si_termino(envio.ruta)
    return envio


@transaction.atomic
def cancelar_envio(envio, *, motivo="", usuario=None):
    if envio.estado not in (Envio.ESTADO_REGISTRADO, Envio.ESTADO_ASIGNADO):
        raise ValidationError("Solo se puede cancelar antes del recojo.")
    envio.estado = Envio.ESTADO_CANCELADO
    envio.save(update_fields=["estado", "actualizado_en"])
    _evento(envio, Envio.ESTADO_CANCELADO, motivo or "Cancelado.", usuario=usuario)
    return envio


# --------------------------------------------------------------------------- #
#  Rutas de reparto (P2)
# --------------------------------------------------------------------------- #

def _zona_orden(distrito):
    z = ZonaReparto.para_distrito(distrito)
    return (z.orden, (distrito or "").lower()) if z else (99, (distrito or "").lower())


@transaction.atomic
def crear_ruta(*, transportista, fecha, vehiculo=None, envios=None, usuario=None):
    ruta = RutaReparto.objects.create(
        transportista=transportista, transportista_vehiculo=vehiculo, fecha=fecha, creado_por=usuario,
    )
    for e in (envios or []):
        agregar_a_ruta(ruta, e)
    reordenar_ruta(ruta)
    return ruta


@transaction.atomic
def agregar_a_ruta(ruta, envio):
    if ruta.estado == RutaReparto.ESTADO_CERRADA:
        raise ValidationError("La ruta ya está cerrada.")
    if envio.estado not in (Envio.ESTADO_REGISTRADO, Envio.ESTADO_ASIGNADO, Envio.ESTADO_RECOGIDO, Envio.ESTADO_EN_RUTA):
        raise ValidationError(f"{envio.codigo} ya no se puede rutear ({envio.get_estado_display()}).")
    envio.ruta = ruta
    envio.transportista = ruta.transportista
    envio.transportista_vehiculo = ruta.transportista_vehiculo
    if envio.estado == Envio.ESTADO_REGISTRADO:
        envio.estado = Envio.ESTADO_ASIGNADO
        _evento(envio, Envio.ESTADO_ASIGNADO, f"En ruta {ruta.codigo} con {ruta.transportista.nombre}.")
    envio.save(update_fields=["ruta", "transportista", "transportista_vehiculo", "estado", "actualizado_en"])
    return envio


@transaction.atomic
def quitar_de_ruta(ruta, envio):
    if envio.estado in (Envio.ESTADO_ENTREGADO, Envio.ESTADO_FALLIDO):
        raise ValidationError("Ese envío ya se cerró.")
    envio.ruta = None
    envio.orden_ruta = 0
    envio.save(update_fields=["ruta", "orden_ruta", "actualizado_en"])
    reordenar_ruta(ruta)


@transaction.atomic
def reordenar_ruta(ruta, *, orden_manual=None):
    """`orden_manual` = lista de códigos en el orden deseado. Sin eso, ordena por
    zona + distrito (agrupa entregas cercanas)."""
    paradas = list(ruta.paradas.all())
    if orden_manual:
        pos = {c: i for i, c in enumerate(orden_manual)}
        paradas.sort(key=lambda e: pos.get(e.codigo, 999))
    else:
        paradas.sort(key=lambda e: _zona_orden(e.destino_distrito))
    for i, e in enumerate(paradas, start=1):
        if e.orden_ruta != i:
            e.orden_ruta = i
            e.save(update_fields=["orden_ruta"])


@transaction.atomic
def iniciar_ruta(ruta):
    if ruta.estado != RutaReparto.ESTADO_PLANIFICADA:
        raise ValidationError("La ruta ya fue iniciada.")
    if not ruta.paradas.exists():
        raise ValidationError("La ruta no tiene envíos.")
    ruta.estado = RutaReparto.ESTADO_EN_CURSO
    ruta.iniciada_en = timezone.now()
    ruta.save(update_fields=["estado", "iniciada_en", "actualizado_en"])
    ruta.paradas.filter(estado__in=[Envio.ESTADO_ASIGNADO, Envio.ESTADO_RECOGIDO]).update(estado=Envio.ESTADO_EN_RUTA)
    return ruta


@transaction.atomic
def cerrar_ruta(ruta, *, usuario=None):
    ruta.estado = RutaReparto.ESTADO_CERRADA
    ruta.cerrada_en = timezone.now()
    ruta.save(update_fields=["estado", "cerrada_en", "actualizado_en"])
    # los que quedaron sin entregar y sin fallar → devueltos
    for e in ruta.paradas.filter(estado__in=list(Envio.ABIERTOS)):
        e.estado = Envio.ESTADO_DEVUELTO
        e.save(update_fields=["estado", "actualizado_en"])
        _evento(e, Envio.ESTADO_DEVUELTO, "Ruta cerrada sin completar la entrega.", usuario=usuario)
    return ruta


def _cerrar_ruta_si_termino(ruta):
    if ruta.estado == RutaReparto.ESTADO_EN_CURSO and not ruta.paradas.filter(estado__in=list(Envio.ABIERTOS)).exists():
        ruta.estado = RutaReparto.ESTADO_CERRADA
        ruta.cerrada_en = timezone.now()
        ruta.save(update_fields=["estado", "cerrada_en", "actualizado_en"])


def ruta_progreso(ruta):
    total = ruta.paradas.count()
    hechas = ruta.paradas.filter(estado__in=[Envio.ESTADO_ENTREGADO, Envio.ESTADO_FALLIDO, Envio.ESTADO_DEVUELTO]).count()
    return {"total": total, "done": hechas,
            "delivered": ruta.paradas.filter(estado=Envio.ESTADO_ENTREGADO).count()}


# --------------------------------------------------------------------------- #
#  Contra-entrega (COD) — rendición de caja del motorizado + remisión al remitente (P3)
# --------------------------------------------------------------------------- #

def cod_por_rendir(transportista=None):
    """Envíos COD cobrados que el motorizado todavía no rindió."""
    qs = Envio.objects.filter(
        es_contraentrega=True, estado=Envio.ESTADO_ENTREGADO,
        cod_rendido=False, cod_cobrado__gt=0, rendicion__isnull=True,
    ).select_related("transportista")
    if transportista is not None:
        qs = qs.filter(transportista=transportista)
    return qs


@transaction.atomic
def crear_rendicion(transportista, *, envios=None, usuario=None):
    envios = list(envios) if envios is not None else list(cod_por_rendir(transportista))
    envios = [e for e in envios if e.transportista_id == transportista.id and e.cod_rendido is False and e.rendicion_id is None]
    if not envios:
        raise ValidationError("No hay contra-entregas por rendir de ese motorizado.")
    esperado = sum((_dec(e.cod_cobrado) for e in envios), Decimal(0))
    r = RendicionCaja.objects.create(transportista=transportista, esperado=esperado)
    Envio.objects.filter(pk__in=[e.pk for e in envios]).update(rendicion=r)
    return r


@transaction.atomic
def conciliar_rendicion(rendicion, *, entregado, usuario=None, referencia="", nota=""):
    if rendicion.estado == RendicionCaja.ESTADO_CONCILIADA:
        raise ValidationError("La rendición ya está conciliada.")
    entregado = _dec(entregado)
    rendicion.entregado = entregado
    rendicion.diferencia = (entregado - rendicion.esperado).quantize(_Q)
    rendicion.estado = RendicionCaja.ESTADO_CONCILIADA
    rendicion.referencia = referencia or ""
    if nota:
        rendicion.nota = nota
    rendicion.conciliada_por = usuario
    rendicion.conciliada_en = timezone.now()
    rendicion.save()
    rendicion.envios.update(cod_rendido=True)
    return rendicion


def cod_por_remitir():
    """Neto que la plataforma le debe a los remitentes (COD ya rendido, sin remitir)."""
    return Envio.objects.filter(
        es_contraentrega=True, estado=Envio.ESTADO_ENTREGADO,
        cod_rendido=True, cod_remitido=False, cod_a_remitir__gt=0,
    )


@transaction.atomic
def marcar_remitido(envios, *, referencia="", usuario=None):
    n = Envio.objects.filter(pk__in=[e.pk for e in envios], cod_rendido=True, cod_remitido=False).update(
        cod_remitido=True, cod_remitido_ref=referencia or "",
    )
    return n


# --------------------------------------------------------------------------- #
#  Seguimiento público (por token) — sin datos sensibles de la otra parte
# --------------------------------------------------------------------------- #

def tracking_publico(envio):
    return {
        "code": envio.codigo,
        "state": envio.estado,
        "stateLabel": envio.get_estado_display(),
        "level": envio.nivel,
        "route": f"{envio.origen_distrito} → {envio.destino_distrito}",
        "recipient": envio.destinatario_nombre,
        "deliveredTo": envio.recibido_por or None,
        "deliveredAt": envio.entregado_en.isoformat() if envio.entregado_en else None,
        "events": [
            {
                "state": e.estado,
                "label": dict(Envio.ESTADOS).get(e.estado, e.estado),
                "detail": e.descripcion,
                "at": e.creado_en.isoformat(),
            }
            for e in envio.eventos.all()
        ],
    }
