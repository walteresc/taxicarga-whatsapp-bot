"""Capacidades de lectura — no cambian nada. `efecto="lectura"`."""
from apps.agente.errores import FueraDeAlcance
from apps.agente.principal import (
    TIPO_ASESOR, TIPO_CLIENTE, TIPO_SISTEMA, TIPO_TRANSPORTISTA,
)
from apps.agente.registro import EFECTO_LECTURA, capacidad

from . import _alcance

_TODOS = ["asesor", "transportista", "cliente", "sistema"]


@capacidad("ver_carga", perfiles=["asesor", "cliente", "transportista", "sistema"], efecto=EFECTO_LECTURA)
def ver_carga(principal, codigo):
    """Datos de una carga. El cliente ve la suya completa; el transportista ve la
    versión con privacidad (sin datos del cliente ni precio de venta)."""
    if principal.tipo == TIPO_TRANSPORTISTA:
        from apps.tercerizacion.api.portal_views import _safe_load
        pub = _alcance.publicacion_para(principal, codigo)
        oferta = pub.ofertas.filter(transportista=principal.carrier).first()
        return {**_safe_load(pub, oferta), "_lead": pub.servicio.lead_origen}
    from apps.clientes.api.portal_cliente_views import load_detail
    lead = _alcance.carga_para(principal, codigo)
    return {**load_detail(lead), "_lead": lead}


@capacidad("ver_cotizacion", perfiles=["asesor", "cliente", "sistema"], efecto=EFECTO_LECTURA)
def ver_cotizacion(principal, codigo):
    """La cotización comercial de una carga: precio actual, revisiones, estado."""
    from apps.cotizador.api.shapes import quote_detail
    cot = _alcance.cotizacion_para(principal, codigo)
    return {**quote_detail(cot), "_lead": cot.lead}


@capacidad("ver_reserva", perfiles=["asesor", "cliente", "transportista", "sistema"], efecto=EFECTO_LECTURA)
def ver_reserva(principal, codigo):
    """Una reserva (servicio confirmado): fecha, estado, asignación."""
    from apps.cotizador.api.shapes import booking_item
    svc = _alcance.reserva_para(principal, codigo)
    return {**booking_item(svc), "_servicio": svc, "_lead": svc.lead_origen}


@capacidad("ver_publicacion", perfiles=["asesor", "sistema"], efecto=EFECTO_LECTURA)
def ver_publicacion(principal, codigo):
    """Una publicación a transportistas: ofertas, estado, costo objetivo."""
    from apps.tercerizacion.api.publicaciones_views import publication_detail
    pub = _alcance.publicacion_para(principal, codigo)
    return {**publication_detail(pub), "_servicio": pub.servicio}


@capacidad("ver_negociacion", perfiles=_TODOS, efecto=EFECTO_LECTURA)
def ver_negociacion(principal, hilo_id):
    """Una mesa de negociación con sus mensajes. El externo solo ve su lado; sin margen."""
    hilo = _alcance.negociacion_para(principal, hilo_id)
    if principal.tipo == TIPO_TRANSPORTISTA:
        from apps.tercerizacion.api.portal_views import _carrier_hilo
        return {**_carrier_hilo(hilo, with_messages=True), "_lead": hilo.lead}
    if principal.tipo == TIPO_CLIENTE:
        from apps.clientes.api.portal_cliente_views import _cust_msg
        from apps.tercerizacion.models import MensajeNegociacion
        return {
            "code": hilo.lead.codigo,
            "state": hilo.estado,
            "currentAmount": float(hilo.monto_actual) if hilo.monto_actual is not None else None,
            "messages": [
                _cust_msg(m) for m in hilo.mensajes.order_by("creado_en")
                if m.emisor != MensajeNegociacion.EMISOR_TRANSPORTISTA
            ],
            "_lead": hilo.lead,
        }
    from apps.tercerizacion.api.negociacion_views import hilo_detail
    return {**hilo_detail(hilo, ver_margen=principal.ve_margen()), "_lead": hilo.lead}


@capacidad("cargas_del_cliente", perfiles=["cliente", "asesor", "sistema"], efecto=EFECTO_LECTURA)
def cargas_del_cliente(principal, cliente_id=None):
    """Lista de cargas de un cliente. El cliente ve solo las suyas; el asesor pasa `cliente_id`."""
    from apps.clientes.api.portal_cliente_views import load_item
    from apps.clientes.models import Cliente
    from apps.leads.models import Lead

    if principal.tipo == TIPO_CLIENTE:
        cli = principal.cliente
    else:
        if not cliente_id:
            raise FueraDeAlcance("Indicá `cliente_id`.")
        cli = Cliente.objects.filter(pk=cliente_id).first()
        if cli is None:
            raise FueraDeAlcance("Cliente no encontrado.")
    leads = (
        Lead.objects.filter(cliente=cli).exclude(estado=Lead.PERDIDO)
        .select_related("servicio_generado").order_by("-fecha_creacion")[:50]
    )
    return {"resultados": [load_item(x) for x in leads]}


@capacidad("cargas_disponibles", perfiles=["transportista", "sistema"], efecto=EFECTO_LECTURA)
def cargas_disponibles(principal):
    """Cargas que un transportista puede ofertar (con privacidad)."""
    from apps.tercerizacion.api.portal_views import _safe_load
    from apps.tercerizacion.models import OfertaTransportista, PublicacionCarga

    if principal.tipo == TIPO_SISTEMA:
        raise FueraDeAlcance("Indicá el transportista (perfil transportista).")
    mis = {
        o.publicacion_id: o
        for o in OfertaTransportista.objects.filter(transportista=principal.carrier)
    }
    pubs = (
        PublicacionCarga.objects
        .filter(estado__in=("abierta", "publicada", "con_ofertas"))
        .select_related("servicio").order_by("-creado_en")
    )
    out = []
    for pub in pubs:
        if pub.alcance == PublicacionCarga.ALCANCE_TODOS or pub.id in mis:
            out.append(_safe_load(pub, mis.get(pub.id)))
    return {"resultados": out}


@capacidad("estado_y_seguimiento", perfiles=_TODOS, efecto=EFECTO_LECTURA)
def estado_y_seguimiento(principal, codigo):
    """Estado de alto nivel de una carga + seguimiento del servicio (transportista/placa)."""
    from apps.clientes.api.portal_cliente_views import _load_status, _tracking

    if principal.tipo == TIPO_TRANSPORTISTA:
        svc = _alcance.reserva_para(principal, codigo)
        lead = svc.lead_origen
    else:
        lead = _alcance.carga_para(principal, codigo)
    return {
        "codigo": codigo,
        "estado": _load_status(lead),
        "seguimiento": _tracking(lead),
        "_lead": lead,
    }


@capacidad("margen", perfiles=["asesor", "sistema"], efecto=EFECTO_LECTURA)
def margen(principal, codigo):
    """Margen en vivo de una carga (venta − costo de tercerización). Solo roles de margen."""
    from apps.tercerizacion.negociacion import margen_en_vivo

    if principal.tipo == TIPO_ASESOR and not principal.ve_margen():
        raise FueraDeAlcance("Tu rol no ve márgenes.")
    lead = _alcance.carga_para(principal, codigo)
    return {**margen_en_vivo(lead), "_lead": lead}
