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


def crear_conversacion_manual(telefono, actor, nombre=""):
    """El asesor escribe un número que nunca contactó y arranca una conversación
    desde cero (no llegó por webhook). Sin mensajes entrantes todavía, así que
    el composer queda bloqueado hasta que exista una plantilla aprobada — WhatsApp
    no permite texto libre fuera de la ventana de 24h / sin que el cliente haya
    escrito primero. Ver ChatComposer.vue (pendingTemplate).

    `nombre` es opcional y a propósito: WhatsApp Business API NUNCA manda a
    ningún integrador el nombre que alguien tenga guardado en su agenda del
    celular — solo el nombre de perfil que el CLIENTE se puso a sí mismo, y
    eso recién llega cuando el cliente escribe por primera vez. Si el asesor
    ya conoce el contacto (lo tiene guardado), este es el único momento en que
    ese nombre puede entrar al sistema. Se guarda como name_source=MANUAL para
    que un eco/mensaje entrante futuro nunca lo pise (mismo criterio que
    apps/whatsapp/services_ycloud.py)."""
    from apps.clientes.models import Cliente
    from apps.clientes.phone_normalizer import normalize_phone

    from .models import WhatsAppChannel

    telefono = (telefono or "").strip()
    if not telefono:
        raise TransicionConversacionInvalida("Ingresa un número de teléfono.")
    nombre = (nombre or "").strip()

    norm_result = normalize_phone(telefono)
    phone_e164 = (
        norm_result["normalized_e164"] if norm_result["is_valid"]
        else (telefono if telefono.startswith("+") else f"+{telefono}")
    )

    channel = WhatsAppChannel.objects.filter(activo=True).order_by("id").first()
    if channel is None:
        raise TransicionConversacionInvalida("No hay un canal de WhatsApp activo configurado.")

    with transaction.atomic():
        defaults = {"nombre": nombre or phone_e164}
        if nombre:
            defaults["name_source"] = Cliente.SOURCE_MANUAL
        cliente, _created = Cliente.objects.get_or_create(telefono=phone_e164, defaults=defaults)
        if nombre and cliente.name_source != Cliente.SOURCE_MANUAL:
            cliente.nombre = nombre
            cliente.name_source = Cliente.SOURCE_MANUAL
            cliente.save(update_fields=["nombre", "name_source"])
        lead = (
            Lead.objects.filter(cliente=cliente)
            .exclude(estado__in=(Lead.CERRADO, Lead.PERDIDO))
            .order_by("-fecha_creacion")
            .first()
        )
        if lead is None:
            lead = Lead.objects.create(cliente=cliente, whatsapp_channel=channel)
        elif not lead.whatsapp_channel_id:
            lead.whatsapp_channel = channel
            lead.save(update_fields=["whatsapp_channel"])
        conversacion = obtener_o_crear_conversacion(lead)
        # Si el contacto estaba oculto (archivado), volver a crearle una conversación
        # a mano debe traerlo de vuelta a la vista — mismo reset que al recibir un
        # mensaje nuevo (ver services_ycloud.py).
        if conversacion.archivada:
            conversacion.archivada = False
            conversacion.archivada_por = None
            conversacion.archivada_en = None
            conversacion.save(update_fields=["archivada", "archivada_por", "archivada_en"])
        _auditar(conversacion, actor, "conversacion_iniciada_manual", {"telefono": phone_e164})
        return conversacion


def _ensure_integration_control(conversation):
    from apps.integrations.models import ConversationControl
    from apps.integrations.services.channel_policy import integration_enabled

    if integration_enabled(conversation.channel):
        ConversationControl.objects.get_or_create(conversation=conversation)


def _obtener_o_crear_lead_para_conversacion(conversacion):
    """Lead comercial de la conversación — creación PEREZOSA (FASE 1).

    Se crea la primera vez que se necesita de verdad:
      - un asesor toma la conversación o la envía a cotizar, o
      - la extracción (FASE 2) alcanza el mínimo para cotizar.

    Reglas:
      - Un lead activo por (cliente, whatsapp_channel); se reutiliza salvo que
        esté CERRADO/PERDIDO (así una mudanza nueva a los 3 meses = oportunidad
        nueva en reportes).
      - Los contactos marcados es_transportista NUNCA generan lead comercial.
      - Al crear el lead se vuelca lo que ya haya en conversacion.datos_extraidos.

    Debe llamarse dentro de una transacción. Devuelve el Lead o None.
    """
    if conversacion.lead_id:
        return conversacion.lead
    cliente = conversacion.cliente
    if not cliente or cliente.es_transportista:
        return None

    lead = (
        Lead.objects.select_for_update()
        .filter(cliente=cliente, whatsapp_channel=conversacion.channel)
        .exclude(estado__in=[Lead.CERRADO, Lead.PERDIDO])
        .order_by("-fecha_creacion")
        .first()
    )
    # No reutilizar un lead que ya está colgado de otra conversación activa
    # (rompería el constraint whatsapp_lead_conversacion_activa_unica).
    if lead and (
        ConversacionWhatsApp.objects
        .filter(lead=lead)
        .exclude(pk=conversacion.pk)
        .exclude(estado_atencion=ConversacionWhatsApp.ATENCION_CERRADA)
        .exists()
    ):
        lead = None

    creado = False
    if lead is None:
        lead = Lead.objects.create(
            cliente=cliente,
            whatsapp_channel=conversacion.channel,
            estado=Lead.NUEVO,
        )
        creado = True

    conversacion.lead = lead
    conversacion.save(update_fields=["lead", "actualizada_en"])

    if creado and conversacion.datos_extraidos:
        from apps.whatsapp.services_extraccion import volcar_datos_extraidos_al_lead
        volcar_datos_extraidos_al_lead(lead, conversacion.datos_extraidos, solo_vacios=True)

    return lead


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
        # El asesor engancha la conversación → hay oportunidad comercial: crear el
        # Lead perezosamente si aún no existe (FASE 1). Nunca para transportistas.
        _obtener_o_crear_lead_para_conversacion(conversacion)
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
            # FASE 1: crear el Lead perezosamente en lugar de bloquear. Vuelca lo
            # que la extracción (FASE 2) haya acumulado en datos_extraidos.
            lead = _obtener_o_crear_lead_para_conversacion(conversacion)
            if lead is None:
                raise TransicionConversacionInvalida(
                    "No se puede cotizar: el contacto está marcado como transportista."
                )
            conversacion.refresh_from_db(fields=["lead"])
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
                tipo=SolicitudCotizacion.TIPO_COTIZACION,
                motivo=motivo,
                datos_faltantes=datos_faltantes or [],
                prioridad=lead.prioridad,
                creada_por=actor,
            )
        else:
            changed = []
            # Si venía de "Para revisión", enviarla a cotizar la reclasifica.
            if solicitud.tipo != SolicitudCotizacion.TIPO_COTIZACION:
                solicitud.tipo = SolicitudCotizacion.TIPO_COTIZACION
                changed.append("tipo")
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
