"""Capacidades de precio — solo lectura, no escriben nada."""
from apps.agente.registro import EFECTO_LECTURA, capacidad

from . import _alcance


@capacidad("calcular_precio", perfiles=["asesor", "cliente", "sistema"], efecto=EFECTO_LECTURA,
           params={"codigo": {"description": "Código de la carga (CRG-NNNN)."}})
def calcular_precio(principal, codigo):
    """Precio estimado de una carga con el motor determinista. Devuelve un número
    o `{modo: 'manual'}` cuando el motor no cubre (interprovincial, no-mudanza)."""
    from apps.cotizador.models import Cotizacion
    from apps.cotizador.services import cotizar_lead

    lead = _alcance.carga_para(principal, codigo)
    tecnica = lead.cotizaciones.order_by("-fecha_creacion").first() or cotizar_lead(lead)
    if tecnica.modo == Cotizacion.MODO_MANUAL:
        return {
            "modo": "manual",
            "motivo": tecnica.explicacion,
            "confianza": tecnica.confianza,
            "_lead": lead,
        }
    return {
        "modo": "automatico",
        "recomendado": float(tecnica.precio_recomendado),
        "min": float(tecnica.precio_min),
        "max": float(tecnica.precio_max),
        "confianza": tecnica.confianza,
        "_lead": lead,
    }


@capacidad("sugerir_precio_cierre", perfiles=["asesor", "sistema"], efecto=EFECTO_LECTURA,
           params={"codigo": {"description": "Código de la carga en negociación."}})
def sugerir_precio_cierre(principal, codigo):
    """Para una negociación de venta en curso: rango técnico + contraoferta del
    cliente + nuestra oferta + monto sobre la mesa → precio de cierre sugerido."""
    from apps.cotizador.services import sugerir_precio_cierre as _calc

    lead = _alcance.carga_para(principal, codigo)
    return {**_calc(lead), "_lead": lead}
