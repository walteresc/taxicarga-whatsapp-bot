"""API v2 · Portal del Transportista (F5).

Todo bajo /api/v2/portal/carrier/*. Permiso IsCarrier: el usuario tiene una
ficha `Transportista` activa enlazada (grupo 'Transportista'). Cada queryset se
acota a `self.carrier`. NUNCA se expone el objeto Servicio/Lead crudo: lo único
que se muestra de una carga sale de `lineas_detalle_permitido()` (lista blanca de
privacidad) y de un puñado de campos de esa misma lista. El precio visible es el
`precio_publicado` (costo objetivo), jamás el precio de venta al cliente.

    GET  me
    GET  loads                         cargas disponibles para ofertar
    POST loads/<code>/offer            {amount, vehicleId?, note?}
    GET  offers                        mis ofertas
    GET  assignments                   mis servicios adjudicados
    GET  negotiations                  mis mesas de compra
    GET  negotiations/<pk>/
    POST negotiations/<pk>/messages    {text?, proposalAmount?}
    POST negotiations/messages/<pk>/respond   {action, amount?}
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.permissions import IsCarrier, carrier_for
from apps.campo.models import ProgramacionServicio
from apps.tercerizacion import adjudicacion as adj
from apps.tercerizacion import negociacion as neg
from apps.tercerizacion.models import (
    HiloNegociacion, MensajeNegociacion, OfertaTransportista, PublicacionCarga,
)
from apps.tercerizacion.services import lineas_detalle_permitido

_LOADS_ABIERTAS = (
    PublicacionCarga.ESTADO_ABIERTA,
    PublicacionCarga.ESTADO_PUBLICADA,
    PublicacionCarga.ESTADO_CON_OFERTAS,
)
_OFFER_STATE_EN = {
    "pendiente": "pending", "contraoferta_taxicarga": "countered_us",
    "contraoferta_transportista": "countered_you", "aceptada": "accepted",
    "rechazada": "rejected", "retirada": "withdrawn", "vencida": "expired",
}
_HILO_STATE_EN = {
    "abierta": "open", "pausada": "paused", "acuerdo": "agreement",
    "sin_acuerdo": "no_agreement", "cerrada": "closed",
}
_PRICE_MODE_EN = {"fijo": "fixed", "referencial": "reference", "abierto": "open"}
_PROP_EN = {"pendiente": "pending", "aceptada": "accepted",
            "contraofertada": "countered", "rechazada": "rejected", "": None}


def _d(dt):
    return dt.isoformat() if dt else None


def _num(v):
    return float(v) if v is not None else None


def _amount(raw):
    if raw in (None, ""):
        return None
    try:
        v = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        raise ValidationError({"amount": "Monto no válido."})
    if v <= 0:
        raise ValidationError({"amount": "El monto debe ser mayor que cero."})
    return v


def _safe_load(pub, mi_oferta=None):
    """Vista de una carga SIN datos del cliente. Fuente única: la lista blanca."""
    s = pub.servicio
    return {
        "code": pub.codigo,
        "priceMode": _PRICE_MODE_EN.get(pub.modo_precio, pub.modo_precio),
        "targetPrice": _num(pub.precio_publicado),
        "origin": s.distrito_origen or "",
        "destination": s.distrito_destino or "",
        "serviceType": s.tipo_servicio or "",
        "date": _d(s.fecha_servicio),
        "lines": lineas_detalle_permitido(s),
        "myOfferId": mi_oferta.id if mi_oferta else None,
        "myOfferAmount": _num(mi_oferta.monto_actual or mi_oferta.precio_ofertado) if mi_oferta else None,
        "myOfferState": _OFFER_STATE_EN.get(mi_oferta.estado) if mi_oferta else None,
    }


class _Portal(APIView):
    permission_classes = [IsCarrier]

    def get_exception_handler(self):
        return api_exception_handler

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.carrier = carrier_for(request.user)


class CarrierMeView(_Portal):
    def get(self, request):
        c = self.carrier
        return Response({
            "id": c.id, "name": c.nombre, "active": c.activo,
            "vehicleCount": c.vehiculos.filter(activo=True).count(),
            "driverCount": c.conductores.filter(activo=True).count(),
        })


def _vehicle_item(v):
    return {
        "id": v.id, "plate": v.placa, "brand": v.marca, "model": v.modelo, "year": v.anio,
        # 3 cupos fijos: null = todavía sin foto en ese cupo.
        "photos": [
            f"/api/v2/portal/carrier/vehicles/{v.id}/photo/{n}" if getattr(v, f"foto_{n}") else None
            for n in (1, 2, 3)
        ],
    }


class CarrierVehiclesView(_Portal):
    """Mis vehículos — para elegir a cuál subirle fotos."""

    def get(self, request):
        vehicles = self.carrier.vehiculos.filter(activo=True).order_by("placa")
        return Response({"results": [_vehicle_item(v) for v in vehicles]})


class CarrierVehiclePhotosView(_Portal):
    """Subir/reemplazar hasta 3 fotos del propio vehículo. Multipart con
    cualquier subconjunto de `photo1`/`photo2`/`photo3` — los cupos no
    incluidos quedan como estaban."""

    def post(self, request, pk):
        vehiculo = get_object_or_404(self.carrier.vehiculos, pk=pk)
        campos = []
        for n in (1, 2, 3):
            archivo = request.FILES.get(f"photo{n}")
            if archivo:
                setattr(vehiculo, f"foto_{n}", archivo)
                campos.append(f"foto_{n}")
        if not campos:
            raise ValidationError("Mandá al menos una foto (photo1, photo2 o photo3).")
        vehiculo.save(update_fields=campos)
        return Response(_vehicle_item(vehiculo))


class CarrierVehiclePhotoView(_Portal):
    def get(self, request, pk, slot):
        from django.http import FileResponse, Http404

        vehiculo = get_object_or_404(self.carrier.vehiculos, pk=pk)
        campo = getattr(vehiculo, f"foto_{slot}", None) if slot in (1, 2, 3) else None
        if not campo:
            raise Http404("Sin foto en ese cupo.")
        resp = FileResponse(campo.open("rb"))
        resp["Cache-Control"] = "private, max-age=86400"
        return resp


class CarrierLoadsView(_Portal):
    def get(self, request):
        mis_ofertas = {
            o.publicacion_id: o
            for o in OfertaTransportista.objects.filter(transportista=self.carrier)
        }
        pubs = (
            PublicacionCarga.objects
            .filter(estado__in=_LOADS_ABIERTAS)
            .select_related("servicio")
            .order_by("-creado_en")
        )
        out = []
        for pub in pubs:
            visible = pub.alcance == PublicacionCarga.ALCANCE_TODOS or pub.id in mis_ofertas
            if visible:
                out.append(_safe_load(pub, mis_ofertas.get(pub.id)))
        return Response({"results": out})


class CarrierOfferView(_Portal):
    def post(self, request, code):
        pub = get_object_or_404(
            PublicacionCarga.objects.select_related("servicio"), codigo=code,
        )
        if pub.estado not in _LOADS_ABIERTAS:
            raise ValidationError("Esta carga ya no recibe ofertas.")
        if pub.alcance != PublicacionCarga.ALCANCE_TODOS and not pub.ofertas.filter(transportista=self.carrier).exists():
            raise ValidationError("Esta carga no está disponible para vos.")

        amount = _amount(request.data.get("amount"))
        if pub.modo_precio == PublicacionCarga.PRECIO_FIJO:
            amount = pub.precio_publicado  # precio cerrado: solo se acepta
            if amount is None:
                raise ValidationError("La carga tiene precio fijo pero sin monto — avisá al despacho.")
        elif amount is None:
            raise ValidationError({"amount": "Ingresá tu monto."})

        vehiculo = None
        if request.data.get("vehicleId"):
            vehiculo = self.carrier.vehiculos.filter(pk=request.data["vehicleId"]).first()
            if vehiculo is None:
                raise ValidationError({"vehicleId": "Ese vehículo no es tuyo."})

        try:
            adj.registrar_oferta(
                pub, monto=amount, usuario=request.user, transportista=self.carrier,
                transportista_vehiculo=vehiculo,
                nota=(request.data.get("note") or "").strip(),
                canal=MensajeNegociacion.CANAL_PORTAL,
            )
        except adj.AdjudicacionError as e:
            raise ValidationError(str(e))
        oferta = pub.ofertas.get(transportista=self.carrier)
        return Response(_safe_load(pub, oferta))


class CarrierOffersView(_Portal):
    def get(self, request):
        ofertas = (
            OfertaTransportista.objects
            .filter(transportista=self.carrier)
            .select_related("publicacion", "publicacion__servicio")
            .order_by("-creado_en")
        )
        return Response({"results": [
            {
                "id": o.id,
                "publicationCode": o.publicacion.codigo,
                "origin": o.publicacion.servicio.distrito_origen or "",
                "destination": o.publicacion.servicio.distrito_destino or "",
                "date": _d(o.publicacion.servicio.fecha_servicio),
                "firstAmount": _num(o.precio_ofertado),
                "currentAmount": _num(o.monto_actual or o.precio_ofertado),
                "state": _OFFER_STATE_EN.get(o.estado, o.estado),
                "createdAt": _d(o.creado_en),
            }
            for o in ofertas
        ]})


class CarrierAssignmentsView(_Portal):
    def get(self, request):
        progs = (
            ProgramacionServicio.objects
            .filter(transportista=self.carrier)
            .exclude(estado_operativo=ProgramacionServicio.ESTADO_CANCELADO)
            .select_related("servicio", "transportista_vehiculo")
            .order_by("-fecha")
        )
        return Response({"results": [
            {
                "id": p.id,
                "code": p.servicio.codigo,
                "date": _d(p.fecha),
                "start": p.hora_inicio.strftime("%H:%M") if p.hora_inicio else None,
                "vehiclePlate": p.transportista_vehiculo.placa if p.transportista_vehiculo_id else None,
                "amount": _num(p.monto),
                "operationalState": p.estado_operativo,
                "origin": p.servicio.distrito_origen or "",
                "destination": p.servicio.distrito_destino or "",
                "lines": lineas_detalle_permitido(p.servicio),
            }
            for p in progs
        ]})


class CarrierEarningsView(_Portal):
    """Mis cobros: lo que la plataforma te va a pagar (o lo que le debés) por los
    servicios tercerizados que ejecutaste. Nunca muestra el precio de venta al
    cliente ni la comisión — solo tu neto."""

    def get(self, request):
        from apps.tercerizacion.liquidaciones import resumen_transportista
        from apps.tercerizacion.models import Liquidacion

        qs = (
            Liquidacion.objects
            .filter(transportista=self.carrier)
            .exclude(estado=Liquidacion.ESTADO_ANULADA)
            .select_related("servicio")
            .order_by("-creado_en")
        )
        _STATE_EN = {"pendiente": "pending", "conciliada": "confirmed", "pagada": "settled"}
        rows = [{
            "id": l.id,
            "serviceCode": l.servicio.codigo,
            "route": f"{l.servicio.distrito_origen or '?'} → {l.servicio.distrito_destino or '?'}",
            "date": _d(l.servicio.fecha_servicio),
            # el transportista ve SU neto, con signo: + le pagan, - debe
            "amount": _num(l.neto),
            "youOwe": l.neto < 0,
            "state": _STATE_EN.get(l.estado, l.estado),
            "settledOn": _d(l.fecha_liquidacion),
            "paymentRef": l.referencia_pago or None,
        } for l in qs]
        return Response({"summary": resumen_transportista(self.carrier), "results": rows})


class CarrierPayoutView(_Portal):
    """GET/PATCH los datos de cobro del propio transportista (a dónde le paga
    la plataforma)."""

    _MAP = {
        "bank": "pago_banco", "accountType": "pago_tipo_cuenta", "account": "pago_numero_cuenta",
        "cci": "pago_cci", "holder": "pago_titular", "yape": "pago_yape",
    }

    def _payload(self):
        c = self.carrier
        return {k: getattr(c, f) for k, f in self._MAP.items()}

    def get(self, request):
        return Response(self._payload())

    def patch(self, request):
        c = self.carrier
        campos = []
        for k, f in self._MAP.items():
            if k in request.data:
                setattr(c, f, (request.data[k] or "").strip())
                campos.append(f)
        if "cci" in request.data and c.pago_cci and not c.pago_cci.isdigit():
            raise ValidationError({"cci": "El CCI son solo dígitos (20)."})
        if campos:
            c.save(update_fields=campos + ["actualizado_en"])
        return Response(self._payload())


def _carrier_msg(m):
    sender = {
        MensajeNegociacion.EMISOR_TRANSPORTISTA: "you",
        MensajeNegociacion.EMISOR_TAXICARGA: "taxicarga",
        MensajeNegociacion.EMISOR_SISTEMA: "system",
    }.get(m.emisor, "taxicarga")
    return {
        "id": m.id,
        "sender": sender,
        "text": m.texto,
        "proposalAmount": _num(m.propuesta_monto),
        "proposalState": _PROP_EN.get(m.propuesta_estado, m.propuesta_estado or None),
        "proposalFromTaxicarga": m.emisor == MensajeNegociacion.EMISOR_TAXICARGA,
        "createdAt": _d(m.creado_en),
    }


def _carrier_hilo(hilo, *, with_messages=False):
    out = {
        "id": hilo.id,
        "publicationCode": hilo.publicacion.codigo if hilo.publicacion_id else None,
        "state": _HILO_STATE_EN.get(hilo.estado, hilo.estado),
        "currentAmount": _num(hilo.monto_actual),
        "agreedAmount": _num(hilo.monto_acordado),
        "targetPrice": _num(hilo.monto_objetivo),
        "paused": hilo.estado == HiloNegociacion.ESTADO_PAUSADA,
        "updatedAt": _d(hilo.actualizado_en),
    }
    if with_messages:
        out["messages"] = [
            _carrier_msg(m) for m in hilo.mensajes.order_by("creado_en")
            if m.emisor != MensajeNegociacion.EMISOR_CLIENTE
        ]
    return out


class _CarrierHilosBase(_Portal):
    def _hilo(self, pk):
        return get_object_or_404(
            HiloNegociacion.objects.select_related("publicacion").filter(
                tipo=HiloNegociacion.TIPO_COMPRA, transportista=self.carrier,
            ),
            pk=pk,
        )


class CarrierNegotiationsView(_CarrierHilosBase):
    def get(self, request):
        hilos = (
            HiloNegociacion.objects
            .filter(tipo=HiloNegociacion.TIPO_COMPRA, transportista=self.carrier)
            .select_related("publicacion")
            .order_by("-actualizado_en")
        )
        return Response({"results": [_carrier_hilo(h) for h in hilos]})


class CarrierNegotiationDetailView(_CarrierHilosBase):
    def get(self, request, pk):
        return Response(_carrier_hilo(self._hilo(pk), with_messages=True))


class CarrierNegotiationMessagesView(_CarrierHilosBase):
    def post(self, request, pk):
        hilo = self._hilo(pk)
        text = (request.data.get("text") or "").strip()
        amount = _amount(request.data.get("proposalAmount"))
        if not text and amount is None:
            raise ValidationError("El mensaje está vacío.")
        try:
            neg.publicar_mensaje(
                hilo, emisor=MensajeNegociacion.EMISOR_TRANSPORTISTA, autor=request.user,
                texto=text, canal=MensajeNegociacion.CANAL_PORTAL, propuesta_monto=amount,
            )
        except neg.NegociacionError as e:
            raise ValidationError(str(e))
        return Response(_carrier_hilo(self._hilo(pk), with_messages=True))


class CarrierNegotiationRespondView(_CarrierHilosBase):
    def post(self, request, pk):
        mensaje = get_object_or_404(
            MensajeNegociacion.objects.select_related("hilo"), pk=pk,
        )
        hilo = mensaje.hilo
        if hilo.tipo != HiloNegociacion.TIPO_COMPRA or hilo.transportista_id != self.carrier.id:
            raise ValidationError("Esa propuesta no es de una negociación tuya.")
        if mensaje.emisor != MensajeNegociacion.EMISOR_TAXICARGA:
            raise ValidationError("Solo podés responder propuestas de TaxiCarga.")
        action_map = {"accept": "aceptar", "counter": "contraofertar", "reject": "rechazar"}
        accion = action_map.get(request.data.get("action"))
        if not accion:
            raise ValidationError("Acción no válida.")
        try:
            neg.responder_propuesta(
                mensaje, accion, usuario=request.user,
                monto=_amount(request.data.get("amount")),
            )
        except neg.NegociacionError as e:
            raise ValidationError(str(e))
        return Response(_carrier_hilo(self._hilo(hilo.id), with_messages=True))
