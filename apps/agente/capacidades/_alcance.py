"""Resolución de objetos *dentro del alcance* de un Principal.

Cada helper devuelve el objeto o lanza `NoEncontrado` / `FueraDeAlcance`.
Nunca distingue "no existe" de "no es tuyo" para un externo — mismo 404.
"""
from apps.agente.errores import FueraDeAlcance, NoEncontrado
from apps.agente.principal import TIPO_ASESOR, TIPO_CLIENTE, TIPO_SISTEMA, TIPO_TRANSPORTISTA


def carga_para(principal, codigo):
    """El `Lead` de una carga. transportista → FueraDeAlcance (ve publicaciones, no leads)."""
    from apps.leads.models import Lead

    codigo = (codigo or "").strip().upper()
    qs = Lead.objects.select_related("cliente", "servicio_generado")
    if principal.tipo in (TIPO_ASESOR, TIPO_SISTEMA):
        pass
    elif principal.tipo == TIPO_CLIENTE:
        qs = qs.filter(cliente=principal.cliente)
    else:
        raise FueraDeAlcance("Este perfil no accede a cargas por código.")
    lead = qs.filter(codigo=codigo).first()
    if lead is None:
        raise NoEncontrado(f"No se encontró la carga {codigo}.")
    return lead


def cotizacion_para(principal, codigo):
    from apps.cotizador.models import CotizacionComercial

    qs = CotizacionComercial.objects.select_related("lead", "lead__cliente")
    if principal.tipo == TIPO_CLIENTE:
        qs = qs.filter(lead__cliente=principal.cliente)
    elif principal.tipo not in (TIPO_ASESOR, TIPO_SISTEMA):
        raise FueraDeAlcance("Este perfil no accede a cotizaciones.")
    cot = qs.filter(codigo=(codigo or "").strip()).first()
    if cot is None:
        raise NoEncontrado(f"No se encontró la cotización {codigo}.")
    return cot


def reserva_para(principal, codigo):
    from apps.servicios.models import Servicio

    qs = Servicio.objects.select_related("cliente", "lead_origen", "lead_origen__cliente")
    if principal.tipo == TIPO_CLIENTE:
        qs = qs.filter(lead_origen__cliente=principal.cliente)
    elif principal.tipo == TIPO_TRANSPORTISTA:
        qs = qs.filter(programaciones__transportista=principal.carrier).distinct()
    elif principal.tipo not in (TIPO_ASESOR, TIPO_SISTEMA):
        raise FueraDeAlcance("Este perfil no accede a reservas.")
    svc = qs.filter(codigo=(codigo or "").strip()).first()
    if svc is None:
        raise NoEncontrado(f"No se encontró la reserva {codigo}.")
    return svc


def publicacion_para(principal, codigo):
    from apps.tercerizacion.models import PublicacionCarga

    codigo = (codigo or "").strip()
    pub = (
        PublicacionCarga.objects
        .select_related("servicio", "servicio__lead_origen")
        .filter(codigo=codigo).first()
    )
    if pub is None:
        raise NoEncontrado(f"No se encontró la publicación {codigo}.")
    if principal.tipo in (TIPO_ASESOR, TIPO_SISTEMA):
        if principal.tipo == TIPO_ASESOR and not principal.ve_margen():
            raise FueraDeAlcance("Necesitás un rol con acceso a costos para ver publicaciones.")
        return pub
    if principal.tipo == TIPO_TRANSPORTISTA:
        abierta = pub.estado in ("abierta", "publicada", "con_ofertas")
        tiene_oferta = pub.ofertas.filter(transportista=principal.carrier).exists()
        if (abierta and pub.alcance == PublicacionCarga.ALCANCE_TODOS) or tiene_oferta:
            return pub
        raise NoEncontrado(f"No se encontró la publicación {codigo}.")
    raise FueraDeAlcance("Este perfil no accede a publicaciones.")


def negociacion_para(principal, hilo_id):
    from apps.tercerizacion.models import HiloNegociacion

    qs = HiloNegociacion.objects.select_related("lead", "publicacion", "contraparte", "transportista")
    if principal.tipo == TIPO_CLIENTE:
        qs = qs.filter(tipo=HiloNegociacion.TIPO_VENTA, contraparte=principal.cliente)
    elif principal.tipo == TIPO_TRANSPORTISTA:
        qs = qs.filter(tipo=HiloNegociacion.TIPO_COMPRA, transportista=principal.carrier)
    elif principal.tipo == TIPO_ASESOR and not principal.ve_margen():
        qs = qs.filter(tipo=HiloNegociacion.TIPO_VENTA)
    elif principal.tipo not in (TIPO_ASESOR, TIPO_SISTEMA):
        raise FueraDeAlcance("Este perfil no accede a negociaciones.")
    hilo = qs.filter(pk=hilo_id).first()
    if hilo is None:
        raise NoEncontrado(f"No se encontró la negociación {hilo_id}.")
    return hilo
