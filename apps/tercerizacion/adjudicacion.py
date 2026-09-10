"""F3 · Publicar una carga a transportistas, recibir ofertas y adjudicar.

Adjudicar crea la `ProgramacionServicio` tercerizada (misma forma que la
asignación manual desde la Pizarra) y cierra las mesas de negociación de compra.
El canal de WhatsApp del bot de transportistas queda para más adelante:
`registrar_oferta` acepta `canal="whatsapp"` pero nada lo llama en vivo todavía.
"""
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from apps.tercerizacion import negociacion as neg
from apps.tercerizacion.models import (
    HiloNegociacion, MensajeNegociacion, OfertaTransportista, PublicacionCarga,
)


class AdjudicacionError(Exception):
    """Regla de negocio violada al publicar/ofertar/adjudicar."""


_ESTADOS_PUBLICABLES = (PublicacionCarga.ESTADO_BORRADOR,)
_ESTADOS_ABIERTOS = (
    PublicacionCarga.ESTADO_ABIERTA,
    PublicacionCarga.ESTADO_PUBLICADA,
    PublicacionCarga.ESTADO_CON_OFERTAS,
)


def publicar_publicacion(pub, usuario, *, grupos=None):
    """Borrador → abierta. `estado='abierta'` es lo que el bot de transportistas
    reconoce (`identificar_posible_transportista`)."""
    if pub.estado not in _ESTADOS_PUBLICABLES:
        raise AdjudicacionError("La publicación ya no está en borrador.")
    pub.estado = PublicacionCarga.ESTADO_ABIERTA
    pub.publicada_por = usuario
    pub.publicada_en = timezone.now()
    if grupos:
        pub.grupos_publicados = sorted(set((pub.grupos_publicados or []) + list(grupos)))
    pub.save(update_fields=["estado", "publicada_por", "publicada_en", "grupos_publicados"])
    return pub


@transaction.atomic
def registrar_oferta(pub, *, monto, usuario, transportista=None, transportista_vehiculo=None,
                     cliente=None, nota="", canal=MensajeNegociacion.CANAL_CRM,
                     mensaje_whatsapp=None):
    """Crea o actualiza la oferta de un transportista y la refleja como propuesta
    en su mesa de negociación de compra."""
    if pub.estado not in _ESTADOS_ABIERTOS:
        raise AdjudicacionError("La publicación no está recibiendo ofertas.")
    if transportista is None and cliente is None:
        raise AdjudicacionError("Falta identificar al transportista.")

    if transportista is not None:
        oferta, creada = OfertaTransportista.objects.get_or_create(
            publicacion=pub, transportista=transportista,
            defaults={"cliente": cliente, "precio_ofertado": monto},
        )
    else:
        oferta, creada = OfertaTransportista.objects.get_or_create(
            publicacion=pub, cliente=cliente,
            defaults={"precio_ofertado": monto},
        )

    if transportista_vehiculo is not None:
        oferta.transportista_vehiculo = transportista_vehiculo
    if creada and oferta.precio_ofertado is None:
        oferta.precio_ofertado = monto
    oferta.monto_actual = monto
    oferta.estado = OfertaTransportista.ESTADO_CONTRAOFERTA_TR if not creada else OfertaTransportista.ESTADO_PENDIENTE
    oferta.mensaje_origen = mensaje_whatsapp or oferta.mensaje_origen
    oferta.save()

    if pub.estado != PublicacionCarga.ESTADO_CON_OFERTAS:
        pub.estado = PublicacionCarga.ESTADO_CON_OFERTAS
        pub.save(update_fields=["estado"])

    lead = pub.servicio.lead_origen if pub.servicio.lead_origen_id else None
    hilo = None
    if lead is not None:
        hilo, _ = neg.abrir_hilo(
            lead, HiloNegociacion.TIPO_COMPRA, usuario=usuario,
            publicacion=pub, transportista=transportista, contraparte=cliente,
            monto_objetivo=pub.precio_publicado,
        )
        try:
            neg.publicar_mensaje(
                hilo, emisor=MensajeNegociacion.EMISOR_TRANSPORTISTA, autor=usuario,
                texto=nota, canal=canal, propuesta_monto=monto, mensaje_whatsapp=mensaje_whatsapp,
            )
        except neg.NegociacionError:
            pass
    return oferta, hilo


def registrar_oferta_desde_whatsapp(pub, cliente, monto, *, mensaje_whatsapp=None, nota=""):
    """Punto de entrada para cuando el bot de transportistas capture
    'OFERTA-<código>' + un monto. NO está enganchado al pipeline de mensajes
    todavía — se llamará desde ahí en una fase posterior."""
    return registrar_oferta(
        pub, monto=monto, usuario=None, cliente=cliente,
        canal=MensajeNegociacion.CANAL_WHATSAPP, nota=nota, mensaje_whatsapp=mensaje_whatsapp,
    )


@transaction.atomic
def adjudicar_publicacion(pub, oferta, usuario, *, transportista_vehiculo=None,
                          precio_cliente=None, autoriza_bajo_margen=False):
    """Cierra la publicación a favor de una oferta: crea la ProgramacionServicio
    tercerizada, rechaza las demás ofertas y cierra sus mesas de compra.

    Además fija el precio de venta al cliente: si se pasa `precio_cliente` se
    usa ese; si el servicio todavía no tiene precio, se calcula como
    costo × (1 + markup de Configuración). Si el precio resultante no cubre el
    piso de margen del negocio, aborta salvo `autoriza_bajo_margen=True`.
    """
    from apps.campo.models import ProgramacionServicio
    from apps.servicios.models import Servicio
    from apps.tercerizacion.services import (
        evaluar_margen_tercerizacion, precio_cliente_sugerido,
    )

    if pub.estado == PublicacionCarga.ESTADO_ADJUDICADA:
        raise AdjudicacionError("La publicación ya fue adjudicada.")
    if oferta.publicacion_id != pub.id:
        raise AdjudicacionError("La oferta no pertenece a esta publicación.")
    if oferta.transportista_id is None:
        raise AdjudicacionError(
            "La oferta la hizo un contacto de WhatsApp sin afiliar. Dá de alta al "
            "transportista como afiliado y vuelve a registrar la oferta antes de adjudicar."
        )

    tv = transportista_vehiculo or oferta.transportista_vehiculo
    if tv is None:
        vehiculos = list(oferta.transportista.vehiculos.filter(activo=True))
        if len(vehiculos) == 1:
            tv = vehiculos[0]
        else:
            raise AdjudicacionError("Elegí con qué vehículo del transportista se cubre el servicio.")
    if tv.transportista_id != oferta.transportista_id:
        raise AdjudicacionError("Ese vehículo no es del transportista de la oferta.")

    servicio = pub.servicio
    if not servicio.fecha_servicio:
        raise AdjudicacionError("El servicio necesita fecha antes de adjudicar.")

    from apps.servicios.utils import parse_horario
    hora_ini = parse_horario(servicio.horario_servicio) or datetime.min.time().replace(hour=8)
    hora_fin = (datetime.combine(servicio.fecha_servicio, hora_ini) + timedelta(hours=1)).time()

    activa = servicio.programaciones.exclude(estado_operativo=ProgramacionServicio.ESTADO_CANCELADO).first()
    if activa:
        raise AdjudicacionError(f"El servicio ya tiene una programación ({activa}).")

    monto = oferta.monto_actual or oferta.precio_ofertado or pub.precio_publicado or servicio.precio or 0

    # Precio de venta al cliente = el que se pasa, o el que ya tenía el servicio,
    # o costo + markup. Vigila el piso de margen del negocio.
    from decimal import Decimal
    nuevo_precio = None
    if precio_cliente not in (None, ""):
        nuevo_precio = Decimal(str(precio_cliente))
    elif not servicio.precio:
        nuevo_precio = precio_cliente_sugerido(monto)
    precio_efectivo = nuevo_precio if nuevo_precio is not None else servicio.precio
    if precio_efectivo and monto:
        ev = evaluar_margen_tercerizacion(precio_efectivo, monto)
        if ev["meetsFloor"] is False and not autoriza_bajo_margen:
            raise AdjudicacionError(
                f"El precio al cliente (S/ {precio_efectivo:g}) no cubre el margen "
                f"mínimo sobre el costo del transportista (S/ {monto:g}). "
                f"Ajustá el precio o autorizá el margen bajo."
            )
    if nuevo_precio is not None and nuevo_precio != servicio.precio:
        servicio.precio = nuevo_precio
        servicio.save(update_fields=["precio"])

    prog = ProgramacionServicio.objects.create(
        servicio=servicio, vehiculo=None,
        transportista=oferta.transportista, transportista_vehiculo=tv,
        conductor_externo="",
        fecha=servicio.fecha_servicio, hora_inicio=hora_ini, hora_fin=hora_fin,
        monto=monto,
    )

    if servicio.modalidad_ejecucion != Servicio.MODALIDAD_TERCERIZADO:
        servicio.modalidad_ejecucion = Servicio.MODALIDAD_TERCERIZADO
        servicio.save(update_fields=["modalidad_ejecucion"])

    ahora = timezone.now()
    oferta.transportista_vehiculo = tv
    oferta.estado = OfertaTransportista.ESTADO_ACEPTADA
    oferta.monto_actual = monto
    oferta.fecha_aceptacion = ahora
    oferta.save()

    pub.oferta_ganadora = oferta
    pub.estado = PublicacionCarga.ESTADO_ADJUDICADA
    pub.adjudicada_por = usuario
    pub.adjudicada_en = ahora
    pub.save(update_fields=["oferta_ganadora", "estado", "adjudicada_por", "adjudicada_en"])

    for otra in pub.ofertas.exclude(pk=oferta.pk).exclude(estado=OfertaTransportista.ESTADO_RECHAZADA):
        otra.estado = OfertaTransportista.ESTADO_RECHAZADA
        otra.save(update_fields=["estado", "actualizado_en"])

    for hilo in pub.hilos_negociacion.filter(tipo=HiloNegociacion.TIPO_COMPRA):
        if hilo.estado == HiloNegociacion.ESTADO_CERRADA:
            continue
        gano = hilo.transportista_id == oferta.transportista_id
        if gano:
            hilo.monto_acordado = monto
            hilo.monto_actual = monto
        hilo.estado = HiloNegociacion.ESTADO_CERRADA
        hilo.cerrado_en = ahora
        hilo.save(update_fields=["monto_acordado", "monto_actual", "estado", "cerrado_en", "actualizado_en"])
        neg._mensaje_sistema(
            hilo,
            f"Adjudicado a este transportista: S/ {monto:g}." if gano
            else "Publicación adjudicada a otro transportista.",
        )

    return prog
