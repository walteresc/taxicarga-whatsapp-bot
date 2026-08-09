from django.core.exceptions import ValidationError
from django.db import transaction

from apps.cotizador.models import RevisionCotizacion
from apps.ia.conversation_policy import booking_missing_fields, effective_quote_values
from apps.leads.route import route_for_lead
from apps.leads.cargo import effective_load_detail

from .models import Servicio, ServicioUbicacion, SERVICIO_PENDIENTE


@transaction.atomic
def crear_servicio_desde_lead(lead, usuario=None, revision=None, *, require_accepted_revision=False):
    lead = type(lead).objects.select_for_update().select_related("cliente").get(pk=lead.pk)
    existing = Servicio.objects.select_for_update().filter(lead_origen=lead).first()
    if existing:
        return existing, False
    if booking_missing_fields(lead):
        raise ValidationError("La reserva no tiene todos los datos obligatorios.")
    if revision is None:
        revision = (
            RevisionCotizacion.objects.select_related("cotizacion")
            .filter(cotizacion__lead=lead, cotizacion__estado="aceptada", enviada=True)
            .order_by("-cotizacion__actualizada_en", "-numero")
            .first()
        )
    if require_accepted_revision and (
        not revision or revision.cotizacion.lead_id != lead.id
        or revision.cotizacion.estado != "aceptada" or not revision.enviada
    ):
        raise ValidationError("No existe una revision comercial enviada y aceptada.")

    effective = effective_quote_values(lead)
    packaging = {
        "sin embalaje": "sin_embalaje",
        "embalaje basico": "basico",
        "embalaje de muebles y artefactos": "muebles",
        "embalaje full": "full",
    }.get(lead.modalidad_servicio, "sin_embalaje")

    servicio = Servicio.objects.create(
        lead_origen=lead,
        cliente=lead.cliente,
        whatsapp_channel=lead.whatsapp_channel,
        asesor=usuario or lead.vendedor_asignado,
        estado=SERVICIO_PENDIENTE,
        tipo_servicio=lead.tipo_servicio,
        distrito_origen=lead.distrito_origen,
        distrito_destino=lead.distrito_destino,
        direccion_origen=lead.direccion_origen,
        direccion_destino=lead.direccion_destino,
        piso_origen=lead.piso_origen,
        piso_destino=lead.piso_destino,
        acceso_origen=lead.acceso_origen,
        acceso_destino=lead.acceso_destino,
        lista_objetos=lead.lista_objetos,
        objetos_pesados=lead.objetos_pesados,
        detalle_carga=effective_load_detail(lead),
        incluye_personal_carga=effective["incluye_personal_carga"],
        cantidad_operarios=lead.cantidad_operarios,
        requiere_desarmado=effective["requiere_desarmado"],
        requiere_armado=effective["requiere_armado"],
        peso_carga_kg=lead.peso_carga_kg,
        volumen_carga_m3=lead.volumen_carga_m3,
        fecha_servicio=lead.fecha_servicio,
        horario_servicio=lead.horario_servicio,
        tipo_embalaje=packaging,
        precio_cotizado=revision.precio_final if revision else lead.precio_cotizado,
        precio_final=revision.precio_final if revision else lead.precio_final,
        precio=revision.precio_final if revision else (lead.precio_final or lead.precio_cotizado),
        dni_ruc=lead.dni_reserva,
        observaciones=lead.observaciones,
    )
    ServicioUbicacion.objects.bulk_create([
        ServicioUbicacion(
            servicio=servicio,
            orden=order,
            tipo=location.tipo,
            distrito=location.distrito,
            direccion=location.direccion,
            piso=location.piso,
            ascensor=location.ascensor,
            acceso_camion=location.acceso_camion,
            distancia_acarreo=location.distancia_acarreo,
            observaciones_acceso=location.observaciones_acceso,
        )
        for order, location in enumerate(route_for_lead(lead))
    ])
    return servicio, True
