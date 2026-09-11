import logging
from decimal import Decimal
from statistics import median

from django.utils import timezone

from apps.leads.models import Lead
from .models import Cotizacion, ServicioHistorico
from .pricing import fallback_price_for_lead
from .similarity import score_service

logger = logging.getLogger(__name__)


# Categorías que el motor determinístico sabe cotizar razonablemente hoy
# (históricos de mudanzas dentro de Lima). El resto → cotización manual / negociación.
_CATEGORIAS_MOTOR = {"", "mudanza"}


def _cotizar_carga_parcial(lead):
    """Carga nacional PARCIAL/consolidada: el transportista comparte el camión
    con otra carga suya, así que cotizamos por peso × tabla de tarifas (no por
    camión dedicado) — ver `apps.tercerizacion.services.resolver_tarifa_parcial`.
    Sin tabla de tarifas para ese destino/peso → cotización manual (asesor)."""
    from apps.tercerizacion.services import resolver_tarifa_parcial

    tarifa = resolver_tarifa_parcial(lead.distrito_destino, lead.peso_carga_kg)
    if tarifa is None:
        return Cotizacion.objects.create(
            lead=lead,
            precio_min=Decimal(0), precio_max=Decimal(0), precio_recomendado=Decimal(0),
            servicios_similares_encontrados=0, confianza=20, modo=Cotizacion.MODO_MANUAL,
            explicacion="Carga nacional parcial sin tarifa cargada para ese destino/peso: "
                        "requiere confirmación de un asesor.",
        )
    precio = tarifa["precio"]
    return Cotizacion.objects.create(
        lead=lead,
        precio_min=precio, precio_max=precio, precio_recomendado=precio,
        servicios_similares_encontrados=0, confianza=70, modo=Cotizacion.MODO_AUTOMATICO,
        dias_estimados=tarifa["dias_estimados"],
        explicacion=f"Carga parcial/consolidada por tabla de tarifas: S/ {precio} · "
                    f"llega en {tarifa['dias_estimados']} días hábiles aprox. "
                    "(comparte camión con otra carga del transportista).",
    )


def cotizar_lead(lead):
    if lead.es_interprovincial and lead.modo_carga == Lead.MODO_CARGA_PARCIAL:
        return _cotizar_carga_parcial(lead)
    similar_services = _find_similar_services(lead)
    n = len(similar_services)
    if n >= 3:
        prices = sorted(
            service.precio_final or service.precio_cotizado
            for _score, service in similar_services
        )
        filtered = _filter_outliers(prices)
        if len(filtered) >= 3:
            prices = filtered
        price_min = _percentile(prices, Decimal("0.20"))
        price_max = _percentile(prices, Decimal("0.80"))
        recommended = Decimal(str(median(prices))).quantize(Decimal("0.01"))
        explanation = (
            "Cotizacion calculada con mediana y percentiles de los historicos "
            "operativamente mas similares."
        )
        confianza = min(95, 55 + n * 4)
    else:
        price_min, price_max, recommended = fallback_price_for_lead(lead)
        explanation = "Cotizacion preliminar calculada por reglas base por falta de historicos similares."
        confianza = 35

    # El motor no cubre bien: interprovincial, o carga que no es mudanza.
    fuera_de_alcance = bool(getattr(lead, "es_interprovincial", False)) or (
        (getattr(lead, "categoria_carga", "") or "") not in _CATEGORIAS_MOTOR
    )
    if fuera_de_alcance:
        confianza = min(confianza, 25)
        modo = Cotizacion.MODO_MANUAL
        explanation += " · Fuera del alcance del cotizador automático: requiere confirmación de un asesor."
    else:
        modo = Cotizacion.MODO_AUTOMATICO if confianza >= 40 else Cotizacion.MODO_MANUAL

    return Cotizacion.objects.create(
        lead=lead,
        precio_min=price_min,
        precio_max=price_max,
        precio_recomendado=recommended,
        servicios_similares_encontrados=n,
        confianza=confianza,
        modo=modo,
        explicacion=explanation,
    )


def _find_similar_services(lead):
    candidates = ServicioHistorico.objects.filter(
        cerrado=True,
        precio_final__gte=50,
        precio_final__lte=10000,
        tipo_servicio__iexact=lead.tipo_servicio,
    )
    scored = sorted(
        ((score_service(lead, service), service) for service in candidates),
        key=lambda item: item[0],
        reverse=True,
    )
    if not scored:
        return []
    best_score = scored[0][0]
    minimum_score = max(8, best_score - 3)
    return [item for item in scored if item[0] >= minimum_score][:20]


def _percentile(values, percentile):
    if len(values) == 1:
        return values[0].quantize(Decimal("0.01"))
    position = Decimal(len(values) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - Decimal(lower)
    result = values[lower] + (values[upper] - values[lower]) * fraction
    return result.quantize(Decimal("0.01"))


def _filter_outliers(prices):
    if len(prices) < 4:
        return prices
    q1 = _percentile(prices, Decimal("0.25"))
    q3 = _percentile(prices, Decimal("0.75"))
    iqr = q3 - q1
    lower = q1 - iqr * Decimal("1.5")
    upper = q3 + iqr * Decimal("1.5")
    return [p for p in prices if lower <= p <= upper]


def sugerir_precio_cierre(lead):
    """Para una negociación de venta en curso: junta el rango técnico (histórico),
    la contraoferta del cliente, nuestra última oferta y el monto sobre la mesa,
    y propone un precio de cierre. Es una sugerencia — no escribe nada.
    """
    similars = _find_similar_services(lead)
    n = len(similars)
    if n >= 3:
        prices = sorted(
            (s.precio_final or s.precio_cotizado) for _sc, s in similars
        )
        filtered = _filter_outliers(prices)
        if len(filtered) >= 3:
            prices = filtered
        piso = _percentile(prices, Decimal("0.20"))
        techo = _percentile(prices, Decimal("0.80"))
        centro = Decimal(str(median(prices))).quantize(Decimal("0.01"))
    else:
        piso, techo, centro = fallback_price_for_lead(lead)

    cot = lead.cotizaciones_comerciales.order_by("-actualizada_en").first()
    contraoferta = cot.precio_cliente if cot and cot.precio_cliente is not None else None
    rev = cot.revisiones.order_by("-numero").first() if cot else None
    nuestra_oferta = (
        rev.precio_final if rev
        else (lead.precio_recomendado if lead.precio_recomendado is not None else None)
    )
    hilo = (
        lead.hilos_negociacion.filter(tipo="venta").order_by("-actualizado_en").first()
    )
    monto_mesa = hilo.monto_actual if hilo and hilo.monto_actual is not None else None

    if contraoferta is not None and nuestra_oferta is not None:
        sugerencia = ((Decimal(contraoferta) + Decimal(nuestra_oferta)) / 2).quantize(Decimal("0.01"))
        motivo = "Punto medio entre la contraoferta del cliente y nuestra última oferta."
    else:
        candidatos = [x for x in (monto_mesa, nuestra_oferta, contraoferta) if x is not None]
        sugerencia = Decimal(str(min(candidatos))) if candidatos else centro
        motivo = "Sin contraoferta cerrada: se toma el monto más bajo sobre la mesa (o el centro técnico)."

    if sugerencia < piso:
        sugerencia = piso
        motivo += " Ajustada al piso técnico."

    return {
        "sugerencia": float(sugerencia),
        "piso_tecnico": float(piso),
        "techo_tecnico": float(techo),
        "centro_tecnico": float(centro),
        "contraoferta_cliente": float(contraoferta) if contraoferta is not None else None,
        "nuestra_oferta_actual": float(nuestra_oferta) if nuestra_oferta is not None else None,
        "monto_en_negociacion": float(monto_mesa) if monto_mesa is not None else None,
        "n_similares": n,
        "motivo": motivo,
    }


def crear_servicio_historico_desde_lead(lead):
    if lead.estado != Lead.CERRADO:
        logger.info(
            "[Learning] lead_id=%s accion=omitido razon=estado_no_cerrado",
            lead.id,
        )
        return None

    if not lead.tipo_servicio:
        logger.info(
            "[Learning] lead_id=%s accion=omitido razon=sin_tipo_servicio",
            lead.id,
        )
        return None

    if not lead.distrito_origen or not lead.distrito_destino:
        logger.info(
            "[Learning] lead_id=%s accion=omitido razon=sin_origen_destino",
            lead.id,
        )
        return None

    precio_final = lead.precio_final
    precio_cotizado = lead.precio_recomendado or Decimal("0.00")
    if not precio_final and not precio_cotizado:
        logger.info(
            "[Learning] lead_id=%s accion=omitido razon=sin_precio_valido",
            lead.id,
        )
        return None

    servicio_fecha = lead.fecha_servicio or (
        lead.fecha_cierre.date() if lead.fecha_cierre else timezone.localdate()
    )

    observaciones_parts = []
    if lead.vendedor_asignado:
        observaciones_parts.append(
            f"asesor: {lead.vendedor_asignado.get_full_name() or lead.vendedor_asignado.username}"
        )
    if lead.whatsapp_channel:
        observaciones_parts.append(f"canal: {lead.whatsapp_channel.nombre}")

    defaults = {
        "fuente": "lead",
        "referencia_externa": str(lead.id),
        "fecha": servicio_fecha,
        "tipo_servicio": lead.tipo_servicio,
        "distrito_origen": lead.distrito_origen,
        "distrito_destino": lead.distrito_destino,
        "piso_origen": lead.piso_origen,
        "piso_destino": lead.piso_destino,
        "ascensor_origen": lead.ascensor_origen,
        "ascensor_destino": lead.ascensor_destino,
        "lista_objetos": lead.lista_objetos,
        "objetos_pesados": lead.objetos_pesados,
        "modalidad_servicio": lead.modalidad_servicio,
        "requiere_desarmado": lead.requiere_desarmado,
        "acceso_origen": lead.acceso_origen,
        "acceso_destino": lead.acceso_destino,
        "camion_llega_origen": lead.camion_llega_origen,
        "camion_llega_destino": lead.camion_llega_destino,
        "distancia_carga_origen_m": lead.distancia_carga_origen_m,
        "distancia_carga_destino_m": lead.distancia_carga_destino_m,
        "peso_carga_kg": lead.peso_carga_kg,
        "volumen_carga_m3": lead.volumen_carga_m3,
        "camion_usado": lead.tipo_camion,
        "capacidad_camion": lead.capacidad_camion,
        "ayudantes": 1 if lead.incluye_personal_carga else 0,
        "precio_cotizado": precio_cotizado,
        "precio_final": precio_final,
        "cerrado": True,
        "observaciones": "; ".join(observaciones_parts),
    }

    historico, created = ServicioHistorico.objects.update_or_create(
        lead_origen=lead,
        defaults=defaults,
    )

    accion = "creado" if created else "actualizado"
    logger.info(
        "[Learning] lead_id=%s historico_id=%s accion=%s",
        lead.id, historico.id, accion,
    )
    return historico
