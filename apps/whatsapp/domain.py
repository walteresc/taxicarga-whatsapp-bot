from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.leads.models import Lead

from .models import AuditoriaWhatsApp, ConversacionWhatsApp


class ConversacionOcupada(Exception):
    pass


class TransicionConversacionInvalida(Exception):
    pass


INSTRUCCIONES_RETORNO_BOT = {
    "recopilar": "Continuar recopilando informacion",
    "resolver_preguntas": "Resolver preguntas del cliente",
    "seguimiento_cotizacion": "Dar seguimiento a la cotizacion",
    "esperar": "Esperar el siguiente mensaje",
}


def obtener_o_crear_conversacion(lead):
    with transaction.atomic():
        lead = Lead.objects.select_for_update(of=("self",)).select_related("cliente", "whatsapp_channel").get(pk=lead.pk)
        conversacion = (
            ConversacionWhatsApp.objects.select_for_update()
            .filter(lead=lead)
            .exclude(estado_atencion=ConversacionWhatsApp.ATENCION_CERRADA)
            .first()
        )
        if conversacion:
            return conversacion
        try:
            with transaction.atomic():
                conversation = ConversacionWhatsApp.objects.create(
                    cliente=lead.cliente,
                    lead=lead,
                    channel=lead.whatsapp_channel,
                    estado_atencion=(
                        ConversacionWhatsApp.ATENCION_ASESOR
                        if lead.atencion_humana
                        else ConversacionWhatsApp.ATENCION_BOT
                    ),
                    responsable=lead.vendedor_asignado if lead.atencion_humana else None,
                    bot_pausado=lead.bot_pausado or lead.atencion_humana,
                    motivo_derivacion=lead.motivo_derivacion or "",
                )
                _ensure_integration_control(conversation)
                return conversation
        except IntegrityError:
            conversation = ConversacionWhatsApp.objects.get(lead=lead)
            _ensure_integration_control(conversation)
            return conversation


def _ensure_integration_control(conversation):
    from apps.integrations.models import ConversationControl
    from apps.integrations.services.channel_policy import integration_enabled

    if integration_enabled(conversation.channel):
        ConversationControl.objects.get_or_create(conversation=conversation)


def tomar_conversacion(conversacion_id, actor):
    if not actor or not actor.is_authenticated:
        raise PermissionDenied
    with transaction.atomic():
        conversacion = _bloquear_conversacion(conversacion_id)
        if conversacion.estado_atencion == ConversacionWhatsApp.ATENCION_CERRADA:
            raise TransicionConversacionInvalida("La conversacion esta cerrada.")
        if conversacion.responsable_id and conversacion.responsable_id != actor.id:
            raise ConversacionOcupada("La conversacion ya tiene otro asesor activo.")
        anterior = conversacion.estado_atencion
        conversacion.estado_atencion = ConversacionWhatsApp.ATENCION_ASESOR
        conversacion.responsable = actor
        conversacion.bot_pausado = True
        conversacion.instruccion_retorno_bot = ""
        conversacion.ultima_actividad = timezone.now()

        # PAUSA BOT: asesor toma control
        from apps.whatsapp_bot_v4.models import ConversationOwnership
        ownership, _ = ConversationOwnership.objects.get_or_create(conversation=conversacion)
        ownership.owner_type = ConversationOwnership.OWNER_ADVISOR
        ownership.control_mode = ConversationOwnership.MODE_MANUAL
        ownership.advisor_id = actor
        ownership.last_human_message_at = timezone.now()
        ownership.save()

        conversacion.save(update_fields=[
            "estado_atencion",
            "responsable",
            "bot_pausado",
            "instruccion_retorno_bot",
            "ultima_actividad",
            "actualizada_en",
        ])
        _sincronizar_lead_humano(conversacion, actor)
        _auditar(conversacion, actor, "conversacion_tomada", {"estado_anterior": anterior})
        return conversacion


def devolver_al_bot(conversacion_id, actor, instruccion):
    if instruccion not in INSTRUCCIONES_RETORNO_BOT:
        raise TransicionConversacionInvalida("Instruccion de retorno invalida.")
    with transaction.atomic():
        conversacion = _bloquear_conversacion(conversacion_id)
        if conversacion.estado_atencion != ConversacionWhatsApp.ATENCION_ASESOR:
            raise TransicionConversacionInvalida("La conversacion no esta bajo control de un asesor.")
        if conversacion.responsable_id and conversacion.responsable_id != actor.id and not actor.is_superuser:
            raise PermissionDenied
        conversacion.estado_atencion = ConversacionWhatsApp.ATENCION_BOT
        conversacion.responsable = None
        conversacion.bot_pausado = False
        conversacion.instruccion_retorno_bot = instruccion
        conversacion.ultima_actividad = timezone.now()

        # DEVUELVE BOT: bot retoma control
        from apps.whatsapp_bot_v4.models import ConversationOwnership
        ownership, _ = ConversationOwnership.objects.get_or_create(conversation=conversacion)
        ownership.owner_type = ConversationOwnership.OWNER_BOT
        ownership.control_mode = ConversationOwnership.MODE_AUTOMATIC
        ownership.advisor_id = None
        ownership.save()

        conversacion.save(update_fields=[
            "estado_atencion",
            "responsable",
            "bot_pausado",
            "instruccion_retorno_bot",
            "ultima_actividad",
            "actualizada_en",
        ])
        if conversacion.lead_id:
            lead = Lead.objects.select_for_update().get(pk=conversacion.lead_id)
            lead.atencion_humana = False
            lead.bot_pausado = False
            lead.requiere_asesor = False
            lead.save(update_fields=["atencion_humana", "bot_pausado", "requiere_asesor"])
        _auditar(conversacion, actor, "conversacion_devuelta_bot", {"instruccion": instruccion})
        return conversacion


def enviar_a_cotizar(conversacion_id, actor, motivo="", datos_faltantes=None):
    from apps.cotizador.models import SolicitudCotizacion
    from apps.integrations.services.commercial_labels import queue_commercial_label_projection

    with transaction.atomic():
        conversacion = _bloquear_conversacion(conversacion_id)
        if not conversacion.lead_id:
            raise TransicionConversacionInvalida("La conversacion no tiene lead asociado.")
        lead = Lead.objects.select_for_update().get(pk=conversacion.lead_id)
        solicitud = (
            SolicitudCotizacion.objects.select_for_update()
            .filter(
                lead_id=conversacion.lead_id,
                estado__in=[SolicitudCotizacion.PENDIENTE, SolicitudCotizacion.EN_PROCESO],
            )
            .first()
        )
        if not solicitud:
            solicitud = SolicitudCotizacion.objects.create(
                lead_id=conversacion.lead_id,
                conversacion=conversacion,
                motivo=motivo,
                datos_faltantes=datos_faltantes or [],
                prioridad=lead.prioridad,
                creada_por=actor,
            )
        else:
            changed = []
            if motivo and solicitud.motivo != motivo:
                solicitud.motivo = motivo
                changed.append("motivo")
            if datos_faltantes is not None and solicitud.datos_faltantes != datos_faltantes:
                solicitud.datos_faltantes = datos_faltantes
                changed.append("datos_faltantes")
            if not solicitud.conversacion_id:
                solicitud.conversacion = conversacion
                changed.append("conversacion")
            if changed:
                solicitud.save(update_fields=changed + ["actualizada_en"])
        conversacion.estado_cotizacion = ConversacionWhatsApp.COTIZACION_PENDIENTE
        conversacion.motivo_derivacion = motivo
        conversacion.save(update_fields=["estado_cotizacion", "motivo_derivacion", "actualizada_en"])
        _auditar(conversacion, actor, "enviada_a_cotizar", {"solicitud_id": solicitud.id, "motivo": motivo})
        transaction.on_commit(lambda: queue_commercial_label_projection(conversacion.id))
        return solicitud


def cerrar_conversacion(conversacion_id, actor):
    with transaction.atomic():
        conversacion = _bloquear_conversacion(conversacion_id)
        conversacion.estado_atencion = ConversacionWhatsApp.ATENCION_CERRADA
        conversacion.responsable = None
        conversacion.bot_pausado = True
        conversacion.cerrada_en = timezone.now()
        conversacion.save(update_fields=[
            "estado_atencion",
            "responsable",
            "bot_pausado",
            "cerrada_en",
            "actualizada_en",
        ])
        if conversacion.lead_id:
            lead = Lead.objects.select_for_update().get(pk=conversacion.lead_id)
            lead.atencion_humana = True
            lead.bot_pausado = True
            lead.save(update_fields=["atencion_humana", "bot_pausado"])
        _auditar(conversacion, actor, "conversacion_cerrada")
        return conversacion


def _bloquear_conversacion(conversacion_id):
    return (
        ConversacionWhatsApp.objects.select_for_update(of=("self",))
        .select_related("lead")
        .get(pk=conversacion_id)
    )


def _sincronizar_lead_humano(conversacion, actor):
    if not conversacion.lead_id:
        return
    lead = Lead.objects.select_for_update().get(pk=conversacion.lead_id)
    lead.atencion_humana = True
    lead.bot_pausado = True
    lead.vendedor_asignado = actor
    update_fields = ["atencion_humana", "bot_pausado", "vendedor_asignado"]
    if lead.estado not in [Lead.CERRADO, Lead.PERDIDO]:
        lead.estado = Lead.ASIGNADO
        update_fields.append("estado")
    lead.save(update_fields=update_fields)


def _auditar(conversacion, actor, evento, detalle=None):
    return AuditoriaWhatsApp.objects.create(
        conversacion=conversacion,
        lead=conversacion.lead,
        actor=actor if actor and actor.is_authenticated else None,
        evento=evento,
        detalle=detalle or {},
    )
