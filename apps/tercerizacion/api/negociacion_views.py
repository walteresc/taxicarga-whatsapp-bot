"""API v2 · Negociaciones (F2).

    GET  /api/v2/negotiations/                     lista de hilos (filtros: type, state, search)
    GET  /api/v2/negotiations/<pk>/                hilo + mensajes + hilo hermano + margen
    POST /api/v2/negotiations/<pk>/messages        {text?, proposalAmount?, sender?, channel?}
    POST /api/v2/negotiations/messages/<pk>/respond {action: accept|counter|reject, amount?, text?}
    POST /api/v2/negotiations/<pk>/pause           {reason?}
    POST /api/v2/negotiations/<pk>/resume
    POST /api/v2/negotiations/<pk>/close           {agreement: bool}
"""
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.pagination import StandardPagination
from apps.api.permissions import HasAnyRole, puede_ver_margen
from apps.tercerizacion import negociacion as neg
from apps.tercerizacion.models import HiloNegociacion, MensajeNegociacion

# Asesor de Ventas entra pero solo ve los hilos de venta (el gate de compra/margen
# está en la vista). Gerencia/Despacho/Finanzas ven todo.
_ROLES = ("Administrador", "Gerencia", "Supervisor", "Asesor de Ventas", "Despacho", "Finanzas")

_STATE_EN = {
    "abierta": "open", "pausada": "paused", "acuerdo": "agreement",
    "sin_acuerdo": "no_agreement", "cerrada": "closed",
}
_TYPE_EN = {"venta": "sale", "compra": "purchase"}
_TYPE_ES = {v: k for k, v in _TYPE_EN.items()}
_SENDER_EN = {
    "cliente": "client", "taxicarga": "taxicarga",
    "transportista": "carrier", "sistema": "system",
}
_SENDER_ES = {v: k for k, v in _SENDER_EN.items()}
_PROP_EN = {
    "pendiente": "pending", "aceptada": "accepted",
    "contraofertada": "countered", "rechazada": "rejected", "": None,
}


def _d(dt):
    return dt.isoformat() if dt else None


def _num(v):
    return float(v) if v is not None else None


def _counterparty_name(hilo):
    if hilo.contraparte:
        return hilo.contraparte.profile_name or hilo.contraparte.nombre or "—"
    return "Cliente" if hilo.tipo == HiloNegociacion.TIPO_VENTA else "Transportista (pendiente)"


def _route(lead):
    return f"{lead.distrito_origen or '?'} → {lead.distrito_destino or '?'}"


def hilo_item(hilo):
    last = hilo.mensajes.order_by("-creado_en").first()
    return {
        "id": hilo.id,
        "leadId": hilo.lead_id,
        "code": hilo.lead.codigo or f"L{hilo.lead_id}",
        "type": _TYPE_EN[hilo.tipo],
        "state": _STATE_EN.get(hilo.estado, hilo.estado),
        "counterpartyName": _counterparty_name(hilo),
        "route": _route(hilo.lead),
        "targetAmount": _num(hilo.monto_objetivo),
        "currentAmount": _num(hilo.monto_actual),
        "agreedAmount": _num(hilo.monto_acordado),
        "pauseReason": hilo.motivo_pausa or None,
        "publicationCode": hilo.publicacion.codigo if hilo.publicacion_id else None,
        "lastMessageAt": _d(last.creado_en) if last else _d(hilo.actualizado_en),
        "lastMessagePreview": (last.texto or (f"Propuesta S/ {last.propuesta_monto:g}" if last and last.propuesta_monto is not None else "")) if last else "",
        "updatedAt": _d(hilo.actualizado_en),
    }


def mensaje_item(m):
    return {
        "id": m.id,
        "sender": _SENDER_EN.get(m.emisor, m.emisor),
        "authorName": (m.autor.get_full_name() or m.autor.username) if m.autor_id else None,
        "channel": m.canal,
        "kind": m.tipo,
        "text": m.texto,
        "proposalAmount": _num(m.propuesta_monto),
        "proposalState": _PROP_EN.get(m.propuesta_estado, m.propuesta_estado or None),
        "createdAt": _d(m.creado_en),
    }


def hilo_detail(hilo, *, ver_margen=True):
    out = hilo_item(hilo)
    out["messages"] = [mensaje_item(m) for m in hilo.mensajes.select_related("autor").order_by("creado_en")]
    out["canSeeMargin"] = ver_margen
    if not ver_margen:
        out["siblings"] = []
        out["margin"] = None
        return out
    sibling_type = (
        HiloNegociacion.TIPO_COMPRA if hilo.tipo == HiloNegociacion.TIPO_VENTA
        else HiloNegociacion.TIPO_VENTA
    )
    siblings = HiloNegociacion.objects.filter(lead_id=hilo.lead_id, tipo=sibling_type)
    out["siblings"] = [
        {
            "id": s.id, "type": _TYPE_EN[s.tipo], "state": _STATE_EN.get(s.estado, s.estado),
            "counterpartyName": _counterparty_name(s),
            "currentAmount": _num(s.monto_actual), "agreedAmount": _num(s.monto_acordado),
        }
        for s in siblings
    ]
    out["margin"] = neg.margen_en_vivo(hilo.lead)
    return out


class _Base(APIView):
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_exception_handler(self):
        return api_exception_handler

    def _ver_margen(self):
        return puede_ver_margen(self.request.user)

    def _guard(self, hilo):
        if hilo.tipo == HiloNegociacion.TIPO_COMPRA and not self._ver_margen():
            raise PermissionDenied("No tenés acceso a las negociaciones de compra.")

    def _detail(self, hilo):
        return hilo_detail(hilo, ver_margen=self._ver_margen())


_HILO_QS = HiloNegociacion.objects.select_related(
    "lead", "contraparte", "publicacion", "cotizacion",
)


class NegotiationListView(_Base):
    def get(self, request):
        p = request.query_params
        qs = _HILO_QS
        if not puede_ver_margen(request.user):
            qs = qs.filter(tipo=HiloNegociacion.TIPO_VENTA)
        t = p.get("type")
        if t in _TYPE_ES:
            qs = qs.filter(tipo=_TYPE_ES[t])
        st = p.get("state")
        es_state = {v: k for k, v in _STATE_EN.items()}.get(st)
        if es_state:
            qs = qs.filter(estado=es_state)
        elif p.get("active") == "true":
            qs = qs.filter(estado__in=["abierta", "pausada", "acuerdo", "sin_acuerdo"])
        search = (p.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(lead__codigo__icontains=search)
                | Q(lead__distrito_origen__icontains=search)
                | Q(lead__distrito_destino__icontains=search)
                | Q(contraparte__nombre__icontains=search)
                | Q(publicacion__codigo__icontains=search)
            )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs.order_by("-actualizado_en"), request, view=self)
        return paginator.get_paginated_response([hilo_item(h) for h in page])


class NegotiationDetailView(_Base):
    def get(self, request, pk):
        hilo = get_object_or_404(_HILO_QS, pk=pk)
        self._guard(hilo)
        return Response(self._detail(hilo))


class NegotiationMessagesView(_Base):
    def post(self, request, pk):
        hilo = get_object_or_404(_HILO_QS, pk=pk)
        self._guard(hilo)
        d = request.data
        sender = _SENDER_ES.get(d.get("sender") or "taxicarga")
        if sender not in ("cliente", "taxicarga", "transportista"):
            raise ValidationError("Emisor no válido.")
        text = (d.get("text") or "").strip()
        amount = _parse_amount(d.get("proposalAmount"))
        if not text and amount is None:
            raise ValidationError("El mensaje está vacío.")
        channel = d.get("channel") or MensajeNegociacion.CANAL_CRM
        if channel not in dict(MensajeNegociacion.CANALES):
            channel = MensajeNegociacion.CANAL_CRM
        try:
            neg.publicar_mensaje(
                hilo, emisor=sender, texto=text, autor=request.user,
                canal=channel, propuesta_monto=amount,
            )
        except neg.NegociacionError as e:
            raise ValidationError(str(e))
        hilo.refresh_from_db()
        return Response(self._detail(hilo))


class NegotiationRespondView(_Base):
    def post(self, request, pk):
        mensaje = get_object_or_404(
            MensajeNegociacion.objects.select_related("hilo", "hilo__lead"), pk=pk,
        )
        self._guard(mensaje.hilo)
        d = request.data
        action_map = {"accept": "aceptar", "counter": "contraofertar", "reject": "rechazar"}
        accion = action_map.get(d.get("action"))
        if not accion:
            raise ValidationError("Acción no válida.")
        monto = _parse_amount(d.get("amount"))
        try:
            neg.responder_propuesta(
                mensaje, accion, usuario=request.user, monto=monto,
                texto=(d.get("text") or "").strip(),
            )
        except neg.NegociacionError as e:
            raise ValidationError(str(e))
        return Response(self._detail(get_object_or_404(_HILO_QS, pk=mensaje.hilo_id)))


class NegotiationPauseView(_Base):
    def post(self, request, pk):
        hilo = get_object_or_404(_HILO_QS, pk=pk)
        self._guard(hilo)
        try:
            neg.pausar_hilo(hilo, request.user, (request.data.get("reason") or "").strip())
        except neg.NegociacionError as e:
            raise ValidationError(str(e))
        return Response(self._detail(hilo))


class NegotiationResumeView(_Base):
    def post(self, request, pk):
        hilo = get_object_or_404(_HILO_QS, pk=pk)
        self._guard(hilo)
        try:
            neg.reanudar_hilo(hilo, request.user)
        except neg.NegociacionError as e:
            raise ValidationError(str(e))
        return Response(self._detail(hilo))


class NegotiationCloseView(_Base):
    def post(self, request, pk):
        hilo = get_object_or_404(_HILO_QS, pk=pk)
        self._guard(hilo)
        agreement = bool(request.data.get("agreement"))
        neg.cerrar_hilo(hilo, request.user, con_acuerdo=agreement)
        return Response(self._detail(hilo))


def _parse_amount(raw):
    if raw in (None, ""):
        return None
    try:
        from decimal import Decimal
        v = Decimal(str(raw))
    except Exception:
        raise ValidationError("Monto no válido.")
    if v <= 0:
        raise ValidationError("El monto debe ser mayor que cero.")
    return v
