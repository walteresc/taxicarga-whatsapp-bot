"""Encomiendas P1 — cotizar, crear, asignar y mover el estado de un envío
door-to-door express. Reusa la flota de transportistas afiliados; el pago del
remitente y la contra-entrega llegan en fases posteriores.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Envio, EventoTracking, TarifaZona, ZonaReparto

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
    Envio.ESTADO_ASIGNADO: {Envio.ESTADO_RECOGIDO, Envio.ESTADO_REGISTRADO, Envio.ESTADO_CANCELADO},
    Envio.ESTADO_RECOGIDO: {Envio.ESTADO_EN_RUTA, Envio.ESTADO_ENTREGADO, Envio.ESTADO_FALLIDO},
    Envio.ESTADO_EN_RUTA: {Envio.ESTADO_ENTREGADO, Envio.ESTADO_FALLIDO},
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


@transaction.atomic
def registrar_evento(envio, estado, *, descripcion="", ubicacion="", recibido_por="",
                     prueba_foto="", motivo_fallo="", usuario=None):
    if estado not in dict(Envio.ESTADOS):
        raise ValidationError({"state": "Estado no válido."})
    if estado not in _TRANSICIONES.get(envio.estado, set()):
        raise ValidationError(
            f"No se puede pasar de «{envio.get_estado_display()}» a «{dict(Envio.ESTADOS)[estado]}»."
        )

    ahora = timezone.now()
    campos = ["estado", "actualizado_en"]
    envio.estado = estado
    if estado == Envio.ESTADO_RECOGIDO:
        envio.recogido_en = ahora
        campos.append("recogido_en")
    elif estado == Envio.ESTADO_ENTREGADO:
        envio.entregado_en = ahora
        envio.recibido_por = recibido_por or ""
        envio.prueba_foto = prueba_foto or ""
        campos += ["entregado_en", "recibido_por", "prueba_foto"]
    elif estado == Envio.ESTADO_FALLIDO:
        envio.motivo_fallo = motivo_fallo or descripcion or "No entregado"
        campos.append("motivo_fallo")
    envio.save(update_fields=campos)

    _evento(envio, estado, descripcion or dict(Envio.ESTADOS)[estado],
            ubicacion=ubicacion, usuario=usuario)
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
