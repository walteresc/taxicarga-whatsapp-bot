"""API v2 · Portal del Cliente (F6, "Mionca").

Bajo /api/v2/portal/customer/*. Permiso IsPortalCustomer: el usuario tiene un
`ClienteUsuario` activo. Cada queryset se acota a `self.cu.cliente`.

El cliente ve TODO lo de su propia carga (lo que él cargó) y el estado del
servicio — incluido el transportista asignado — pero nunca el costo de compra
ni el margen. Si negocia, ve solo el hilo de venta.

    GET  me
    GET  loads                          mis cargas
    POST loads                          wizard: crea Lead + cotiza -> precio
    GET  loads/<code>                   detalle + precio + estado + seguimiento
    POST loads/<code>/accept            acepta el precio -> a 'Cotizados'
    POST loads/<code>/negotiate         "esperar mejores ofertas" -> hilo de venta
    GET  loads/<code>/negotiation
    POST loads/<code>/negotiation/messages          {text?, proposalAmount?}
    POST loads/<code>/negotiation/messages/<pk>/respond   {action, amount?}
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.permissions import IsPortalCustomer, customer_portal_for
from apps.cotizador.commercial import crear_cotizacion_portal
from apps.cotizador.services import cotizar_lead
from apps.leads.models import Lead
from apps.leads.route import replace_lead_route
from apps.tercerizacion import negociacion as neg
from apps.tercerizacion.models import HiloNegociacion, MensajeNegociacion

_HILO_STATE_EN = {
    "abierta": "open", "pausada": "paused", "acuerdo": "agreement",
    "sin_acuerdo": "no_agreement", "cerrada": "closed",
}
_PROP_EN = {"pendiente": "pending", "aceptada": "accepted",
            "contraofertada": "countered", "rechazada": "rejected", "": None}


def _d(v):
    return v.isoformat() if v else None


def _num(v):
    return float(v) if v is not None else None


def _amount(raw, *, required=False, field="amount"):
    if raw in (None, ""):
        if required:
            raise ValidationError({field: "Ingresá un monto."})
        return None
    try:
        v = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        raise ValidationError({field: "Monto no válido."})
    if v <= 0:
        raise ValidationError({field: "El monto debe ser mayor que cero."})
    return v


# --------------------------------------------------------------------------- #
#  Forma de una carga para el cliente
# --------------------------------------------------------------------------- #

def _load_status(lead):
    """Estado de alto nivel que ve el cliente."""
    servicio = getattr(lead, "servicio_generado", None)
    if servicio:
        prog = servicio.programaciones.exclude(estado_operativo="cancelado").first()
        if servicio.estado == "finalizado":
            return "completed"
        if prog:
            return "in_progress" if prog.estado_operativo in ("en_ruta", "en_servicio") else "scheduled"
        return "booked"
    cot = lead.cotizaciones_comerciales.order_by("-actualizada_en").first()
    if cot:
        if cot.estado == "en_negociacion":
            return "negotiating"
        if cot.estado == "aceptada":
            return "booked"
        return "quoted"
    tecnica = lead.cotizaciones.order_by("-fecha_creacion").first()
    if tecnica:
        return "quoted"
    return "draft"


def _price_view(lead):
    tecnica = lead.cotizaciones.order_by("-fecha_creacion").first()
    cot = lead.cotizaciones_comerciales.order_by("-actualizada_en").first()
    rev = cot.revisiones.order_by("-numero").first() if cot else None
    if rev:
        return {"amount": _num(rev.precio_final), "mode": "confirmed", "confidence": None}
    if tecnica:
        if tecnica.modo == "manual":
            return {"amount": None, "mode": "advisor", "confidence": tecnica.confianza}
        return {
            "amount": _num(tecnica.precio_recomendado),
            "mode": "auto",
            "confidence": tecnica.confianza,
            "range": [_num(tecnica.precio_min), _num(tecnica.precio_max)],
        }
    return {"amount": None, "mode": "pending", "confidence": None}


def _tracking(lead):
    servicio = getattr(lead, "servicio_generado", None)
    if not servicio:
        return None
    prog = (servicio.programaciones.exclude(estado_operativo="cancelado")
            .select_related("conductor", "transportista", "transportista_vehiculo").first())
    carrier = None
    if prog:
        if prog.transportista_vehiculo_id:
            carrier = {
                "kind": "carrier",
                "name": prog.transportista.nombre if prog.transportista_id else "Transportista",
                "plate": prog.transportista_vehiculo.placa,
                "driver": prog.conductor_externo or None,
            }
        elif prog.vehiculo_id:
            carrier = {
                "kind": "own",
                "name": "Equipo Lima Express",
                "plate": prog.vehiculo.placa,
                "driver": prog.conductor.nombre if prog.conductor_id else None,
            }
    return {
        "operationalState": prog.estado_operativo if prog else "pendiente",
        "date": _d(servicio.fecha_servicio),
        "schedule": servicio.horario_servicio,
        "assignee": carrier,
    }


def load_item(lead):
    return {
        "code": lead.codigo,
        "origin": lead.distrito_origen or "",
        "destination": lead.distrito_destino or "",
        "date": _d(lead.fecha_servicio),
        "schedule": lead.horario_servicio,
        "quoteMode": lead.modo_cotizacion or "por_carga",
        "cargoCategory": lead.categoria_carga or "",
        "status": _load_status(lead),
        "price": _price_view(lead),
        "createdAt": _d(lead.fecha_creacion),
    }


def load_detail(lead):
    out = load_item(lead)
    out["addressOrigin"] = lead.direccion_origen
    out["addressDestination"] = lead.direccion_destino
    out["cargoDetail"] = lead.lista_objetos
    out["weightKg"] = _num(lead.peso_carga_kg)
    out["volumeM3"] = _num(lead.volumen_carga_m3)
    out["operators"] = lead.cantidad_operarios
    out["truckType"] = lead.tipo_camion
    out["tracking"] = _tracking(lead)
    cot = lead.cotizaciones_comerciales.order_by("-actualizada_en").first()
    out["negotiating"] = bool(cot and cot.estado == "en_negociacion")

    servicio = getattr(lead, "servicio_generado", None)
    if servicio and servicio.precio:
        from apps.servicios.cobro import estado_cobro
        e = estado_cobro(servicio)
        # el cliente ve sus cuotas y cuánto debe, nada más
        out["billing"] = {
            "total": e["total"], "paid": e["paid"], "balance": e["balance"],
            "installments": [
                {"id": i["id"], "label": i["triggerLabel"], "dueDate": i["dueDate"],
                 "amount": i["amount"], "paid": i["paid"], "state": i["state"]}
                for i in e["installments"]
            ],
        }
    return out


# --------------------------------------------------------------------------- #
#  Vistas
# --------------------------------------------------------------------------- #

class _Portal(APIView):
    permission_classes = [IsPortalCustomer]

    def get_exception_handler(self):
        return api_exception_handler

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.cu = customer_portal_for(request.user)

    def _lead(self, code):
        return get_object_or_404(
            Lead.objects.select_related("cliente")
            .prefetch_related("cotizaciones", "cotizaciones_comerciales"),
            codigo=code, cliente=self.cu.cliente,
        )


class CustomerMeView(_Portal):
    def get(self, request):
        c = self.cu.cliente
        return Response({
            "id": self.cu.id,
            "name": c.nombre or c.display_name,
            "email": c.correo,
            "phone": c.telefono,
            "company": self.cu.empresa.razon_social if self.cu.empresa_id else None,
        })


class CustomerLoadsView(_Portal):
    def get(self, request):
        leads = (
            Lead.objects.filter(cliente=self.cu.cliente)
            .exclude(estado=Lead.PERDIDO)
            .select_related("servicio_generado")
            .prefetch_related("cotizaciones", "cotizaciones_comerciales")
            .order_by("-fecha_creacion")
        )
        return Response({"results": [load_item(x) for x in leads]})

    @transaction.atomic
    def post(self, request):
        d = request.data
        origin, destination = d.get("origin") or {}, d.get("destination") or {}
        cargo = d.get("cargo") or {}
        if not origin.get("district") or not destination.get("district"):
            raise ValidationError("Falta el distrito de origen o destino.")

        fecha = None
        if d.get("date"):
            try:
                fecha = datetime.strptime(d["date"], "%Y-%m-%d").date()
            except ValueError:
                raise ValidationError({"date": "Fecha inválida."})

        modo = d.get("quoteMode") or Lead.MODO_COT_POR_CARGA
        if modo not in dict(Lead.MODOS_COTIZACION):
            modo = Lead.MODO_COT_POR_CARGA

        lead = Lead.objects.create(
            cliente=self.cu.cliente,
            origen_carga="portal_cliente",
            modo_cotizacion=modo,
            categoria_carga=(cargo.get("category") or ""),
            tipo_servicio=(cargo.get("category") or "carga"),
            distrito_origen=origin.get("district") or "",
            distrito_destino=destination.get("district") or "",
            direccion_origen=origin.get("address") or "",
            direccion_destino=destination.get("address") or "",
            piso_origen=origin.get("floor") or None,
            piso_destino=destination.get("floor") or None,
            lista_objetos=cargo.get("detail") or "",
            peso_carga_kg=_amount(cargo.get("weightKg")),
            volumen_carga_m3=_amount(cargo.get("volumeM3")),
            cantidad_operarios=cargo.get("operators") or None,
            tipo_camion=(cargo.get("truckType") or "") if modo == Lead.MODO_COT_POR_VEHICULO else "",
            fecha_servicio=fecha,
            horario_servicio=(d.get("schedule") or ""),
            estado=Lead.NUEVO,
        )
        replace_lead_route(lead, [
            {"tipo": "origen", "distrito": origin.get("district") or "",
             "direccion": origin.get("address") or "", "piso": origin.get("floor") or None},
            {"tipo": "destino", "distrito": destination.get("district") or "",
             "direccion": destination.get("address") or "", "piso": destination.get("floor") or None},
        ])
        cotizar_lead(lead)
        lead.refresh_from_db()
        return Response(load_detail(lead), status=201)


class CustomerLoadDetailView(_Portal):
    def get(self, request, code):
        return Response(load_detail(self._lead(code)))


class CustomerLoadPayView(_Portal):
    """Genera una orden de pago para una cuota (la indicada, o la próxima
    pendiente) y devuelve el link del checkout público."""

    def post(self, request, code):
        from apps.pagos import services as pagos
        lead = self._lead(code)
        servicio = getattr(lead, "servicio_generado", None)
        if not servicio:
            raise ValidationError("Todavía no hay una reserva confirmada para pagar.")
        orden = pagos.crear_orden(
            servicio,
            cuota_id=request.data.get("installmentId"),
            usuario=request.user, origen="portal",
            email=self.cu.cliente.correo or "",
        )
        return Response({"token": orden.token, "url": f"/pagar/{orden.token}",
                         "amount": float(orden.monto), "state": orden.estado})


class CustomerLoadAcceptView(_Portal):
    def post(self, request, code):
        lead = self._lead(code)
        tecnica = lead.cotizaciones.order_by("-fecha_creacion").first()
        if not tecnica or tecnica.modo == "manual":
            raise ValidationError(
                "Esta carga necesita que un asesor confirme el precio. Elegí "
                "\"Que me contacte un asesor\"."
            )
        precio = request.data.get("price")
        monto = _amount(precio) or tecnica.precio_recomendado
        crear_cotizacion_portal(lead, monto)
        return Response(load_detail(self._lead(code)))


class CustomerLoadRequestAdvisorView(_Portal):
    def post(self, request, code):
        lead = self._lead(code)
        tecnica = lead.cotizaciones.order_by("-fecha_creacion").first()
        base = tecnica.precio_recomendado if tecnica else Decimal("0")
        crear_cotizacion_portal(lead, base or Decimal("1"))
        return Response(load_detail(self._lead(code)))


class CustomerLoadNegotiateView(_Portal):
    def post(self, request, code):
        lead = self._lead(code)
        tecnica = lead.cotizaciones.order_by("-fecha_creacion").first()
        base = (tecnica.precio_recomendado if tecnica else None)
        cotizacion = crear_cotizacion_portal(lead, base or Decimal("1"), en_negociacion=True)
        hilo, _ = neg.abrir_hilo(
            lead, HiloNegociacion.TIPO_VENTA, usuario=request.user,
            cotizacion=cotizacion, contraparte=self.cu.cliente, monto_objetivo=base,
        )
        note = (request.data.get("note") or "").strip()
        counter = _amount(request.data.get("counterOffer"))
        if counter is not None:
            try:
                neg.publicar_mensaje(hilo, emisor=MensajeNegociacion.EMISOR_CLIENTE,
                                     autor=request.user, texto=note, propuesta_monto=counter)
            except neg.NegociacionError:
                pass
        elif note:
            try:
                neg.publicar_mensaje(hilo, emisor=MensajeNegociacion.EMISOR_CLIENTE,
                                     autor=request.user, texto=note)
            except neg.NegociacionError:
                pass
        return Response(load_detail(self._lead(code)))


def _cust_msg(m):
    sender = {
        MensajeNegociacion.EMISOR_CLIENTE: "you",
        MensajeNegociacion.EMISOR_TAXICARGA: "taxicarga",
        MensajeNegociacion.EMISOR_SISTEMA: "system",
    }.get(m.emisor, "taxicarga")
    return {
        "id": m.id, "sender": sender, "text": m.texto,
        "proposalAmount": _num(m.propuesta_monto),
        "proposalState": _PROP_EN.get(m.propuesta_estado, m.propuesta_estado or None),
        "proposalFromTaxicarga": m.emisor == MensajeNegociacion.EMISOR_TAXICARGA,
        "createdAt": _d(m.creado_en),
    }


class _CustHilo(_Portal):
    def _hilo(self, code):
        lead = self._lead(code)
        return get_object_or_404(
            HiloNegociacion.objects.filter(
                lead=lead, tipo=HiloNegociacion.TIPO_VENTA, contraparte=self.cu.cliente,
            )
        )

    def _payload(self, hilo):
        return {
            "code": hilo.lead.codigo,
            "state": _HILO_STATE_EN.get(hilo.estado, hilo.estado),
            "paused": hilo.estado == HiloNegociacion.ESTADO_PAUSADA,
            "currentAmount": _num(hilo.monto_actual),
            "agreedAmount": _num(hilo.monto_acordado),
            "messages": [
                _cust_msg(m) for m in hilo.mensajes.order_by("creado_en")
                if m.emisor != MensajeNegociacion.EMISOR_TRANSPORTISTA
            ],
        }


class CustomerNegotiationView(_CustHilo):
    def get(self, request, code):
        return Response(self._payload(self._hilo(code)))


class CustomerNegotiationMessagesView(_CustHilo):
    def post(self, request, code):
        hilo = self._hilo(code)
        text = (request.data.get("text") or "").strip()
        amount = _amount(request.data.get("proposalAmount"))
        if not text and amount is None:
            raise ValidationError("El mensaje está vacío.")
        try:
            neg.publicar_mensaje(
                hilo, emisor=MensajeNegociacion.EMISOR_CLIENTE, autor=request.user,
                texto=text, propuesta_monto=amount,
            )
        except neg.NegociacionError as e:
            raise ValidationError(str(e))
        return Response(self._payload(self._hilo(code)))


class CustomerNegotiationRespondView(_CustHilo):
    def post(self, request, code, pk):
        hilo = self._hilo(code)
        mensaje = get_object_or_404(hilo.mensajes, pk=pk)
        if mensaje.emisor != MensajeNegociacion.EMISOR_TAXICARGA:
            raise ValidationError("Solo podés responder propuestas de Lima Express.")
        accion = {"accept": "aceptar", "counter": "contraofertar", "reject": "rechazar"}.get(
            request.data.get("action"))
        if not accion:
            raise ValidationError("Acción no válida.")
        try:
            neg.responder_propuesta(mensaje, accion, usuario=request.user,
                                    monto=_amount(request.data.get("amount")))
        except neg.NegociacionError as e:
            raise ValidationError(str(e))
        return Response(self._payload(self._hilo(code)))
