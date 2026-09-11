"""API v2 (interna, CRM) para administrar socios comerciales y sus llaves.
Distinta de `apps/partners/api/views.py`, que es la API pública que consume el
socio con su ApiKey."""
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.permissions import HasAnyRole
from apps.partners.models import ApiKey, SocioComercial, WebhookDelivery

_ROLES = ("Administrador", "Gerencia")


def _d(v):
    return v.isoformat() if v else None


def _key_item(k):
    return {"id": k.id, "environment": k.entorno, "prefix": k.prefix, "active": k.activa,
            "lastUsedAt": _d(k.ultimo_uso_en), "createdAt": _d(k.creado_en)}


def _item(s):
    return {
        "id": s.id, "name": s.nombre, "contactName": s.contacto_nombre, "contactEmail": s.contacto_email,
        "contactPhone": s.contacto_telefono, "active": s.activo, "balance": float(s.saldo),
        "webhookUrl": s.webhook_url, "shipmentCount": s.envios.count(), "createdAt": _d(s.creado_en),
    }


def _detail(s):
    out = _item(s)
    out["keys"] = [_key_item(k) for k in s.api_keys.order_by("-creado_en")]
    out["recentWebhooks"] = [
        {"event": w.evento, "state": w.estado, "code": w.ultimo_codigo, "at": _d(w.creado_en)}
        for w in s.webhooks.order_by("-creado_en")[:20]
    ]
    return out


class _Base(APIView):
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_exception_handler(self):
        return api_exception_handler


class PartnerListView(_Base):
    def get(self, request):
        return Response({"results": [_item(s) for s in SocioComercial.objects.order_by("nombre")]})

    def post(self, request):
        d = request.data
        if not (d.get("name") or "").strip():
            raise ValidationError({"name": "Requerido."})
        s = SocioComercial.objects.create(
            nombre=d["name"].strip(), contacto_nombre=(d.get("contactName") or "").strip(),
            contacto_email=(d.get("contactEmail") or "").strip(), contacto_telefono=(d.get("contactPhone") or "").strip(),
            webhook_url=(d.get("webhookUrl") or "").strip(), creado_por=request.user,
        )
        return Response(_detail(s), status=201)


class PartnerDetailView(_Base):
    def get(self, request, pk):
        return Response(_detail(get_object_or_404(SocioComercial, pk=pk)))

    def patch(self, request, pk):
        s = get_object_or_404(SocioComercial, pk=pk)
        d = request.data
        campos = []
        for api_f, model_f in (("name", "nombre"), ("contactName", "contacto_nombre"),
                               ("contactEmail", "contacto_email"), ("contactPhone", "contacto_telefono"),
                               ("webhookUrl", "webhook_url")):
            if api_f in d:
                setattr(s, model_f, (d[api_f] or "").strip())
                campos.append(model_f)
        if "active" in d:
            s.activo = bool(d["active"])
            campos.append("activo")
        if campos:
            s.save(update_fields=campos + ["actualizado_en"])
        return Response(_detail(s))


class PartnerKeyListView(_Base):
    def post(self, request, pk):
        s = get_object_or_404(SocioComercial, pk=pk)
        entorno = request.data.get("environment") or ApiKey.ENTORNO_TEST
        if entorno not in dict(ApiKey.ENTORNOS):
            raise ValidationError({"environment": "Debe ser 'test' o 'live'."})
        key, token = ApiKey.generar(s, entorno=entorno)
        out = _key_item(key)
        out["token"] = token  # única vez que se muestra
        return Response(out, status=201)


class PartnerKeyRevokeView(_Base):
    def post(self, request, pk, key_id):
        key = get_object_or_404(ApiKey, pk=key_id, socio_id=pk)
        key.activa = False
        key.save(update_fields=["activa"])
        return Response({"ok": True})
