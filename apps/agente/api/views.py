"""API v2 · Agente (G1).

    POST /api/v2/agent/ask                       {message, conversationId?}
    GET  /api/v2/agent/conversations/
    GET  /api/v2/agent/conversations/<id>/
    GET  /api/v2/agent/proposals/?estado=pendiente
    POST /api/v2/agent/proposals/<id>/apply
    POST /api/v2/agent/proposals/<id>/reject     {motivo?}
"""
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.agente.errores import CapacidadError
from apps.agente.models import ConversacionAgente, PropuestaAccion
from apps.agente.orquestador import Orquestador, aplicar_propuesta, rechazar_propuesta
from apps.agente.principal import (
    PrincipalNoResoluble, agente_habilitado_para, principal_desde_usuario,
)


class _AgentThrottle(ScopedRateThrottle):
    scope = "agent_ask"
    cache = caches["throttle"]


class _Base(APIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return api_exception_handler

    def _principal(self, request, *, exigir_habilitado=True):
        from rest_framework.exceptions import PermissionDenied
        try:
            principal = principal_desde_usuario(request.user)
        except PrincipalNoResoluble as e:
            raise PermissionDenied(str(e))
        if exigir_habilitado and not agente_habilitado_para(principal.tipo):
            raise PermissionDenied("El asistente no está habilitado para tu perfil.")
        return principal


def _d(dt):
    return dt.isoformat() if dt else None


def _conv_item(c):
    return {"id": c.id, "titulo": c.titulo, "principalTipo": c.principal_tipo,
            "cerrada": c.cerrada, "actualizadoEn": _d(c.actualizado_en)}


def _prop_item(p):
    return {
        "id": p.id, "capacidad": p.capacidad, "resumen": p.resumen,
        "estado": p.estado, "args": p.args,
        "creadoEn": _d(p.creado_en), "resueltaEn": _d(p.resuelta_en),
        "resueltaPor": p.resuelta_por.username if p.resuelta_por_id else None,
        "motivoRechazo": p.motivo_rechazo or None,
    }


class StatusView(_Base):
    """Le dice al frontend si mostrar el widget del agente."""

    def get(self, request):
        try:
            principal = self._principal(request, exigir_habilitado=False)
        except Exception:
            return Response({"enabled": False, "profile": None})
        return Response({
            "enabled": agente_habilitado_para(principal.tipo),
            "profile": principal.tipo,
        })


class AskView(_Base):
    throttle_classes = [_AgentThrottle]

    def post(self, request):
        principal = self._principal(request)
        mensaje = (request.data.get("message") or "").strip()
        if not mensaje:
            raise ValidationError("El mensaje está vacío.")

        conv = None
        if request.data.get("conversationId"):
            conv = ConversacionAgente.objects.filter(
                pk=request.data["conversationId"], usuario=request.user,
            ).first()
            if conv is None:
                raise ValidationError("Conversación no encontrada.")

        r = Orquestador(principal, conversacion=conv).responder(mensaje)
        return Response({
            "conversationId": r.conversacion_id,
            "reply": r.texto,
            "executed": r.ejecutadas,
            "proposals": r.propuestas,
            "iterations": r.iteraciones,
        })


class ConversationListView(_Base):
    def get(self, request):
        self._principal(request)
        qs = ConversacionAgente.objects.filter(usuario=request.user)[:50]
        return Response({"results": [_conv_item(c) for c in qs]})


class ConversationDetailView(_Base):
    def get(self, request, pk):
        self._principal(request)
        conv = get_object_or_404(ConversacionAgente, pk=pk, usuario=request.user)
        turnos = [
            {"rol": t.rol, "contenido": t.contenido, "toolCalls": t.tool_calls,
             "creadoEn": _d(t.creado_en)}
            for t in conv.turnos.order_by("creado_en")
        ]
        return Response({**_conv_item(conv), "turnos": turnos})


class ProposalListView(_Base):
    def get(self, request):
        self._principal(request)
        qs = PropuestaAccion.objects.filter(usuario=request.user)
        estado = request.query_params.get("estado")
        if estado:
            qs = qs.filter(estado=estado)
        return Response({"results": [_prop_item(p) for p in qs[:100]]})


class ProposalApplyView(_Base):
    def post(self, request, pk):
        self._principal(request)
        prop = get_object_or_404(PropuestaAccion, pk=pk, usuario=request.user)
        try:
            res = aplicar_propuesta(prop, request.user)
        except CapacidadError as e:
            raise ValidationError(str(e))
        prop.refresh_from_db()
        return Response({"ok": res.ok, "error": res.error or None,
                         "resultado": res.datos, "propuesta": _prop_item(prop)})


class ProposalRejectView(_Base):
    def post(self, request, pk):
        self._principal(request)
        prop = get_object_or_404(PropuestaAccion, pk=pk, usuario=request.user)
        try:
            rechazar_propuesta(prop, request.user, motivo=(request.data.get("motivo") or "").strip())
        except CapacidadError as e:
            raise ValidationError(str(e))
        prop.refresh_from_db()
        return Response({"ok": True, "propuesta": _prop_item(prop)})
