from decimal import Decimal
from statistics import median

from .models import Cotizacion, ServicioHistorico
from .pricing import fallback_price_for_lead
from .similarity import score_service


def cotizar_lead(lead):
    similar_services = _find_similar_services(lead)
    if len(similar_services) >= 3:
        prices = sorted(
            service.precio_final or service.precio_cotizado
            for _score, service in similar_services
        )
        price_min = _percentile(prices, Decimal("0.20"))
        price_max = _percentile(prices, Decimal("0.80"))
        recommended = Decimal(str(median(prices))).quantize(Decimal("0.01"))
        explanation = (
            "Cotizacion calculada con mediana y percentiles de los historicos "
            "operativamente mas similares."
        )
    else:
        price_min, price_max, recommended = fallback_price_for_lead(lead)
        explanation = "Cotizacion preliminar calculada por reglas base por falta de historicos similares."

    return Cotizacion.objects.create(
        lead=lead,
        precio_min=price_min,
        precio_max=price_max,
        precio_recomendado=recommended,
        servicios_similares_encontrados=len(similar_services),
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
