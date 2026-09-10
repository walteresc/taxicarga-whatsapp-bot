"""Capacidades de negociación: abrir hilo, mandar mensaje/propuesta, responder."""
from apps.agente.errores import ArgInvalido, FueraDeAlcance
from apps.agente.principal import TIPO_ASESOR, TIPO_CLIENTE, TIPO_SISTEMA, TIPO_TRANSPORTISTA
from apps.agente.registro import EFECTO_REVERSIBLE, capacidad

from . import _alcance

_ACCIONES = {
    "aceptar": "aceptar", "accept": "aceptar",
    "contraofertar": "contraofertar", "counter": "contraofertar",
    "rechazar": "rechazar", "reject": "rechazar",
}


def _emisor_canal(principal):
    from apps.tercerizacion.models import MensajeNegociacion
    if principal.tipo == TIPO_CLIENTE:
        return MensajeNegociacion.EMISOR_CLIENTE, MensajeNegociacion.CANAL_PORTAL
    if principal.tipo == TIPO_TRANSPORTISTA:
        return MensajeNegociacion.EMISOR_TRANSPORTISTA, MensajeNegociacion.CANAL_PORTAL
    return MensajeNegociacion.EMISOR_TAXICARGA, MensajeNegociacion.CANAL_CRM


@capacidad("abrir_negociacion", perfiles=["asesor", "sistema"], efecto=EFECTO_REVERSIBLE)
def abrir_negociacion(principal, codigo, con="cliente", transportista_id=None):
    """Abre una mesa de negociación de una carga. `con`: 'cliente' (venta) o
    'transportista' (compra, requiere `transportista_id`)."""
    from apps.tercerizacion import negociacion as neg
    from apps.tercerizacion.models import HiloNegociacion, Transportista

    lead = _alcance.carga_para(principal, codigo)
    if con == "cliente":
        cot = lead.cotizaciones_comerciales.order_by("-actualizada_en").first()
        hilo, creado = neg.abrir_hilo(
            lead, HiloNegociacion.TIPO_VENTA, usuario=principal.user,
            cotizacion=cot, contraparte=lead.cliente,
        )
    elif con == "transportista":
        if not transportista_id:
            raise ArgInvalido("Indicá `transportista_id`.")
        carrier = Transportista.objects.filter(pk=transportista_id).first()
        if carrier is None:
            raise ArgInvalido("Transportista no encontrado.")
        hilo, creado = neg.abrir_hilo(
            lead, HiloNegociacion.TIPO_COMPRA, usuario=principal.user, transportista=carrier,
        )
    else:
        raise ArgInvalido("`con` debe ser 'cliente' o 'transportista'.")
    return {"hilo_id": hilo.id, "tipo": hilo.tipo, "creado": creado, "_lead": lead}


@capacidad("enviar_mensaje_negociacion",
           perfiles=["asesor", "transportista", "cliente", "sistema"], efecto=EFECTO_REVERSIBLE)
def enviar_mensaje_negociacion(principal, hilo_id, texto="", monto=None):
    """Manda un mensaje (o una propuesta si va `monto`) a una mesa de
    negociación. El emisor se deriva del perfil de quien llama."""
    from apps.tercerizacion import negociacion as neg

    if not (texto or "").strip() and monto is None:
        raise ArgInvalido("El mensaje está vacío.")
    hilo = _alcance.negociacion_para(principal, hilo_id)
    emisor, canal = _emisor_canal(principal)
    neg.publicar_mensaje(
        hilo, emisor=emisor, autor=principal.user, texto=(texto or "").strip(),
        canal=canal, propuesta_monto=monto,
    )
    hilo.refresh_from_db()
    return {"hilo_id": hilo.id, "estado": hilo.estado,
            "monto_actual": float(hilo.monto_actual) if hilo.monto_actual is not None else None,
            "_lead": hilo.lead}


@capacidad("responder_propuesta",
           perfiles=["asesor", "transportista", "cliente", "sistema"], efecto=EFECTO_REVERSIBLE)
def responder_propuesta(principal, mensaje_id, accion, monto=None, texto=""):
    """Responde una propuesta de la otra parte. `accion`: aceptar | contraofertar | rechazar."""
    from apps.tercerizacion.models import MensajeNegociacion

    acc = _ACCIONES.get((accion or "").strip().lower())
    if not acc:
        raise ArgInvalido("`accion` debe ser aceptar, contraofertar o rechazar.")
    mensaje = (
        MensajeNegociacion.objects
        .select_related("hilo", "hilo__lead").filter(pk=mensaje_id).first()
    )
    if mensaje is None:
        from apps.agente.errores import NoEncontrado
        raise NoEncontrado(f"No se encontró la propuesta {mensaje_id}.")
    # el hilo tiene que estar en el alcance del principal
    _alcance.negociacion_para(principal, mensaje.hilo_id)
    # quien responde debe ser la contraparte de quien propuso
    yo, _ = _emisor_canal(principal)
    if mensaje.emisor == yo:
        raise FueraDeAlcance("No podés responder tu propia propuesta.")
    if principal.es_externo and mensaje.emisor != MensajeNegociacion.EMISOR_TAXICARGA:
        raise FueraDeAlcance("Solo podés responder propuestas de Lima Express.")

    from apps.tercerizacion import negociacion as neg
    neg.responder_propuesta(mensaje, acc, usuario=principal.user, monto=monto,
                            texto=(texto or "").strip())
    mensaje.hilo.refresh_from_db()
    return {"hilo_id": mensaje.hilo_id, "estado": mensaje.hilo.estado,
            "monto_acordado": float(mensaje.hilo.monto_acordado)
            if mensaje.hilo.monto_acordado is not None else None,
            "_lead": mensaje.hilo.lead}
