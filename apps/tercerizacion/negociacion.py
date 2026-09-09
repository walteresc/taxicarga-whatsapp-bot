"""Lógica de las mesas de negociación (F2).

Una carga (Lead) tiene hasta dos frentes: `venta` (cliente ↔ TaxiCarga) y uno o
más `compra` (TaxiCarga ↔ cada transportista). El asesor mueve todo: puede
escribir por cualquiera de las partes (registra lo que le dijeron por teléfono),
lanzar propuestas, responderlas, y **pausar** la mesa (control) — con la mesa
pausada, cliente y transportista no pueden escribir; el asesor sí.
"""
from django.utils import timezone

from .models import HiloNegociacion, MensajeNegociacion


class NegociacionError(Exception):
    """Regla de negocio violada (hilo pausado/cerrado, propuesta ya resuelta…)."""


def abrir_hilo(lead, tipo, *, usuario=None, cotizacion=None, publicacion=None,
               contraparte=None, monto_objetivo=None):
    """Idempotente por (lead, tipo, contraparte). Rellena los vínculos y el
    monto objetivo si llegan después de la creación."""
    hilo, creado = HiloNegociacion.objects.get_or_create(
        lead=lead, tipo=tipo, contraparte=contraparte,
        defaults={
            "creado_por": usuario,
            "supervisor": usuario,
            "cotizacion": cotizacion,
            "publicacion": publicacion,
            "monto_objetivo": monto_objetivo,
        },
    )
    if not creado:
        campos = []
        if cotizacion is not None and hilo.cotizacion_id != cotizacion.id:
            hilo.cotizacion = cotizacion
            campos.append("cotizacion")
        if publicacion is not None and hilo.publicacion_id != publicacion.id:
            hilo.publicacion = publicacion
            campos.append("publicacion")
        if monto_objetivo is not None and hilo.monto_objetivo != monto_objetivo:
            hilo.monto_objetivo = monto_objetivo
            campos.append("monto_objetivo")
        if campos:
            hilo.save(update_fields=campos + ["actualizado_en"])
    return hilo, creado


def _contraparte_emisor(hilo, emisor):
    """El otro lado de la mesa respecto de `emisor`."""
    if emisor == MensajeNegociacion.EMISOR_TAXICARGA:
        return (
            MensajeNegociacion.EMISOR_CLIENTE
            if hilo.tipo == HiloNegociacion.TIPO_VENTA
            else MensajeNegociacion.EMISOR_TRANSPORTISTA
        )
    return MensajeNegociacion.EMISOR_TAXICARGA


def _mensaje_sistema(hilo, texto):
    return MensajeNegociacion.objects.create(
        hilo=hilo, emisor=MensajeNegociacion.EMISOR_SISTEMA,
        tipo=MensajeNegociacion.TIPO_SISTEMA, texto=texto,
    )


def _puede_escribir(hilo, emisor):
    if hilo.estado == HiloNegociacion.ESTADO_CERRADA:
        return False
    if hilo.estado == HiloNegociacion.ESTADO_PAUSADA and emisor in (
        MensajeNegociacion.EMISOR_CLIENTE, MensajeNegociacion.EMISOR_TRANSPORTISTA,
    ):
        return False
    return True


def publicar_mensaje(hilo, *, emisor, texto="", autor=None,
                     canal=MensajeNegociacion.CANAL_CRM,
                     propuesta_monto=None, mensaje_whatsapp=None):
    """Agrega un mensaje. Si trae `propuesta_monto` es una propuesta (pendiente
    de respuesta) y actualiza `monto_actual` del hilo. Un mensaje nuevo reabre
    un hilo que estaba en acuerdo/sin_acuerdo."""
    if not _puede_escribir(hilo, emisor):
        raise NegociacionError("La negociación está pausada o cerrada.")

    es_propuesta = propuesta_monto is not None
    msg = MensajeNegociacion.objects.create(
        hilo=hilo,
        emisor=emisor,
        autor=autor,
        canal=canal,
        tipo=MensajeNegociacion.TIPO_PROPUESTA if es_propuesta else MensajeNegociacion.TIPO_TEXTO,
        texto=texto or "",
        propuesta_monto=propuesta_monto,
        propuesta_estado=MensajeNegociacion.PROP_PENDIENTE if es_propuesta else "",
        mensaje_whatsapp=mensaje_whatsapp,
    )

    campos = ["actualizado_en"]
    if es_propuesta:
        hilo.monto_actual = propuesta_monto
        campos.append("monto_actual")
    if hilo.estado in (HiloNegociacion.ESTADO_ACUERDO, HiloNegociacion.ESTADO_SIN_ACUERDO):
        hilo.estado = HiloNegociacion.ESTADO_ABIERTA
        campos.append("estado")
    hilo.save(update_fields=campos)
    return msg


def responder_propuesta(mensaje, accion, *, usuario, monto=None, texto=""):
    """`accion` ∈ {aceptar, contraofertar, rechazar}. La respuesta la da la
    contraparte del emisor de la propuesta (el asesor la registra)."""
    hilo = mensaje.hilo
    if (
        mensaje.tipo != MensajeNegociacion.TIPO_PROPUESTA
        or mensaje.propuesta_estado != MensajeNegociacion.PROP_PENDIENTE
    ):
        raise NegociacionError("Esa propuesta ya fue respondida.")
    if hilo.estado == HiloNegociacion.ESTADO_CERRADA:
        raise NegociacionError("La negociación está cerrada.")

    ahora = timezone.now()
    mensaje.respondido_por = usuario
    mensaje.respondido_en = ahora

    if accion == "aceptar":
        mensaje.propuesta_estado = MensajeNegociacion.PROP_ACEPTADA
        mensaje.save(update_fields=["propuesta_estado", "respondido_por", "respondido_en"])
        hilo.monto_acordado = mensaje.propuesta_monto
        hilo.monto_actual = mensaje.propuesta_monto
        hilo.estado = HiloNegociacion.ESTADO_ACUERDO
        hilo.save(update_fields=["monto_acordado", "monto_actual", "estado", "actualizado_en"])
        _mensaje_sistema(hilo, f"Propuesta aceptada: S/ {mensaje.propuesta_monto:g}")
        return mensaje

    if accion == "rechazar":
        mensaje.propuesta_estado = MensajeNegociacion.PROP_RECHAZADA
        mensaje.save(update_fields=["propuesta_estado", "respondido_por", "respondido_en"])
        _mensaje_sistema(hilo, f"Propuesta rechazada: S/ {mensaje.propuesta_monto:g}")
        return mensaje

    if accion == "contraofertar":
        if monto is None:
            raise NegociacionError("Falta el monto de la contraoferta.")
        mensaje.propuesta_estado = MensajeNegociacion.PROP_CONTRAOFERTADA
        mensaje.save(update_fields=["propuesta_estado", "respondido_por", "respondido_en"])
        return publicar_mensaje(
            hilo,
            emisor=_contraparte_emisor(hilo, mensaje.emisor),
            autor=usuario,
            texto=texto,
            propuesta_monto=monto,
        )

    raise NegociacionError("Acción no válida.")


def pausar_hilo(hilo, usuario, motivo=""):
    if hilo.estado == HiloNegociacion.ESTADO_CERRADA:
        raise NegociacionError("La negociación ya está cerrada.")
    hilo.estado = HiloNegociacion.ESTADO_PAUSADA
    hilo.supervisor = usuario
    hilo.motivo_pausa = motivo or ""
    hilo.save(update_fields=["estado", "supervisor", "motivo_pausa", "actualizado_en"])
    _mensaje_sistema(hilo, "Negociación pausada por el asesor" + (f" — {motivo}" if motivo else "."))
    return hilo


def reanudar_hilo(hilo, usuario):
    if hilo.estado != HiloNegociacion.ESTADO_PAUSADA:
        raise NegociacionError("La negociación no está pausada.")
    hilo.estado = HiloNegociacion.ESTADO_ABIERTA
    hilo.motivo_pausa = ""
    hilo.supervisor = usuario
    hilo.save(update_fields=["estado", "motivo_pausa", "supervisor", "actualizado_en"])
    _mensaje_sistema(hilo, "Negociación reanudada.")
    return hilo


def cerrar_hilo(hilo, usuario, *, con_acuerdo):
    hilo.estado = HiloNegociacion.ESTADO_CERRADA
    hilo.cerrado_en = timezone.now()
    hilo.supervisor = usuario
    hilo.save(update_fields=["estado", "cerrado_en", "supervisor", "actualizado_en"])
    _mensaje_sistema(
        hilo,
        "Negociación cerrada con acuerdo." if con_acuerdo else "Negociación cerrada sin acuerdo.",
    )
    return hilo


# --------------------------------------------------------------------------- #
#  Margen en vivo
# --------------------------------------------------------------------------- #

def _venta_vigente(lead):
    """Mejor estimación del precio de venta al cliente ahora mismo."""
    venta = lead.hilos_negociacion.filter(tipo=HiloNegociacion.TIPO_VENTA).first()
    if venta and (venta.monto_acordado or venta.monto_actual):
        return venta.monto_acordado or venta.monto_actual
    cot = lead.hilos_negociacion.filter(
        tipo=HiloNegociacion.TIPO_VENTA, cotizacion__isnull=False,
    ).select_related("cotizacion").first()
    if cot and cot.cotizacion:
        c = cot.cotizacion
        if c.precio_acordado or c.precio_cliente:
            return c.precio_acordado or c.precio_cliente
    return None


def _costo_vigente(lead):
    """Mejor estimación del costo de tercerización ahora mismo (hilo de compra
    con acuerdo, si hay; si no, el mejor monto vivo; si no, el precio publicado)."""
    compras = list(lead.hilos_negociacion.filter(tipo=HiloNegociacion.TIPO_COMPRA))
    acordados = [h.monto_acordado for h in compras if h.monto_acordado is not None]
    if acordados:
        return min(acordados)
    vivos = [h.monto_actual for h in compras if h.monto_actual is not None]
    if vivos:
        return min(vivos)
    for h in compras:
        if h.publicacion and h.publicacion.precio_publicado is not None:
            return h.publicacion.precio_publicado
    return None


def margen_en_vivo(lead):
    """{sale, cost, amount, pct} — cualquiera puede ser None si falta el dato."""
    sale = _venta_vigente(lead)
    cost = _costo_vigente(lead)
    amount = pct = None
    if sale is not None and cost is not None:
        amount = sale - cost
        pct = round(float(amount) / float(sale) * 100, 1) if sale else None
    return {
        "sale": float(sale) if sale is not None else None,
        "cost": float(cost) if cost is not None else None,
        "amount": float(amount) if amount is not None else None,
        "pct": pct,
    }
