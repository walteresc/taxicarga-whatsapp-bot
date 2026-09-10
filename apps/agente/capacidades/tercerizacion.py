"""Capacidades de tercerización: publicar, ofertar, adjudicar."""
from apps.agente.errores import ArgInvalido, FueraDeAlcance
from apps.agente.principal import TIPO_TRANSPORTISTA
from apps.agente.registro import EFECTO_CRITICO, EFECTO_REVERSIBLE, capacidad

from . import _alcance


@capacidad("publicar_a_transportistas", perfiles=["asesor", "sistema"], efecto=EFECTO_CRITICO)
def publicar_a_transportistas(principal, publicacion_codigo, grupos=None):
    """Pasa una publicación de borrador a abierta (los transportistas la ven).
    Requiere rol con acceso a costos."""
    from apps.tercerizacion import adjudicacion as adj

    pub = _alcance.publicacion_para(principal, publicacion_codigo)
    adj.publicar_publicacion(pub, principal.user, grupos=grupos or [])
    pub.refresh_from_db()
    return {"publicacion": pub.codigo, "estado": pub.estado, "_servicio": pub.servicio}


@capacidad("registrar_oferta",
           perfiles=["asesor", "transportista", "sistema"], efecto=EFECTO_REVERSIBLE)
def registrar_oferta(principal, publicacion_codigo, monto, transportista_id=None,
                     vehiculo_id=None, nota=""):
    """Registra la oferta de un transportista sobre una publicación. El
    transportista solo puede ofertar por sí mismo."""
    from apps.tercerizacion import adjudicacion as adj
    from apps.tercerizacion.models import Transportista, TransportistaVehiculo

    pub = _alcance.publicacion_para(principal, publicacion_codigo)

    if principal.tipo == TIPO_TRANSPORTISTA:
        carrier = principal.carrier
    else:
        if not transportista_id:
            raise ArgInvalido("Indicá `transportista_id`.")
        carrier = Transportista.objects.filter(pk=transportista_id).first()
        if carrier is None:
            raise ArgInvalido("Transportista no encontrado.")

    vehiculo = None
    if vehiculo_id:
        vehiculo = carrier.vehiculos.filter(pk=vehiculo_id).first()
        if vehiculo is None:
            raise FueraDeAlcance("Ese vehículo no es del transportista.")

    if pub.modo_precio == "fijo":
        monto = pub.precio_publicado

    oferta, _hilo = adj.registrar_oferta(
        pub, monto=monto, usuario=principal.user, transportista=carrier,
        transportista_vehiculo=vehiculo, nota=(nota or "").strip(),
        canal="portal" if principal.es_externo else "crm",
    )
    return {"oferta_id": oferta.id, "publicacion": pub.codigo,
            "monto": float(oferta.monto_actual or oferta.precio_ofertado),
            "_servicio": pub.servicio}


@capacidad("adjudicar", perfiles=["asesor", "sistema"], efecto=EFECTO_CRITICO)
def adjudicar(principal, publicacion_codigo, oferta_id, vehiculo_id=None):
    """Adjudica una publicación a una oferta → crea la programación tercerizada,
    rechaza las demás ofertas y cierra los hilos de compra."""
    from apps.tercerizacion import adjudicacion as adj
    from apps.tercerizacion.models import OfertaTransportista, TransportistaVehiculo

    pub = _alcance.publicacion_para(principal, publicacion_codigo)
    oferta = OfertaTransportista.objects.filter(pk=oferta_id, publicacion=pub).first()
    if oferta is None:
        from apps.agente.errores import NoEncontrado
        raise NoEncontrado(f"La oferta {oferta_id} no es de esta publicación.")
    vehiculo = TransportistaVehiculo.objects.filter(pk=vehiculo_id).first() if vehiculo_id else None
    prog = adj.adjudicar_publicacion(pub, oferta, principal.user, transportista_vehiculo=vehiculo)
    return {"programacion_id": prog.id, "publicacion": pub.codigo, "_servicio": pub.servicio}
