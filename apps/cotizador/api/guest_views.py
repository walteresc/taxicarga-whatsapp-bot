"""API v2 · Cotización rápida de invitado + conversión a cliente/empresa (F7).

Endpoints PÚBLICOS (AllowAny). Protegidos con:
  - ScopedRateThrottle por IP (cache 'throttle' → Redis, compartido entre workers)
  - honeypot: campo oculto `website`; si viene lleno, se descarta como bot
El Lead que crean se marca origen_carga='invitado' y NO dispara notificaciones.

    POST /api/v2/guest/quote     {origin, destination, cargo, date?, contact, website?}
    POST /api/v2/guest/signup    {quoteCode?, phone, name, password, email?, isCompany, ruc?, razonSocial?, website?}
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model, login
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.clientes.models import Cliente, ClienteUsuario, Empresa
from apps.cotizador.models import Cotizacion
from apps.cotizador.services import cotizar_lead, estimar_precio
from apps.dashboard.views_auth_api import _user_payload
from apps.leads.geo import clasificar_y_marcar_ambito, evaluar_ambito
from apps.leads.models import Lead
from apps.leads.route import replace_lead_route

User = get_user_model()


class _ThrottleCache(ScopedRateThrottle):
    cache = caches["throttle"]


def _honeypot(data):
    return bool((data.get("website") or "").strip())


def _num(raw):
    if raw in (None, ""):
        return None
    try:
        v = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        return None
    return v if v > 0 else None


def _coord(raw):
    """Como `_num` pero para lat/lng: pueden ser negativas (Perú) o cero."""
    if raw in (None, ""):
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError):
        return None


def _quote_view(lead):
    tecnica = lead.cotizaciones.order_by("-fecha_creacion").first()
    if not tecnica:
        return {"amount": None, "mode": "pending"}
    if tecnica.modo == "manual":
        return {"amount": None, "mode": "advisor", "confidence": tecnica.confianza}
    return {
        "amount": float(tecnica.precio_recomendado),
        "mode": "auto",
        "confidence": tecnica.confianza,
        "range": [float(tecnica.precio_min), float(tecnica.precio_max)],
        "daysEstimated": tecnica.dias_estimados,
    }


def _price_view_from_calc(calc):
    """Como `_quote_view`, pero sobre el dict que devuelve `estimar_precio`
    (sin Cotizacion persistida) — para el preview de precio."""
    if calc["modo"] == Cotizacion.MODO_MANUAL:
        return {"amount": None, "mode": "advisor", "confidence": calc["confianza"]}
    return {
        "amount": float(calc["precio_recomendado"]),
        "mode": "auto",
        "confidence": calc["confianza"],
        "range": [float(calc["precio_min"]), float(calc["precio_max"])],
        "daysEstimated": calc.get("dias_estimados"),
    }


class _Public(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [_ThrottleCache]

    def get_exception_handler(self):
        return api_exception_handler


class PreviewQuoteView(_Public):
    """Precio de referencia ANTES de publicar — no crea nada (ni Cliente ni
    Lead). Compara Express (camión dedicado) vs. Consolidada (comparte
    camión, solo si hay tabla de tarifas cargada para ese destino/peso — ver
    `apps.tercerizacion.services.resolver_tarifa_parcial`). Sirve para que el
    cliente elija la modalidad ANTES de que exista la solicitud real; el
    precio final se recalcula (y sí se guarda) al publicar de verdad, con la
    modalidad ya elegida.

        POST /api/v2/guest/quote/preview  {origin, destination, cargo}
        → {isInterprovincial, express, consolidated}
    """
    throttle_scope = "guest_quote_preview"

    def post(self, request):
        d = request.data
        origin = d.get("origin") or {}
        destination = d.get("destination") or {}
        cargo = d.get("cargo") or {}
        if not origin.get("district") or not destination.get("district"):
            raise ValidationError("Necesitamos al menos el distrito de origen y de destino.")

        lead = Lead(
            categoria_carga=(cargo.get("category") or ""),
            tipo_servicio=(cargo.get("category") or "carga"),
            distrito_origen=origin.get("district") or "",
            distrito_destino=destination.get("district") or "",
            peso_carga_kg=_num(cargo.get("weightKg")),
            volumen_carga_m3=_num(cargo.get("volumeM3")),
            lat_origen=_coord(origin.get("lat")), lng_origen=_coord(origin.get("lng")),
            lat_destino=_coord(destination.get("lat")), lng_destino=_coord(destination.get("lng")),
        )
        lead.es_interprovincial = evaluar_ambito(lead)

        lead.modo_carga = Lead.MODO_CARGA_COMPLETA
        express = _price_view_from_calc(estimar_precio(lead))

        consolidated = None
        if lead.es_interprovincial:
            from apps.tercerizacion.services import existe_tarifa_especifica

            # Solo se ofrece Consolidada en rutas "frecuentes" — con tarifa
            # propia cargada para ese destino, no la tarifa general (esa
            # cubre cualquier ciudad y no distingue frecuente de ocasional).
            if existe_tarifa_especifica(destination.get("district")):
                lead.modo_carga = Lead.MODO_CARGA_PARCIAL
                consolidated = _price_view_from_calc(estimar_precio(lead))

        return Response({
            "isInterprovincial": lead.es_interprovincial,
            "express": express,
            "consolidated": consolidated,
        })


class GuestQuoteView(_Public):
    throttle_scope = "guest_quote"

    @transaction.atomic
    def post(self, request):
        from apps.leads.photos import parse_request_body, save_lead_photos

        d, fotos = parse_request_body(request)
        if _honeypot(d):
            # respuesta plausible pero sin crear nada
            return Response({"quoteCode": None, "price": {"amount": None, "mode": "advisor"}})

        origin = d.get("origin") or {}
        destination = d.get("destination") or {}
        cargo = d.get("cargo") or {}
        contact = d.get("contact") or {}
        stops = [s for s in (d.get("stops") or []) if s.get("district")]
        if not origin.get("district") or not destination.get("district"):
            raise ValidationError("Necesitamos al menos el distrito de origen y de destino.")

        phone = (contact.get("phone") or "").strip()
        if not phone:
            raise ValidationError({"phone": "Dejanos un teléfono para poder responderte."})

        cliente = Cliente.objects.filter(telefono=phone).first()
        if cliente is None:
            cliente = Cliente.objects.create(
                telefono=phone, nombre=(contact.get("name") or "").strip(),
                correo=(contact.get("email") or "").strip(), tipo=Cliente.TIPO_OCASIONAL,
            )

        fecha = None
        if d.get("date"):
            try:
                fecha = datetime.strptime(d["date"], "%Y-%m-%d").date()
            except ValueError:
                fecha = None

        modo = d.get("quoteMode") or Lead.MODO_COT_POR_CARGA
        if modo not in dict(Lead.MODOS_COTIZACION):
            modo = Lead.MODO_COT_POR_CARGA
        modo_carga = d.get("loadMode") or Lead.MODO_CARGA_COMPLETA
        if modo_carga not in dict(Lead.MODOS_CARGA):
            modo_carga = Lead.MODO_CARGA_COMPLETA

        lead = Lead.objects.create(
            cliente=cliente,
            origen_carga="invitado",
            modo_cotizacion=modo,
            modo_carga=modo_carga,
            categoria_carga=(cargo.get("category") or ""),
            tipo_servicio=(cargo.get("category") or "carga"),
            distrito_origen=origin.get("district") or "",
            distrito_destino=destination.get("district") or "",
            direccion_origen=origin.get("address") or "",
            direccion_destino=destination.get("address") or "",
            provincia_origen=origin.get("province") or "",
            provincia_destino=destination.get("province") or "",
            region_origen=origin.get("region") or "",
            region_destino=destination.get("region") or "",
            lat_origen=_coord(origin.get("lat")),
            lng_origen=_coord(origin.get("lng")),
            lat_destino=_coord(destination.get("lat")),
            lng_destino=_coord(destination.get("lng")),
            lista_objetos=cargo.get("detail") or "",
            peso_carga_kg=_num(cargo.get("weightKg")),
            volumen_carga_m3=_num(cargo.get("volumeM3")),
            tipo_camion=(cargo.get("truckType") or "") if modo == Lead.MODO_COT_POR_VEHICULO else "",
            fecha_servicio=fecha,
            horario_servicio=(d.get("schedule") or ""),
            estado=Lead.NUEVO,
        )
        save_lead_photos(lead, fotos)
        replace_lead_route(lead, [
            {
                "tipo": "origen", "distrito": origin.get("district") or "", "direccion": origin.get("address") or "",
                "provincia": origin.get("province") or "", "region": origin.get("region") or "",
                "lat": _coord(origin.get("lat")), "lng": _coord(origin.get("lng")),
            },
            *[
                {
                    "tipo": "parada", "distrito": s.get("district") or "", "direccion": s.get("address") or "",
                    "provincia": s.get("province") or "", "region": s.get("region") or "",
                    "lat": _coord(s.get("lat")), "lng": _coord(s.get("lng")),
                }
                for s in stops
            ],
            {
                "tipo": "destino", "distrito": destination.get("district") or "", "direccion": destination.get("address") or "",
                "provincia": destination.get("province") or "", "region": destination.get("region") or "",
                "lat": _coord(destination.get("lat")), "lng": _coord(destination.get("lng")),
            },
        ])
        clasificar_y_marcar_ambito(lead)
        cotizar_lead(lead)
        lead.refresh_from_db()
        return Response({
            "quoteCode": lead.codigo,
            "route": f"{lead.distrito_origen} → {lead.distrito_destino}",
            "price": _quote_view(lead),
        }, status=201)


class GuestSignupView(_Public):
    throttle_scope = "guest_signup"

    @transaction.atomic
    def post(self, request):
        d = request.data
        if _honeypot(d):
            raise ValidationError("No pudimos crear la cuenta.")

        phone = (d.get("phone") or "").strip()
        name = (d.get("name") or "").strip()
        password = d.get("password") or ""
        if not phone or not name:
            raise ValidationError("Teléfono y nombre son obligatorios.")
        if len(password) < 8:
            raise ValidationError({"password": "La contraseña debe tener al menos 8 caracteres."})

        cliente = Cliente.objects.filter(telefono=phone).first()
        if cliente and cliente.usuarios_portal.filter(activo=True, usuario__isnull=False).exists():
            raise ValidationError(
                "Ese teléfono ya tiene una cuenta. Iniciá sesión o recuperá tu contraseña."
            )
        if cliente is None:
            cliente = Cliente.objects.create(telefono=phone, nombre=name, tipo=Cliente.TIPO_FRECUENTE)
        elif not cliente.nombre:
            cliente.nombre = name

        is_company = bool(d.get("isCompany"))
        empresa = None
        if is_company:
            razon = (d.get("razonSocial") or name).strip()
            empresa = Empresa.objects.create(
                razon_social=razon, ruc=(d.get("ruc") or "").strip(),
            )
            cliente.tipo = Cliente.TIPO_EMPRESA
            cliente.razon_social = razon
            cliente.ruc = (d.get("ruc") or "").strip()
        elif cliente.tipo == Cliente.TIPO_OCASIONAL:
            cliente.tipo = Cliente.TIPO_FRECUENTE
        email = (d.get("email") or "").strip()
        if email and not cliente.correo:
            cliente.correo = email
        cliente.save()

        base_username = "".join(ch for ch in phone if ch.isdigit()) or f"cli{cliente.id}"
        username = base_username
        i = 1
        while User.objects.filter(username=username).exists():
            i += 1
            username = f"{base_username}-{i}"
        user = User.objects.create_user(
            username=username, password=password, email=email,
            first_name=name[:150],
        )
        from django.contrib.auth.models import Group
        user.groups.add(Group.objects.get_or_create(name="Cliente Portal")[0])

        ClienteUsuario.objects.create(
            usuario=user, cliente=cliente, empresa=empresa, rol=ClienteUsuario.ROL_TITULAR,
        )

        code = (d.get("quoteCode") or "").strip()
        if code:
            Lead.objects.filter(codigo=code, origen_carga="invitado").update(
                cliente=cliente, origen_carga="portal_cliente",
            )

        login(request, user)
        return Response({"status": "ok", "user": _user_payload(user)}, status=201)
