"""API v2 · Publicaciones a transportistas (F3).

    GET  /api/v2/publications/                   lista (filtros: state, search)
    GET  /api/v2/publications/<pk>/              detalle + ofertas + servicio
    POST /api/v2/publications/<pk>/publish       {groups?}
    POST /api/v2/publications/<pk>/offers        {carrierId, vehicleId?, amount, note?}
    POST /api/v2/publications/<pk>/award         {offerId, vehicleId?}
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.pagination import StandardPagination
from apps.api.permissions import HasAnyRole
from apps.tercerizacion import adjudicacion as adj
from apps.tercerizacion.models import (
    OfertaTransportista, PublicacionCarga, Transportista, TransportistaVehiculo,
)

# Publicaciones exponen el costo de tercerización → mismo criterio que el margen.
_ROLES = ("Administrador", "Gerencia", "Supervisor", "Despacho")

_STATE_EN = {
    "borrador": "draft", "abierta": "open", "publicada": "open",
    "con_ofertas": "with_offers", "adjudicada": "awarded",
    "cancelada": "cancelled", "vencida": "expired",
}
_STATE_ES = {"draft": "borrador", "open": "abierta", "with_offers": "con_ofertas",
             "awarded": "adjudicada", "cancelled": "cancelada", "expired": "vencida"}
_PRICE_MODE_EN = {"fijo": "fixed", "referencial": "reference", "abierto": "open"}
_OFFER_STATE_EN = {
    "pendiente": "pending", "contraoferta_taxicarga": "countered_us",
    "contraoferta_transportista": "countered_carrier", "aceptada": "accepted",
    "rechazada": "rejected", "retirada": "withdrawn", "vencida": "expired",
}


def _d(dt):
    return dt.isoformat() if dt else None


def _num(v):
    return float(v) if v is not None else None


def _amount(raw, label="monto"):
    if raw in (None, ""):
        raise ValidationError({label: "Ingresá un monto."})
    try:
        v = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        raise ValidationError({label: "Monto no válido."})
    if v <= 0:
        raise ValidationError({label: "El monto debe ser mayor que cero."})
    return v


def publication_item(pub):
    s = pub.servicio
    return {
        "id": pub.id,
        "code": pub.codigo,
        "bookingCode": s.codigo,
        "leadId": s.lead_origen_id,
        "route": f"{s.distrito_origen or '?'} → {s.distrito_destino or '?'}",
        "date": _d(s.fecha_servicio),
        "state": _STATE_EN.get(pub.estado, pub.estado),
        "priceMode": _PRICE_MODE_EN.get(pub.modo_precio, pub.modo_precio),
        "publishedPrice": _num(pub.precio_publicado),
        "offerCount": pub.ofertas.exclude(estado="rechazada").count(),
        "publishedAt": _d(pub.publicada_en),
        "awardedAt": _d(pub.adjudicada_en),
        "createdAt": _d(pub.creado_en),
        # El cliente puede marcar una oferta (o el precio directo) como
        # preferida desde el Portal Cliente — es solo una señal, el asesor
        # sigue siendo quien adjudica de verdad. Ver apps/clientes/api/
        # portal_cliente_views.py::CustomerLoadPreferOfferView.
        "clientPreferredOfferId": pub.oferta_preferida_cliente_id,
        "clientPrefersDirect": pub.prefiere_directo_taxicarga,
        "clientPreferenceAt": _d(pub.preferencia_cliente_en),
    }


def offer_item(o):
    carrier = o.transportista
    return {
        "id": o.id,
        "carrierId": o.transportista_id,
        "carrierName": carrier.nombre if carrier else (o.cliente.nombre if o.cliente else "Contacto WhatsApp"),
        "affiliated": o.transportista_id is not None,
        "vehicleId": o.transportista_vehiculo_id,
        "vehiclePlate": o.transportista_vehiculo.placa if o.transportista_vehiculo_id else None,
        "firstAmount": _num(o.precio_ofertado),
        "currentAmount": _num(o.monto_actual or o.precio_ofertado),
        "state": _OFFER_STATE_EN.get(o.estado, o.estado),
        "acceptedAt": _d(o.fecha_aceptacion),
        "createdAt": _d(o.creado_en),
    }


def publication_detail(pub):
    out = publication_item(pub)
    s = pub.servicio
    out["service"] = {
        "code": s.codigo,
        "origin": s.distrito_origen,
        "destination": s.distrito_destino,
        "date": _d(s.fecha_servicio),
        "schedule": s.horario_servicio,
        "cargo": s.detalle_carga,
        "salePrice": _num(s.precio),
    }
    out["publishedText"] = pub.texto_publicado
    out["groups"] = pub.grupos_publicados or []
    out["offers"] = [offer_item(o) for o in pub.ofertas.select_related(
        "transportista", "transportista_vehiculo", "cliente",
    ).order_by("monto_actual", "creado_en")]
    out["winningOfferId"] = pub.oferta_ganadora_id

    # Rentabilidad: costo (mejor oferta viva o la adjudicada) → precio al cliente
    # → comisión de la plataforma (tabla por tramos y categoría de la carga).
    from apps.tercerizacion.services import (
        _categoria_de, desglose_comision, evaluar_margen_tercerizacion,
        precio_cliente_sugerido,
    )
    cat = _categoria_de(s)
    vivas = [o for o in pub.ofertas.all() if o.estado != "rechazada"]
    if pub.oferta_ganadora_id:
        best = pub.oferta_ganadora
    else:
        best = min(vivas, key=lambda o: o.monto_actual or o.precio_ofertado or 1e12, default=None)
    best_cost = (best.monto_actual or best.precio_ofertado) if best else None
    suggested = precio_cliente_sugerido(best_cost, cat)
    out["economics"] = {
        "category": cat,
        "bestOfferCost": _num(best_cost),
        "suggestedClientPrice": _num(suggested),
        "currentClientPrice": _num(s.precio),
        "margin": evaluar_margen_tercerizacion(s.precio, best_cost),
        "commission": desglose_comision(s.precio or suggested, best_cost, cat),
    }
    return out


class _Base(APIView):
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_exception_handler(self):
        return api_exception_handler


_PUB_QS = PublicacionCarga.objects.select_related(
    "servicio", "servicio__lead_origen", "oferta_ganadora",
).prefetch_related("ofertas")


class OutsourcingSettingsView(_Base):
    """GET/PATCH /api/v2/outsourcing/settings — política y rentabilidad de tercerización.

        {"autoDeriveInterprovincial": bool, "markupPercent": number}

    `autoDeriveInterprovincial`: con el flag activo una carga interprovincial con
    datos completos se publica sola a los transportistas (precio abierto).
    `markupPercent`: recargo sobre el costo del transportista para fijar el
    precio al cliente cuando la carga no tiene cotización propia.
    """

    def _payload(self, cfg):
        return {
            "autoDeriveInterprovincial": cfg.derivar_interprovincial_auto,
            "deriveOnReject": cfg.derivar_al_rechazar_precio,
            "deriveOffHours": cfg.derivar_fuera_horario,
            "markupPercent": float(cfg.markup_tercerizacion_porcentaje),
            "minCommissionableAmount": float(cfg.monto_minimo_comisionable),
            "radiusLocalKm": float(cfg.radio_local_km),
            "refLat": float(cfg.lat_referencia_local),
            "refLng": float(cfg.lng_referencia_local),
        }

    def get(self, request):
        from apps.servicios.models import ConfiguracionOperaciones
        return Response(self._payload(ConfiguracionOperaciones.get_solo()))

    def patch(self, request):
        from apps.servicios.models import ConfiguracionOperaciones
        cfg = ConfiguracionOperaciones.get_solo()
        campos = []
        if "autoDeriveInterprovincial" in request.data:
            cfg.derivar_interprovincial_auto = bool(request.data["autoDeriveInterprovincial"])
            campos.append("derivar_interprovincial_auto")
        if "deriveOnReject" in request.data:
            cfg.derivar_al_rechazar_precio = bool(request.data["deriveOnReject"])
            campos.append("derivar_al_rechazar_precio")
        if "deriveOffHours" in request.data:
            cfg.derivar_fuera_horario = bool(request.data["deriveOffHours"])
            campos.append("derivar_fuera_horario")
        if "markupPercent" in request.data:
            try:
                pct = Decimal(str(request.data["markupPercent"]))
            except (InvalidOperation, TypeError):
                raise ValidationError({"markupPercent": "Porcentaje no válido."})
            if not (Decimal(0) <= pct <= Decimal(200)):
                raise ValidationError({"markupPercent": "Debe estar entre 0 y 200."})
            cfg.markup_tercerizacion_porcentaje = pct
            campos.append("markup_tercerizacion_porcentaje")
        if "minCommissionableAmount" in request.data:
            try:
                monto = Decimal(str(request.data["minCommissionableAmount"]))
            except (InvalidOperation, TypeError):
                raise ValidationError({"minCommissionableAmount": "Monto no válido."})
            if monto < 0:
                raise ValidationError({"minCommissionableAmount": "No puede ser negativo."})
            cfg.monto_minimo_comisionable = monto
            campos.append("monto_minimo_comisionable")
        if "radiusLocalKm" in request.data:
            try:
                radio = Decimal(str(request.data["radiusLocalKm"]))
            except (InvalidOperation, TypeError):
                raise ValidationError({"radiusLocalKm": "Radio no válido."})
            if not (Decimal(0) < radio <= Decimal(2000)):
                raise ValidationError({"radiusLocalKm": "Debe estar entre 0 y 2000 km."})
            cfg.radio_local_km = radio
            campos.append("radio_local_km")
        if "refLat" in request.data and "refLng" in request.data:
            try:
                lat = Decimal(str(request.data["refLat"]))
                lng = Decimal(str(request.data["refLng"]))
            except (InvalidOperation, TypeError):
                raise ValidationError({"refLat": "Coordenadas no válidas."})
            cfg.lat_referencia_local = lat
            cfg.lng_referencia_local = lng
            campos += ["lat_referencia_local", "lng_referencia_local"]
        if campos:
            cfg.save(update_fields=campos + ["actualizado_en"])
        return Response(self._payload(cfg))


# Las tasas de comisión son una decisión de tarifa/finanzas.
_ROLES_COMISION = ("Administrador", "Gerencia", "Finanzas")


def _tier_item(t):
    return {
        "id": t.id,
        "category": t.categoria,
        "from": float(t.monto_desde),
        "to": float(t.monto_hasta) if t.monto_hasta is not None else None,
        "percent": float(t.porcentaje),
        "active": t.activo,
    }


def _tier_from_body(data, t):
    from apps.leads.models import Lead
    cats = {c for c, _ in Lead.CATEGORIAS_CARGA} | {""}
    if "category" in data:
        cat = (data["category"] or "").strip()
        if cat not in cats:
            raise ValidationError({"category": "Categoría de carga no válida."})
        t.categoria = cat
    if "from" in data:
        try:
            t.monto_desde = Decimal(str(data["from"]))
        except (InvalidOperation, TypeError):
            raise ValidationError({"from": "Monto no válido."})
        if t.monto_desde < 0:
            raise ValidationError({"from": "No puede ser negativo."})
    if "to" in data:
        if data["to"] in (None, ""):
            t.monto_hasta = None
        else:
            try:
                t.monto_hasta = Decimal(str(data["to"]))
            except (InvalidOperation, TypeError):
                raise ValidationError({"to": "Monto no válido."})
    if "percent" in data:
        try:
            t.porcentaje = Decimal(str(data["percent"]))
        except (InvalidOperation, TypeError):
            raise ValidationError({"percent": "Porcentaje no válido."})
        if not (Decimal(0) <= t.porcentaje < Decimal(100)):
            raise ValidationError({"percent": "Debe estar entre 0 y 100."})
    if "active" in data:
        t.activo = bool(data["active"])
    if t.monto_hasta is not None and t.monto_hasta <= t.monto_desde:
        raise ValidationError({"to": "El 'hasta' debe ser mayor que el 'desde'."})
    return t


class CommissionTiersView(_Base):
    """GET todos los tramos de comisión + las categorías disponibles; POST crea uno.

    Modelo: la comisión de la plataforma sobre un servicio tercerizado baja por
    tramos de monto y puede ser más alta por categoría (p. ej. mudanzas).
    """
    permission_classes = [HasAnyRole(*_ROLES_COMISION)]

    def get(self, request):
        from apps.leads.models import Lead
        from apps.tercerizacion.models import TramoComision
        return Response({
            "tiers": [_tier_item(t) for t in TramoComision.objects.all()],
            "categories": [{"value": c, "label": l} for c, l in Lead.CATEGORIAS_CARGA],
        })

    def post(self, request):
        from apps.tercerizacion.models import TramoComision
        t = _tier_from_body(request.data, TramoComision())
        if "percent" not in request.data:
            raise ValidationError({"percent": "Requerido."})
        t.save()
        return Response(_tier_item(t), status=201)


class CommissionTierDetailView(_Base):
    permission_classes = [HasAnyRole(*_ROLES_COMISION)]

    def patch(self, request, pk):
        from apps.tercerizacion.models import TramoComision
        t = get_object_or_404(TramoComision, pk=pk)
        _tier_from_body(request.data, t)
        t.save()
        return Response(_tier_item(t))

    def delete(self, request, pk):
        from apps.tercerizacion.models import TramoComision
        get_object_or_404(TramoComision, pk=pk).delete()
        return Response(status=204)


def _partial_tariff_item(t):
    return {
        "id": t.id,
        "destination": t.destino,
        "modality": t.modalidad,
        "weightFrom": float(t.peso_desde_kg),
        "weightTo": float(t.peso_hasta_kg) if t.peso_hasta_kg is not None else None,
        "pricePerKg": float(t.precio_por_kg),
        "pricePerKgMax": float(t.precio_por_kg_max) if t.precio_por_kg_max is not None else None,
        "pricePerM3": float(t.precio_por_m3) if t.precio_por_m3 is not None else None,
        "pricePerM3Max": float(t.precio_por_m3_max) if t.precio_por_m3_max is not None else None,
        "minAmount": float(t.monto_minimo),
        "daysEstimated": t.dias_estimados,
        "active": t.activo,
    }


def _partial_tariff_from_body(data, t):
    if "destination" in data:
        t.destino = (data["destination"] or "").strip()
    if "modality" in data:
        from apps.leads.models import Lead

        modalidad = (data["modality"] or "").strip()
        if modalidad not in dict(Lead.MODOS_CARGA):
            raise ValidationError({"modality": "Modalidad inválida."})
        t.modalidad = modalidad
    if "weightFrom" in data:
        try:
            t.peso_desde_kg = Decimal(str(data["weightFrom"]))
        except (InvalidOperation, TypeError):
            raise ValidationError({"weightFrom": "Peso no válido."})
        if t.peso_desde_kg < 0:
            raise ValidationError({"weightFrom": "No puede ser negativo."})
    if "weightTo" in data:
        if data["weightTo"] in (None, ""):
            t.peso_hasta_kg = None
        else:
            try:
                t.peso_hasta_kg = Decimal(str(data["weightTo"]))
            except (InvalidOperation, TypeError):
                raise ValidationError({"weightTo": "Peso no válido."})
    if "pricePerKg" in data:
        try:
            t.precio_por_kg = Decimal(str(data["pricePerKg"]))
        except (InvalidOperation, TypeError):
            raise ValidationError({"pricePerKg": "Precio no válido."})
        if t.precio_por_kg <= 0:
            raise ValidationError({"pricePerKg": "Debe ser mayor que cero."})
    if "pricePerKgMax" in data:
        if data["pricePerKgMax"] in (None, ""):
            t.precio_por_kg_max = None
        else:
            try:
                t.precio_por_kg_max = Decimal(str(data["pricePerKgMax"]))
            except (InvalidOperation, TypeError):
                raise ValidationError({"pricePerKgMax": "Precio no válido."})
            if t.precio_por_kg_max < 0:
                raise ValidationError({"pricePerKgMax": "No puede ser negativo."})
    if "pricePerM3" in data:
        if data["pricePerM3"] in (None, ""):
            t.precio_por_m3 = None
        else:
            try:
                t.precio_por_m3 = Decimal(str(data["pricePerM3"]))
            except (InvalidOperation, TypeError):
                raise ValidationError({"pricePerM3": "Precio no válido."})
            if t.precio_por_m3 < 0:
                raise ValidationError({"pricePerM3": "No puede ser negativo."})
    if "pricePerM3Max" in data:
        if data["pricePerM3Max"] in (None, ""):
            t.precio_por_m3_max = None
        else:
            try:
                t.precio_por_m3_max = Decimal(str(data["pricePerM3Max"]))
            except (InvalidOperation, TypeError):
                raise ValidationError({"pricePerM3Max": "Precio no válido."})
            if t.precio_por_m3_max < 0:
                raise ValidationError({"pricePerM3Max": "No puede ser negativo."})
    if "minAmount" in data:
        try:
            t.monto_minimo = Decimal(str(data["minAmount"]))
        except (InvalidOperation, TypeError):
            raise ValidationError({"minAmount": "Monto no válido."})
        if t.monto_minimo < 0:
            raise ValidationError({"minAmount": "No puede ser negativo."})
    if "daysEstimated" in data:
        try:
            t.dias_estimados = int(data["daysEstimated"])
        except (TypeError, ValueError):
            raise ValidationError({"daysEstimated": "Debe ser un número de días."})
        if t.dias_estimados <= 0:
            raise ValidationError({"daysEstimated": "Debe ser mayor que cero."})
    if "active" in data:
        t.activo = bool(data["active"])
    if t.peso_hasta_kg is not None and t.peso_hasta_kg <= t.peso_desde_kg:
        raise ValidationError({"weightTo": "El 'hasta' debe ser mayor que el 'desde'."})
    if t.precio_por_kg_max is not None and t.precio_por_kg_max < t.precio_por_kg:
        raise ValidationError({"pricePerKgMax": "No puede ser menor que el precio por kg (mínimo)."})
    if t.precio_por_m3_max is not None and t.precio_por_m3 is not None and t.precio_por_m3_max < t.precio_por_m3:
        raise ValidationError({"pricePerM3Max": "No puede ser menor que el precio por m³ (mínimo)."})
    return t


class PartialCargoTariffsView(_Base):
    """GET/POST de la tabla de tarifas de carga nacional PARCIAL/consolidada
    (peso × destino → precio + días estimados). Ver `TarifaCargaParcial`."""
    permission_classes = [HasAnyRole(*_ROLES_COMISION)]

    def get(self, request):
        from apps.tercerizacion.models import TarifaCargaParcial
        return Response({
            "tariffs": [_partial_tariff_item(t) for t in TarifaCargaParcial.objects.all()],
        })

    def post(self, request):
        from apps.tercerizacion.models import TarifaCargaParcial
        t = _partial_tariff_from_body(request.data, TarifaCargaParcial())
        if "pricePerKg" not in request.data:
            raise ValidationError({"pricePerKg": "Requerido."})
        t.save()
        return Response(_partial_tariff_item(t), status=201)


class PartialCargoTariffDetailView(_Base):
    permission_classes = [HasAnyRole(*_ROLES_COMISION)]

    def patch(self, request, pk):
        from apps.tercerizacion.models import TarifaCargaParcial
        t = get_object_or_404(TarifaCargaParcial, pk=pk)
        _partial_tariff_from_body(request.data, t)
        t.save()
        return Response(_partial_tariff_item(t))

    def delete(self, request, pk):
        from apps.tercerizacion.models import TarifaCargaParcial
        get_object_or_404(TarifaCargaParcial, pk=pk).delete()
        return Response(status=204)


def _corridor_stop_item(p):
    return {
        "id": p.id, "name": p.nombre, "order": p.orden,
        "lat": float(p.lat), "lng": float(p.lng),
        "radiusKm": float(p.radio_km), "active": p.activo,
        "typeOfStop": p.tipo_parada, "requiresDetour": p.requiere_desvio,
    }


def _corridor_tramo_item(ct):
    # Cuántos OTROS corredores comparten este mismo TramoVial — advertencia
    # en la UI antes de editar/desactivar un tramo compartido (pedido
    # explícito: que una edición no rompa otro corredor sin avisar).
    otros = ct.tramo.corredores.exclude(corredor_id=ct.corredor_id).count()
    return {
        "order": ct.orden, "from": ct.tramo.nodo_inicio.nombre, "to": ct.tramo.nodo_fin.nombre,
        "direction": ct.sentido, "distanceKm": float(ct.tramo.distancia_km) if ct.tramo.distancia_km is not None else None,
        "sharedWithOtherCorridors": otros,
    }


def _corridor_item(c):
    tiene_tramos = c.tramos.exists()
    return {
        "id": c.id, "name": c.nombre, "active": c.activo,
        "code": c.codigo, "variant": c.variante, "validationStatus": c.estado_validacion,
        "originLabel": c.origen_nombre,
        "originLat": float(c.origen_lat) if c.origen_lat is not None else None,
        "originLng": float(c.origen_lng) if c.origen_lng is not None else None,
        "destinationLabel": c.destino_nombre,
        "destinationLat": float(c.destino_lat) if c.destino_lat is not None else None,
        "destinationLng": float(c.destino_lng) if c.destino_lng is not None else None,
        "trace": c.trazado,
        "traceIsDerived": tiene_tramos,   # True = viene del grafo de tramos, de solo lectura
        "totalDistanceKm": float(c.distancia_total_km) if c.distancia_total_km is not None else None,
        "axisToleranceKm": float(c.tolerancia_eje_km),
        "maxDetourKm": float(c.desvio_maximo_km),
        "stops": [_corridor_stop_item(p) for p in c.paradas.all().order_by("orden")],
        "segments": [_corridor_tramo_item(ct) for ct in c.tramos.select_related("tramo__nodo_inicio", "tramo__nodo_fin").order_by("orden")] if tiene_tramos else [],
    }


def _corridor_from_body(data, c):
    """Setea los campos planos del corredor y, si vino `stops`, reemplaza
    TODAS sus paradas (se editan siempre juntas — pocas por corredor, mismo
    patrón que `replace_lead_route` para las paradas de un Lead). El `order`
    que mande el cliente se ignora: se reasigna por posición en el array,
    para no chocar con el unique_together (corredor, orden)."""
    if "name" in data:
        nombre = (data["name"] or "").strip()
        if not nombre:
            raise ValidationError({"name": "Requerido."})
        c.nombre = nombre
    if "active" in data:
        c.activo = bool(data["active"])
    if "originLabel" in data:
        c.origen_nombre = (data["originLabel"] or "").strip()
    if "originLat" in data and "originLng" in data:
        try:
            c.origen_lat = Decimal(str(data["originLat"])) if data["originLat"] not in (None, "") else None
            c.origen_lng = Decimal(str(data["originLng"])) if data["originLng"] not in (None, "") else None
        except InvalidOperation:
            raise ValidationError({"originLat": "Coordenadas no válidas."})
    if "destinationLabel" in data:
        c.destino_nombre = (data["destinationLabel"] or "").strip()
    if "destinationLat" in data and "destinationLng" in data:
        try:
            c.destino_lat = Decimal(str(data["destinationLat"])) if data["destinationLat"] not in (None, "") else None
            c.destino_lng = Decimal(str(data["destinationLng"])) if data["destinationLng"] not in (None, "") else None
        except InvalidOperation:
            raise ValidationError({"destinationLat": "Coordenadas no válidas."})
    if "trace" in data and not (c.pk and c.tramos.exists()):
        # Si el corredor tiene tramos (CorredorTramo), `trazado` es derivado
        # (ver recalcular_trazado) — se ignora cualquier `trace` manual en vez
        # de romper el request, misma filosofía "nunca bloquear".
        trace = data["trace"] or []
        if not isinstance(trace, list):
            raise ValidationError({"trace": "Formato no válido."})
        c.trazado = trace
    if "axisToleranceKm" in data:
        try:
            c.tolerancia_eje_km = Decimal(str(data["axisToleranceKm"]))
        except (InvalidOperation, TypeError):
            raise ValidationError({"axisToleranceKm": "Valor no válido."})
        if c.tolerancia_eje_km <= 0:
            raise ValidationError({"axisToleranceKm": "Debe ser mayor que cero."})
    if "maxDetourKm" in data:
        try:
            c.desvio_maximo_km = Decimal(str(data["maxDetourKm"]))
        except (InvalidOperation, TypeError):
            raise ValidationError({"maxDetourKm": "Valor no válido."})
        if c.desvio_maximo_km <= c.tolerancia_eje_km:
            raise ValidationError({"maxDetourKm": "Debe ser mayor que la tolerancia del eje."})
    c.save()

    if "stops" in data:
        from apps.tercerizacion.models import CorredorParada

        stops = data["stops"] or []
        c.paradas.all().delete()
        for i, s in enumerate(stops):
            nombre = (s.get("name") or "").strip()
            if not nombre:
                raise ValidationError({"stops": f"Parada #{i + 1}: nombre requerido."})
            try:
                lat = Decimal(str(s["lat"]))
                lng = Decimal(str(s["lng"]))
            except (InvalidOperation, TypeError, KeyError):
                raise ValidationError({"stops": f"Parada #{i + 1}: coordenadas no válidas."})
            try:
                radio_km = Decimal(str(s.get("radiusKm", "1")))
            except InvalidOperation:
                raise ValidationError({"stops": f"Parada #{i + 1}: radio no válido."})
            if radio_km <= 0:
                raise ValidationError({"stops": f"Parada #{i + 1}: el radio debe ser mayor que cero."})
            CorredorParada.objects.create(
                corredor=c, nombre=nombre, orden=i, lat=lat, lng=lng,
                radio_km=radio_km, activo=bool(s.get("active", True)),
            )
    return c


class CorridorsView(_Base):
    """GET/POST de corredores de carga nacional (rutas troncales con paradas)
    — ver `apps.tercerizacion.models.Corredor`/`CorredorParada` y
    `apps.tercerizacion.corredores.resolver_corredor`."""
    permission_classes = [HasAnyRole(*_ROLES_COMISION)]

    def get(self, request):
        from apps.tercerizacion.models import Corredor
        corredores = Corredor.objects.all().prefetch_related(
            "paradas", "tramos__tramo__nodo_inicio", "tramos__tramo__nodo_fin", "tramos__tramo__corredores",
        )
        return Response({"corridors": [_corridor_item(c) for c in corredores]})

    def post(self, request):
        from apps.tercerizacion.models import Corredor
        if not (request.data.get("name") or "").strip():
            raise ValidationError({"name": "Requerido."})
        with transaction.atomic():
            c = _corridor_from_body(request.data, Corredor())
        return Response(_corridor_item(c), status=201)


class CorridorDetailView(_Base):
    permission_classes = [HasAnyRole(*_ROLES_COMISION)]

    def patch(self, request, pk):
        from apps.tercerizacion.models import Corredor
        c = get_object_or_404(Corredor, pk=pk)
        with transaction.atomic():
            _corridor_from_body(request.data, c)
        return Response(_corridor_item(c))

    def delete(self, request, pk):
        from apps.tercerizacion.models import Corredor
        get_object_or_404(Corredor, pk=pk).delete()   # CASCADE borra sus paradas
        return Response(status=204)


class CorridorSharedRoutesView(_Base):
    """GET de solo lectura: qué corredores comparten un trayecto — la
    "detección de corredores compartidos" (ver
    apps.tercerizacion.corredores.detectar_corredores_compartidos). Resuelve
    origen/destino por nombre (`?origin=Trujillo&destination=Chiclayo`) contra
    el catálogo de `Localidad` — nunca comparando nombres de ciudad a ciegas,
    solo geometría real (tramos con estado TRAZADO_CALCULADO/VALIDADO)."""
    permission_classes = [HasAnyRole(*_ROLES_COMISION)]

    def get(self, request):
        from apps.tercerizacion.corredores import detectar_corredores_compartidos, resolver_localidad

        origen_texto = (request.query_params.get("origin") or "").strip()
        destino_texto = (request.query_params.get("destination") or "").strip()
        if not origen_texto or not destino_texto:
            raise ValidationError({"origin": "Se requiere origin y destination."})

        origen = resolver_localidad(origen_texto)
        destino = resolver_localidad(destino_texto)
        if not origen or not destino:
            return Response({
                "originResolved": bool(origen), "destinationResolved": bool(destino), "corridors": [],
            })

        resultados = detectar_corredores_compartidos(origen, destino)
        return Response({
            "originResolved": True, "destinationResolved": True,
            "origin": {"id": origen.id, "name": origen.nombre, "lat": float(origen.lat), "lng": float(origen.lng)},
            "destination": {"id": destino.id, "name": destino.nombre, "lat": float(destino.lat), "lng": float(destino.lng)},
            "corridors": [
                {
                    "id": r["corredor"].id, "code": r["corredor"].codigo, "name": r["corredor"].nombre,
                    "fullSegment": r["tramo_completo"], "requiresDetour": r["requiere_desvio"],
                    "sharedCandidate": r["candidato_a_compartida"],
                }
                for r in resultados if r["tramo_completo"]
            ],
        })


class LocalitiesView(_Base):
    """GET de solo lectura: catálogo de `Localidad` (nodos del grafo de
    corredores) — para el mapa interactivo y el buscador de "corredores
    compartidos" en Configuración → Corredores → Mapa."""
    permission_classes = [HasAnyRole(*_ROLES_COMISION)]

    def get(self, request):
        from apps.tercerizacion.models import Localidad
        localidades = Localidad.objects.filter(activo=True, lat__isnull=False, lng__isnull=False).order_by("nombre")
        return Response({
            "localities": [
                {
                    "id": loc.id, "name": loc.nombre, "department": loc.departamento,
                    "type": loc.tipo, "lat": float(loc.lat), "lng": float(loc.lng),
                }
                for loc in localidades
            ],
        })


class PublicationListView(_Base):
    def get(self, request):
        p = request.query_params
        qs = _PUB_QS
        st = _STATE_ES.get(p.get("state"))
        if st:
            qs = qs.filter(estado=st)
        elif p.get("active") == "true":
            qs = qs.filter(estado__in=["borrador", "abierta", "publicada", "con_ofertas"])
        search = (p.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(codigo__icontains=search)
                | Q(servicio__codigo__icontains=search)
                | Q(servicio__distrito_origen__icontains=search)
                | Q(servicio__distrito_destino__icontains=search)
            )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs.order_by("-creado_en"), request, view=self)
        return paginator.get_paginated_response([publication_item(x) for x in page])


class PublicationDetailView(_Base):
    def get(self, request, pk):
        return Response(publication_detail(get_object_or_404(_PUB_QS, pk=pk)))


class PublicationPublishView(_Base):
    def post(self, request, pk):
        pub = get_object_or_404(_PUB_QS, pk=pk)
        groups = request.data.get("groups") or []
        if isinstance(groups, str):
            groups = [g.strip() for g in groups.split(",") if g.strip()]
        try:
            adj.publicar_publicacion(pub, request.user, grupos=groups)
        except adj.AdjudicacionError as e:
            raise ValidationError(str(e))
        return Response(publication_detail(get_object_or_404(_PUB_QS, pk=pk)))


class PublicationOffersView(_Base):
    def post(self, request, pk):
        pub = get_object_or_404(_PUB_QS, pk=pk)
        d = request.data
        carrier = get_object_or_404(Transportista, pk=d.get("carrierId"))
        vehiculo = None
        if d.get("vehicleId"):
            vehiculo = get_object_or_404(
                TransportistaVehiculo, pk=d["vehicleId"], transportista=carrier,
            )
        amount = _amount(d.get("amount"))
        try:
            adj.registrar_oferta(
                pub, monto=amount, usuario=request.user, transportista=carrier,
                transportista_vehiculo=vehiculo, nota=(d.get("note") or "").strip(),
            )
        except adj.AdjudicacionError as e:
            raise ValidationError(str(e))
        return Response(publication_detail(get_object_or_404(_PUB_QS, pk=pk)))


class PublicationAwardView(_Base):
    def post(self, request, pk):
        pub = get_object_or_404(_PUB_QS, pk=pk)
        oferta = get_object_or_404(OfertaTransportista, pk=request.data.get("offerId"), publicacion=pub)
        vehiculo = None
        if request.data.get("vehicleId"):
            vehiculo = get_object_or_404(
                TransportistaVehiculo, pk=request.data["vehicleId"],
            )
        client_price = request.data.get("clientPrice")
        if client_price not in (None, ""):
            client_price = _amount(client_price, "clientPrice")
        try:
            prog = adj.adjudicar_publicacion(
                pub, oferta, request.user, transportista_vehiculo=vehiculo,
                precio_cliente=client_price or None,
                autoriza_bajo_margen=bool(request.data.get("authorizeLowMargin")),
            )
        except adj.AdjudicacionError as e:
            raise ValidationError(str(e))
        return Response({
            "ok": True,
            "assignmentId": prog.id,
            "publication": publication_detail(get_object_or_404(_PUB_QS, pk=pk)),
        })
