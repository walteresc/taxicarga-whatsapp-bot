"""API v2 del pipeline comercial. APIViews de solo lectura + acciones de
transición. La forma de la respuesta vive en `shapes.py`; la lógica de negocio
en `apps/cotizador/pipeline.py` y `apps/cotizador/commercial.py` (reutilizadas).
"""
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.pagination import StandardPagination
from apps.api.permissions import HasAnyRole
from apps.cotizador import pipeline
from apps.cotizador.models import SolicitudCotizacion
from apps.leads.models import Lead

from . import shapes

_ROLES = ("Administrador", "Supervisor", "Asesor de Ventas")
_ACTIVA = (SolicitudCotizacion.PENDIENTE, SolicitudCotizacion.EN_PROCESO)


class _Base(APIView):
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_exception_handler(self):
        return api_exception_handler

    def _paginate(self, queryset, shape):
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        return paginator.get_paginated_response([shape(x) for x in page])


class PipelineCountsView(_Base):
    def get(self, request):
        return Response(pipeline.pipeline_counts())


# --------------------------------------------------------------------------- #
#  Potenciales
# --------------------------------------------------------------------------- #

class PotentialListView(_Base):
    def get(self, request):
        qs = pipeline.potenciales_queryset().select_related("cliente").order_by("-prioridad", "-fecha_creacion")
        search = (request.query_params.get("search") or "").strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(cliente__nombre__icontains=search)
                | Q(distrito_origen__icontains=search)
                | Q(distrito_destino__icontains=search)
            )
        return self._paginate(qs, shapes.potential_item)


class PotentialDetailView(_Base):
    def get(self, request, pk):
        lead = get_object_or_404(Lead.objects.select_related("cliente"), pk=pk)
        data = shapes.lead_summary(lead)
        conv = lead.sesiones_whatsapp.order_by("-actualizada_en").first()
        data["conversationId"] = conv.id if conv else None
        data["informationPct"] = conv.porcentaje_informacion if conv else 0
        return Response(data)


class LeadStageView(_Base):
    """Etapa del pipeline de un lead + movimiento manual desde la bandeja.
    GET  -> {stage, label, movable} (movable = etapas a las que se puede pasar a mano)
    POST {stage} -> mueve (solo potentials/review/quoting; el resto es error)
    """
    def get(self, request, pk):
        lead = get_object_or_404(Lead.objects.select_related("cliente"), pk=pk)
        stage = pipeline.etapa_de_lead(lead)
        # El resumen del servicio y los precios los sirve la bandeja en
        # `service_data` (ver apps/dashboard/views_whatsapp.py::_service_data); acá
        # solo va lo que ese payload no tiene: la etapa del pipeline y el último
        # monto cotizado, para distinguir cotización nueva de re-cotización.
        from apps.cotizador.pricing import panel_prices
        suggested, quoted = panel_prices(lead)

        conv = lead.sesiones_whatsapp.order_by("-actualizada_en").first()
        ex = (conv.datos_extraidos or {}) if conv else {}

        return Response({
            "stage": stage,
            "label": pipeline.ETAPA_LABEL.get(stage, "—"),
            "movable": list(pipeline.ETAPAS_MANUALES),
            "quotedPrice": float(quoted) if quoted is not None else None,
            "suggestedPrice": float(suggested) if suggested is not None else None,
            "chatPrice": ex.get("precio_chat"),
            "chatPriceAccepted": bool(ex.get("precio_chat_aceptado")),
            "chatPriceIncludes": ex.get("precio_chat_incluye"),
            "chatPriceNote": ex.get("precio_chat_condiciones"),
        })

    def post(self, request, pk):
        stage = (request.data.get("stage") or "").strip()
        result = pipeline.mover_lead_a_etapa(pk, stage, request.user)
        return Response({"stage": result, "label": pipeline.ETAPA_LABEL.get(result, "—")})


class LeadQuickQuoteView(_Base):
    """Botón 'Cotizar' del chat: precio + mensaje → crea la cotización, la
    marca enviada y manda el mensaje al cliente."""
    def post(self, request, pk):
        d = request.data
        result = pipeline.cotizar_rapido(
            pk,
            d.get("price"),
            d.get("message"),
            request.user,
            vigencia_dias=int(d.get("validityDays") or 7),
        )
        result["label"] = pipeline.ETAPA_LABEL.get(result["stage"], "—")
        return Response(result)


class LostListView(_Base):
    def get(self, request):
        qs = pipeline.perdidos_queryset()
        search = (request.query_params.get("search") or "").strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(cliente__nombre__icontains=search)
                | Q(distrito_origen__icontains=search)
                | Q(distrito_destino__icontains=search)
                | Q(motivo_perdida_detalle__icontains=search)
            )
        return self._paginate(qs, shapes.lost_item)


class LeadReactivateView(_Base):
    """Reactiva un lead perdido: vuelve al pipeline (Oportunidades, o Para
    revisión si `requiere_asesor`)."""
    def post(self, request, pk):
        lead = get_object_or_404(Lead, pk=pk)
        if lead.estado != Lead.PERDIDO:
            return Response({"error": "Este lead no está perdido."}, status=400)
        pipeline.mover_lead_a_etapa(pk, "potentials", request.user)
        lead.refresh_from_db()
        return Response({"ok": True, "stage": pipeline.etapa_de_lead(lead)})


class LeadMarkSeenView(_Base):
    """Marca 'visto' el detalle de un lead en una etapa (apaga el badge de
    'no visto' del menú y de las tablas). `stage` puede venir explícito o, si es
    'chat'/vacío, se deduce de la etapa actual del lead."""
    _VALID = {"potentials", "review", "quoting", "quotes", "bookings"}

    def post(self, request, pk):
        etapa = (request.data.get("stage") or "").strip()
        if etapa not in self._VALID:
            lead = get_object_or_404(Lead, pk=pk)
            etapa = pipeline.etapa_de_lead(lead)
        if etapa in self._VALID:
            pipeline.marcar_visto(pk, etapa, request.user)
            return Response({"ok": True, "stage": etapa})
        return Response({"ok": False, "stage": etapa})


class LeadDiscardView(_Base):
    """Descarta la oportunidad de un lead (→ PERDIDO). Sirve para el botón
    'Descartar' del resumen del servicio y de la tabla de Potenciales."""
    def post(self, request, pk):
        motivo = (request.data.get("reason") or "").strip()
        if not motivo:
            raise ValidationError({"reason": "Indica el motivo del descarte."})
        get_object_or_404(Lead, pk=pk)
        pipeline.descartar_lead(pk, request.user, motivo)
        return Response({"ok": True})


class LeadCancelBookingView(_Base):
    """Cancela la reserva (Servicio) asociada a un lead."""
    def post(self, request, pk):
        from apps.servicios.models import Servicio
        from apps.servicios.services import cancelar_servicio

        lead = get_object_or_404(Lead, pk=pk)
        servicio = (Servicio.objects.filter(lead_origen=lead)
                    .exclude(estado="cancelado")
                    .order_by("-fecha_creacion").first())
        if not servicio:
            return Response({"error": "Esta conversación no tiene una reserva activa."}, status=400)
        cancelar_servicio(servicio, request.user,
                          request.data.get("reason") or "Reserva cancelada por el asesor")
        from apps.cotizador import pipeline
        return Response({"cancelled": True, "stage": pipeline.etapa_de_lead(lead)})


class LeadServiceSummaryView(_Base):
    """Texto del servicio para el modal 'Ver' y para enviarlo a un conductor."""
    def get(self, request, pk):
        lead = get_object_or_404(Lead.objects.select_related("cliente"), pk=pk)
        conv = lead.sesiones_whatsapp.order_by("-actualizada_en").first()
        return Response({"text": shapes.texto_servicio(lead, conv)})


class LeadServiceEditView(_Base):
    """El asesor corrige a mano los datos del servicio en el resumen."""

    _STR = ("type:tipo_servicio", "origin:distrito_origen", "destination:distrito_destino",
            "addressOrigin:direccion_origen", "addressDestination:direccion_destino",
            "schedule:horario_servicio", "items:lista_objetos", "heavyItems:objetos_pesados",
            "contactName:persona_contacto", "contactPhone:telefono_contacto")
    _INT = ("floorOrigin:piso_origen", "floorDestination:piso_destino")
    _BOOL = ("elevatorOrigin:ascensor_origen", "elevatorDestination:ascensor_destino")
    _DEC = ("weightKg:peso_carga_kg", "volumeM3:volumen_carga_m3")

    def get(self, request, pk):
        """Datos del servicio con la forma que consume <ServiceSummary> (misma
        que la bandeja). Sirve para reusar el modal 'Ver detalles' fuera del chat."""
        from apps.dashboard.views_whatsapp import _service_data

        lead = get_object_or_404(Lead.objects.select_related("cliente"), pk=pk)
        conv = lead.sesiones_whatsapp.order_by("-actualizada_en").first()
        return Response({"serviceData": (_service_data(conv) if conv else {}) or {}})

    def patch(self, request, pk):
        from decimal import Decimal, InvalidOperation

        from django.utils.dateparse import parse_date

        lead = get_object_or_404(Lead.objects.select_related("cliente"), pk=pk)
        d = request.data
        changed = []          # campos del Lead
        other_changed = []    # cambios fuera del Lead (cliente, cotización)

        if "customerName" in d and lead.cliente_id:
            nombre = (d.get("customerName") or "").strip()
            if nombre and nombre != lead.cliente.nombre:
                lead.cliente.nombre = nombre[:160]
                lead.cliente.save(update_fields=["nombre"])
                other_changed.append("customer_name")

        for pair in self._STR:
            key, attr = pair.split(":")
            if key in d:
                setattr(lead, attr, (d.get(key) or "").strip())
                changed.append(attr)
        for pair in self._INT:
            key, attr = pair.split(":")
            if key in d:
                v = d.get(key)
                try:
                    setattr(lead, attr, int(v) if v not in (None, "") else None)
                    changed.append(attr)
                except (TypeError, ValueError):
                    return Response({"error": f"'{key}' debe ser un número entero."}, status=400)
        for pair in self._BOOL:
            key, attr = pair.split(":")
            if key in d:
                v = d.get(key)
                setattr(lead, attr, None if v in (None, "") else bool(v))
                changed.append(attr)
        for pair in self._DEC:
            key, attr = pair.split(":")
            if key in d:
                v = d.get(key)
                try:
                    setattr(lead, attr, Decimal(str(v)) if v not in (None, "") else None)
                    changed.append(attr)
                except (InvalidOperation, TypeError):
                    return Response({"error": f"'{key}' debe ser un número."}, status=400)
        if "serviceDate" in d:
            raw = d.get("serviceDate")
            if raw in (None, ""):
                lead.fecha_servicio = None
            else:
                parsed = parse_date(str(raw))
                if parsed is None:
                    return Response({"error": "Fecha inválida (usá AAAA-MM-DD)."}, status=400)
                lead.fecha_servicio = parsed
            changed.append("fecha_servicio")

        # Precio cotizado: NO es un campo suelto — lo registra como
        # cotización/revisión (sin mandar WhatsApp) para que el pipeline cuadre.
        quote_updated = None
        if "quotedPrice" in d and d.get("quotedPrice") not in (None, ""):
            try:
                nuevo = Decimal(str(d["quotedPrice"]))
            except (InvalidOperation, TypeError):
                return Response({"error": "'quotedPrice' debe ser un número."}, status=400)
            if nuevo > 0 and nuevo != (lead.precio_cotizado or None):
                conv = lead.sesiones_whatsapp.order_by("-actualizada_en").first()
                if conv is not None:
                    from apps.cotizador.commercial import registrar_cotizacion_desde_chat
                    registrar_cotizacion_desde_chat(
                        conv, nuevo,
                        observacion="Precio ajustado a mano por el asesor desde el resumen del servicio",
                    )
                    quote_updated = float(nuevo)

        if not changed and not other_changed and quote_updated is None:
            return Response({"error": "Nada para actualizar."}, status=400)
        if changed:
            lead.save(update_fields=list(set(changed)))
        return Response({
            "updated": sorted(set(changed) | set(other_changed)),
            "quotedPrice": quote_updated,
        })


class LeadSendSummaryView(_Base):
    """Envía el resumen del servicio a un contacto (conductor u otra
    conversación) — mismo circuito que 'reenviar' un mensaje del chat."""
    def post(self, request, pk):
        from apps.whatsapp.domain import crear_conversacion_manual
        from apps.whatsapp.models import ConversacionWhatsApp
        from apps.whatsapp.services import send_crm_message

        lead = get_object_or_404(Lead.objects.select_related("cliente"), pk=pk)
        conv_src = lead.sesiones_whatsapp.order_by("-actualizada_en").first()
        texto = (request.data.get("text") or "").strip() or shapes.texto_servicio(lead, conv_src)

        conv_id = request.data.get("conversationId")
        phone = (request.data.get("phone") or "").strip()
        name = (request.data.get("name") or "").strip()

        if conv_id:
            target = get_object_or_404(ConversacionWhatsApp, pk=conv_id)
        elif phone:
            target = crear_conversacion_manual(phone, request.user, nombre=name)
        else:
            return Response({"error": "Indicá un contacto o un teléfono."}, status=400)

        res = send_crm_message(target, request.user, texto)
        if not res.get("success"):
            return Response({
                "sent": False,
                "conversationId": target.id,
                "error": res.get("error_detail") or "WhatsApp rechazó el envío; mandalo a mano por WhatsApp Web.",
            }, status=200)
        return Response({"sent": True, "conversationId": target.id})


class LeadQuickBookingView(_Base):
    """Botón 'Reservar' del chat: datos mínimos → crea la Reserva (Servicio)."""
    def post(self, request, pk):
        d = request.data
        result = pipeline.reservar_rapido(pk, {
            "nombre_cliente": d.get("customerName"),
            "persona_contacto": d.get("contactName"),
            "telefono_contacto": d.get("contactPhone"),
            "fecha_servicio": d.get("serviceDate"),
            "horario_servicio": d.get("schedule"),
            "tipo_servicio": d.get("type"),
            "direccion_origen": d.get("addressOrigin"),
            "direccion_destino": d.get("addressDestination"),
            "distrito_origen": d.get("districtOrigin"),
            "distrito_destino": d.get("districtDestination"),
            "precio": d.get("price"),
        }, request.user)
        result["label"] = pipeline.ETAPA_LABEL.get(result["stage"], "—")
        return Response(result)


# --------------------------------------------------------------------------- #
#  Para revisión
# --------------------------------------------------------------------------- #

class ReviewListView(_Base):
    def get(self, request):
        qs = (
            SolicitudCotizacion.objects
            .filter(tipo=SolicitudCotizacion.TIPO_REVISION, estado__in=_ACTIVA)
            .select_related("lead__cliente", "asignada_a", "conversacion")
            .order_by("-prioridad", "creada_en")
        )
        search = (request.query_params.get("search") or "").strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(lead__cliente__nombre__icontains=search)
                | Q(lead__distrito_origen__icontains=search)
                | Q(lead__distrito_destino__icontains=search)
                | Q(motivo__icontains=search)
            )
        return self._paginate(qs, shapes.review_item)


class ReviewDetailView(_Base):
    def get(self, request, pk):
        solicitud = get_object_or_404(
            SolicitudCotizacion.objects.select_related("lead__cliente", "conversacion"),
            pk=pk, tipo=SolicitudCotizacion.TIPO_REVISION,
        )
        data = shapes.lead_summary(solicitud.lead)
        data["reviewId"] = solicitud.id
        data["reason"] = solicitud.motivo
        data["conversationId"] = solicitud.conversacion_id
        return Response(data)


class ReviewToQuotingView(_Base):
    def post(self, request, pk):
        solicitud = pipeline.pasar_revision_a_cotizar(pk, request.user)
        return Response(shapes.quote_request_item(solicitud), status=200)


class ReviewDiscardView(_Base):
    def post(self, request, pk):
        motivo = (request.data.get("reason") or "").strip()
        if not motivo:
            raise ValidationError({"reason": "Indica el motivo del descarte."})
        solicitud = get_object_or_404(SolicitudCotizacion, pk=pk, tipo=SolicitudCotizacion.TIPO_REVISION)
        pipeline.descartar_lead(solicitud.lead_id, request.user, motivo)
        return Response({"ok": True})


# --------------------------------------------------------------------------- #
#  Por cotizar
# --------------------------------------------------------------------------- #

def _quote_request_qs():
    return (
        SolicitudCotizacion.objects
        .filter(tipo=SolicitudCotizacion.TIPO_COTIZACION, estado__in=_ACTIVA)
        .select_related("lead__cliente", "lead__whatsapp_channel", "asignada_a", "conversacion")
    )


class QuoteRequestListView(_Base):
    def get(self, request):
        qs = _quote_request_qs().order_by("-prioridad", "creada_en")
        search = (request.query_params.get("search") or "").strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(lead__cliente__nombre__icontains=search)
                | Q(lead__distrito_origen__icontains=search)
                | Q(lead__distrito_destino__icontains=search)
            )
        return self._paginate(qs, shapes.quote_request_item)


class QuoteRequestDetailView(_Base):
    def get(self, request, pk):
        from apps.cotizador.services import cotizar_lead

        solicitud = get_object_or_404(_quote_request_qs(), pk=pk)
        lead = solicitud.lead
        technical = lead.cotizaciones.order_by("-fecha_creacion").first() or cotizar_lead(lead)
        frequent = pipeline.tarifa_ruta_frecuente(lead.distrito_origen, lead.distrito_destino)
        return Response(shapes.quote_request_detail(
            solicitud, technical=technical, frequent_route=frequent,
        ))


class QuoteRequestAssignView(_Base):
    def post(self, request, pk):
        from apps.cotizador.commercial import SolicitudOcupada, asignar_solicitud

        get_object_or_404(_quote_request_qs(), pk=pk)
        try:
            solicitud = asignar_solicitud(pk, request.user)
        except SolicitudOcupada as exc:
            raise ValidationError(exc.messages[0])
        return Response(shapes.quote_request_item(solicitud))


class QuoteRequestQuoteView(_Base):
    """Guarda un borrador de cotización (precio + condiciones). Toma la solicitud
    si aún no está asignada. Reutiliza commercial.guardar_borrador."""

    def post(self, request, pk):
        from apps.cotizador.commercial import (
            SolicitudOcupada, asignar_solicitud, guardar_borrador,
        )
        from apps.cotizador.services import cotizar_lead
        from apps.dashboard.views_quotes import _quote_message, _service_snapshot

        solicitud = get_object_or_404(_quote_request_qs(), pk=pk)
        lead = solicitud.lead
        d = request.data

        price = _decimal(d.get("price"), "precio", positive=True)
        cost = _decimal(d.get("cost"), "costo") if d.get("cost") not in (None, "") else None
        margin = _decimal(d.get("margin"), "margen") if d.get("margin") not in (None, "") else None
        validity = int(d.get("validityDays") or 7)
        if not 1 <= validity <= 90:
            raise ValidationError({"validityDays": "Entre 1 y 90 días."})
        message = (d.get("whatsappMessage") or "").strip() or _quote_message(lead, price, validity)
        authorize = bool(d.get("authorizeLowMargin")) and request.user.is_superuser

        try:
            asignar_solicitud(pk, request.user)
        except SolicitudOcupada as exc:
            raise ValidationError(exc.messages[0])

        technical = lead.cotizaciones.order_by("-fecha_creacion").first() or cotizar_lead(lead)
        cotizacion, revision = guardar_borrador(
            solicitud, request.user, price,
            snapshot_servicio=_service_snapshot(lead),
            precio_sugerido_min=technical.precio_min,
            precio_sugerido_max=technical.precio_max,
            costo_estimado=cost,
            margen_minimo_porcentaje=margin,
            condiciones=(d.get("conditions") or "").strip(),
            vigencia_dias=validity,
            observacion_interna=(d.get("internalNote") or "").strip(),
            mensaje_whatsapp=message,
            autoriza_bajo_margen=authorize,
        )
        return Response({"code": cotizacion.codigo, "revision": revision.numero, "price": float(revision.precio_final)})


class QuoteRequestSendView(_Base):
    """Envía la cotización al cliente por WhatsApp y la mueve a 'Cotizaciones'.

    Reutiliza el mismo camino de envío que el panel viejo (delivery.queue_revision_whatsapp)
    y marca la revisión como enviada (el asesor afirma el envío; el estado de
    entrega real vive aparte en EnvioCotizacion)."""

    def post(self, request, pk):
        from apps.cotizador.commercial import marcar_revision_enviada
        from apps.cotizador.delivery import queue_revision_whatsapp

        solicitud = get_object_or_404(_quote_request_qs(), pk=pk)
        borrador = solicitud.cotizaciones.filter(estado="borrador").order_by("-creada_en").first()
        revision = borrador.revisiones.order_by("-numero").first() if borrador else None
        if revision is None:
            raise ValidationError("No hay un borrador de cotización para enviar.")

        queue_revision_whatsapp(revision.id, actor=request.user)
        marcar_revision_enviada(revision)
        return Response({"ok": True, "code": borrador.codigo})


def _decimal(value, label, *, positive=False):
    from decimal import Decimal, InvalidOperation
    try:
        n = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValidationError({label: f"Ingresa un {label} válido."})
    if positive and n <= 0:
        raise ValidationError({label: f"El {label} debe ser mayor que cero."})
    return n


# --------------------------------------------------------------------------- #
#  Cotizaciones
# --------------------------------------------------------------------------- #

from apps.cotizador.models import CotizacionComercial  # noqa: E402

_QUOTE_VISIBLE_QS_STATES = ("enviada", "entregada", "en_negociacion", "aceptada", "rechazada", "vencida")


def _quote_qs():
    return (
        CotizacionComercial.objects
        .filter(estado__in=_QUOTE_VISIBLE_QS_STATES)
        .select_related("lead__cliente", "asesor")
        .prefetch_related("revisiones")
    )


class QuoteListView(_Base):
    def get(self, request):
        qs = _quote_qs().order_by("-actualizada_en")
        state = (request.query_params.get("state") or "").strip()
        if state and state in shapes.QUOTE_STATE_ES:
            qs = qs.filter(estado=shapes.QUOTE_STATE_ES[state])
        search = (request.query_params.get("search") or "").strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(codigo__icontains=search)
                | Q(lead__cliente__nombre__icontains=search)
                | Q(lead__distrito_origen__icontains=search)
                | Q(lead__distrito_destino__icontains=search)
            )
        return self._paginate(qs, shapes.quote_item)


class QuoteDetailView(_Base):
    def get(self, request, pk):
        cot = get_object_or_404(_quote_qs(), pk=pk)
        return Response(shapes.quote_detail(cot))


class QuoteStateView(_Base):
    def post(self, request, pk):
        from apps.cotizador.commercial import cambiar_estado_cotizacion

        target = (request.data.get("state") or "").strip()
        if target not in shapes.QUOTE_STATE_ES:
            raise ValidationError({"state": "Estado no reconocido."})
        cot = cambiar_estado_cotizacion(pk, shapes.QUOTE_STATE_ES[target])
        return Response(shapes.quote_item(cot))


class QuoteReviseView(_Base):
    """Nueva revisión (nuevo precio) sobre una cotización ya enviada, y la reenvía."""

    def post(self, request, pk):
        from apps.cotizador.commercial import crear_revision, marcar_revision_enviada
        from apps.cotizador.delivery import queue_revision_whatsapp
        from apps.dashboard.views_quotes import _quote_message

        cot = get_object_or_404(_quote_qs(), pk=pk)
        d = request.data
        price = _decimal(d.get("price"), "precio", positive=True)
        validity = int(d.get("validityDays") or 7)
        message = (d.get("whatsappMessage") or "").strip() or _quote_message(cot.lead, price, validity)
        revision = crear_revision(
            cot, request.user, price,
            condiciones=(d.get("conditions") or "").strip(),
            vigencia_dias=validity,
            mensaje_whatsapp=message,
        )
        queue_revision_whatsapp(revision.id, actor=request.user)
        marcar_revision_enviada(revision)
        return Response(shapes.quote_detail(get_object_or_404(_quote_qs(), pk=pk)))


class QuoteAcceptView(_Base):
    """El asesor registra que el cliente aceptó (por WhatsApp). Marca la
    cotización 'aceptada' y crea la Reserva. Reutiliza crear_servicio_desde_lead
    (la misma función que usará el bot si algún día detecta la aceptación)."""

    def post(self, request, pk):
        from django.db import transaction

        from apps.cotizador.commercial import cambiar_estado_cotizacion
        from apps.cotizador.pipeline import _auditar
        from apps.servicios.services import crear_servicio_desde_lead

        from apps.ia.conversation_policy import booking_missing_fields

        cot = get_object_or_404(
            CotizacionComercial.objects.select_related("lead"), pk=pk,
        )
        if cot.estado not in ("enviada", "entregada", "en_negociacion", "aceptada"):
            raise ValidationError("Esta cotización no se puede aceptar en su estado actual.")

        missing = booking_missing_fields(cot.lead)
        if missing:
            raise ValidationError(
                "Faltan datos obligatorios para crear la reserva ("
                + ", ".join(missing)
                + "). Complétalos en el lead antes de aceptar."
            )

        with transaction.atomic():
            if cot.estado != "aceptada":
                cambiar_estado_cotizacion(cot.id, "aceptada")
            servicio, created = crear_servicio_desde_lead(
                cot.lead, usuario=request.user, require_accepted_revision=True,
            )
            _auditar(cot.lead, request.user, "cotizacion_aceptada",
                     {"cotizacion": cot.codigo, "reserva": servicio.codigo})

        return Response({
            "ok": True, "bookingCode": servicio.codigo, "bookingId": servicio.id,
            "created": created,
        })


# --------------------------------------------------------------------------- #
#  Reservas
# --------------------------------------------------------------------------- #

from apps.servicios.models import Servicio  # noqa: E402


def _booking(pk):
    return get_object_or_404(
        Servicio.objects.select_related("cliente", "asesor", "lead_origen"), pk=pk,
    )


class BookingListView(_Base):
    def get(self, request):
        from apps.servicios.services import bookings_queryset
        return self._paginate(bookings_queryset(request.query_params), shapes.booking_item)


class BookingDetailView(_Base):
    def get(self, request, pk):
        return Response(shapes.booking_detail(_booking(pk)))

    def patch(self, request, pk):
        servicio = _booking(pk)
        editable = {
            "serviceDate": "fecha_servicio", "schedule": "horario_servicio",
            "addressOrigin": "direccion_origen", "addressDestination": "direccion_destino",
            "notes": "observaciones",
        }
        changed = []
        for api_key, field in editable.items():
            if api_key in request.data:
                setattr(servicio, field, request.data[api_key] or "")
                changed.append(field)
        if changed:
            servicio.save(update_fields=changed + ["fecha_actualizacion"])
        return Response(shapes.booking_detail(servicio))


class BookingPaymentView(_Base):
    def post(self, request, pk):
        from apps.servicios.services import registrar_pago
        d = request.data
        registrar_pago(
            _booking(pk),
            concepto=d.get("concept") or "parcial",
            metodo_pago=d.get("method") or "yape",
            monto=d.get("amount"),
            usuario=request.user,
            observaciones=d.get("note") or "",
        )
        return Response(shapes.booking_detail(_booking(pk)))


class BookingFinalizeView(_Base):
    def post(self, request, pk):
        from apps.servicios.services import finalizar_servicio
        d = request.data
        finalizar_servicio(
            _booking(pk), request.user,
            monto_final=d.get("finalAmount"),
            metodo_final=d.get("method") or "yape",
            observaciones=d.get("note") or "",
        )
        return Response(shapes.booking_detail(_booking(pk)))


class BookingCancelView(_Base):
    def post(self, request, pk):
        from apps.servicios.services import cancelar_servicio
        cancelar_servicio(_booking(pk), request.user, request.data.get("reason"))
        return Response(shapes.booking_detail(_booking(pk)))


class BookingSetModeView(_Base):
    """Cambia la modalidad de ejecución (nuestro equipo ↔ transportistas).
    Solo mientras la reserva no esté asignada a un conductor."""
    def post(self, request, pk):
        from apps.servicios.models import Servicio

        servicio = _booking(pk)
        mode = (request.data.get("mode") or "").strip()
        if mode not in (Servicio.MODALIDAD_PROPIO, Servicio.MODALIDAD_TERCERIZADO):
            return Response({"error": "Modalidad no válida."}, status=400)
        if servicio.programaciones.filter(conductor__isnull=False).exists():
            return Response(
                {"error": "Ya está asignada a un conductor; primero quitá la asignación."},
                status=409,
            )
        servicio.modalidad_ejecucion = mode
        servicio.save(update_fields=["modalidad_ejecucion"])
        return Response(shapes.booking_detail(servicio))
