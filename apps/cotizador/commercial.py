from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import CotizacionComercial, RevisionCotizacion, SolicitudCotizacion


class SolicitudOcupada(ValidationError):
    pass


TRANSICIONES_COTIZACION = {
    "borrador": {"cancelada"},
    "enviada": {"entregada", "en_negociacion", "aceptada", "rechazada", "vencida"},
    "entregada": {"en_negociacion", "aceptada", "rechazada", "vencida"},
    "en_negociacion": {"aceptada", "rechazada", "vencida"},
}


def cambiar_estado_cotizacion(cotizacion_id, nuevo_estado):
    with transaction.atomic():
        cotizacion = CotizacionComercial.objects.select_for_update().get(pk=cotizacion_id)
        permitidos = TRANSICIONES_COTIZACION.get(cotizacion.estado, set())
        if nuevo_estado not in permitidos:
            raise ValidationError("Transición de estado no permitida.")
        cotizacion.estado = nuevo_estado
        cotizacion.save(update_fields=["estado", "actualizada_en"])
        return cotizacion


def aceptar_cotizacion_para_lead(lead):
    """Accept the latest actually-sent revision; repeated events are harmless."""
    with transaction.atomic():
        accepted = (
            CotizacionComercial.objects.select_for_update()
            .filter(lead=lead, estado="aceptada", revisiones__enviada=True)
            .order_by("-actualizada_en")
            .first()
        )
        if accepted:
            return accepted.revisiones.filter(enviada=True).order_by("-numero").first(), False
        quote = (
            CotizacionComercial.objects.select_for_update()
            .filter(lead=lead, estado__in=["enviada", "entregada", "en_negociacion"])
            .order_by("-actualizada_en")
            .first()
        )
        if not quote:
            return None, False
        revision = quote.revisiones.filter(enviada=True).order_by("-numero").first()
        if not revision:
            return None, False
        quote.estado = "aceptada"
        quote.save(update_fields=["estado", "actualizada_en"])
        return revision, True


def asignar_solicitud(solicitud_id, actor):
    with transaction.atomic():
        solicitud = SolicitudCotizacion.objects.select_for_update().get(pk=solicitud_id)
        if solicitud.estado not in [SolicitudCotizacion.PENDIENTE, SolicitudCotizacion.EN_PROCESO]:
            raise ValidationError("La solicitud ya no esta activa.")
        if solicitud.asignada_a_id and solicitud.asignada_a_id != actor.id:
            raise SolicitudOcupada("La solicitud ya fue tomada por otro asesor.")
        solicitud.asignada_a = actor
        solicitud.estado = SolicitudCotizacion.EN_PROCESO
        solicitud.save(update_fields=["asignada_a", "estado", "actualizada_en"])
        if solicitud.conversacion_id:
            solicitud.conversacion.responsable = actor
            solicitud.conversacion.save(update_fields=["responsable", "actualizada_en"])
        if solicitud.lead.vendedor_asignado_id != actor.id:
            solicitud.lead.vendedor_asignado = actor
            solicitud.lead.save(update_fields=["vendedor_asignado"])
        return solicitud


def crear_borrador(solicitud, actor, precio_final, **datos):
    with transaction.atomic():
        solicitud = SolicitudCotizacion.objects.select_for_update().select_related("lead").get(pk=solicitud.pk)
        cotizacion = CotizacionComercial.objects.create(
            codigo=_nuevo_codigo(),
            lead=solicitud.lead,
            solicitud=solicitud,
            channel=solicitud.lead.whatsapp_channel,
            origen="asesor" if actor else "bot",
            asesor=actor,
        )
        revision = _crear_revision(cotizacion, actor, precio_final, 1, **datos)
        solicitud.estado = SolicitudCotizacion.EN_PROCESO
        solicitud.asignada_a = actor
        solicitud.save(update_fields=["estado", "asignada_a", "actualizada_en"])
        return cotizacion, revision


def crear_revision(cotizacion, actor, precio_final, **datos):
    with transaction.atomic():
        cotizacion = CotizacionComercial.objects.select_for_update().get(pk=cotizacion.pk)
        ultima = cotizacion.revisiones.order_by("-numero").first()
        numero = (ultima.numero if ultima else 0) + 1
        return _crear_revision(cotizacion, actor, precio_final, numero, **datos)


def guardar_borrador(solicitud, actor, precio_final, **datos):
    with transaction.atomic():
        solicitud = SolicitudCotizacion.objects.select_for_update().get(pk=solicitud.pk)
        source_key = datos.get("source_key", "")
        if source_key:
            existing_revision = RevisionCotizacion.objects.select_related("cotizacion").filter(
                source_key=source_key
            ).first()
            if existing_revision:
                return existing_revision.cotizacion, existing_revision
        cotizacion = solicitud.cotizaciones.filter(estado="borrador").order_by("-creada_en").first()
        if cotizacion:
            return cotizacion, crear_revision(cotizacion, actor, precio_final, **datos)
        return crear_borrador(solicitud, actor, precio_final, **datos)


def crear_cotizacion_automatica(conversacion, cotizacion_tecnica, mensaje, *, source_key):
    """Persist bot pricing once; publication remains owned by the bot outbox."""
    with transaction.atomic():
        from apps.whatsapp.models import ConversacionWhatsApp
        conversation = ConversacionWhatsApp.objects.select_for_update(of=("self",)).get(pk=conversacion.pk)
        revision = RevisionCotizacion.objects.select_related("cotizacion").filter(source_key=source_key).first()
        if revision:
            return revision.cotizacion, revision, False
        commercial = CotizacionComercial.objects.create(
            codigo=_nuevo_codigo(),
            lead=conversation.lead,
            channel=conversation.channel,
            origen="bot",
            moneda="PEN",
        )
        revision = _crear_revision(
            commercial,
            None,
            cotizacion_tecnica.precio_max,
            1,
            cotizacion_tecnica=cotizacion_tecnica,
            source_key=source_key,
            precio_sugerido_min=cotizacion_tecnica.precio_min,
            precio_sugerido_max=cotizacion_tecnica.precio_max,
            mensaje_whatsapp=mensaje,
        )
        return commercial, revision, True


def marcar_revision_enviada(revision):
    with transaction.atomic():
        revision = RevisionCotizacion.objects.select_for_update().select_related(
            "cotizacion__solicitud__conversacion", "cotizacion__lead"
        ).get(pk=revision.pk)
        if revision.enviada:
            return revision
        revision.enviada = True
        revision.enviada_en = timezone.now()
        revision.save(update_fields=["enviada", "enviada_en"])
        cotizacion = revision.cotizacion
        cotizacion.estado = "enviada"
        cotizacion.save(update_fields=["estado", "actualizada_en"])
        if cotizacion.solicitud_id:
            solicitud = cotizacion.solicitud
            solicitud.estado = SolicitudCotizacion.TERMINADA
            solicitud.resuelta_en = timezone.now()
            solicitud.save(update_fields=["estado", "resuelta_en", "actualizada_en"])
            conversacion = solicitud.conversacion
        else:
            from apps.whatsapp.models import ConversacionWhatsApp
            conversacion = ConversacionWhatsApp.objects.filter(lead=cotizacion.lead).exclude(
                estado_atencion=ConversacionWhatsApp.ATENCION_CERRADA
            ).order_by("-ultima_actividad").first()
        if conversacion:
            from apps.whatsapp.models import ConversacionWhatsApp
            conversacion.estado_cotizacion = ConversacionWhatsApp.COTIZACION_PRECIO_ENVIADO
            conversacion.save(update_fields=["estado_cotizacion", "actualizada_en"])
        lead = cotizacion.lead
        lead.precio_cotizado = revision.precio_final
        lead.precio_recomendado = revision.precio_final
        lead.estado = lead.COTIZADO
        lead.save(update_fields=["precio_cotizado", "precio_recomendado", "estado"])
        if conversacion:
            from apps.integrations.services.commercial_labels import queue_commercial_label_projection
            transaction.on_commit(lambda: queue_commercial_label_projection(conversacion.id))
        return revision


def _crear_revision(cotizacion, actor, precio_final, numero, **datos):
    precio = Decimal(str(precio_final))
    costo = _decimal_opcional(datos.get("costo_estimado"))
    margen = _decimal_opcional(datos.get("margen_minimo_porcentaje"))
    autoriza_bajo_margen = bool(datos.pop("autoriza_bajo_margen", False))
    if costo is not None and margen is not None:
        minimo = costo * (Decimal("1") + margen / Decimal("100"))
        if precio < minimo and not autoriza_bajo_margen:
            raise ValidationError("El precio final no cumple el margen minimo.")
    return RevisionCotizacion.objects.create(
        cotizacion=cotizacion,
        cotizacion_tecnica=datos.get("cotizacion_tecnica"),
        source_key=datos.get("source_key", ""),
        numero=numero,
        creada_por=actor,
        snapshot_servicio=datos.get("snapshot_servicio", {}),
        precio_sugerido_min=datos.get("precio_sugerido_min"),
        precio_sugerido_max=datos.get("precio_sugerido_max"),
        costo_estimado=costo,
        margen_minimo_porcentaje=margen,
        precio_final=precio,
        condiciones=datos.get("condiciones", ""),
        vigencia_dias=datos.get("vigencia_dias", 7),
        observacion_interna=datos.get("observacion_interna", ""),
        mensaje_whatsapp=datos.get("mensaje_whatsapp", ""),
    )


def _nuevo_codigo():
    return f"COT-{timezone.localdate():%Y%m%d}-{uuid4().hex[:6].upper()}"


def _decimal_opcional(value):
    if value in (None, ""):
        return None
    return Decimal(str(value))
