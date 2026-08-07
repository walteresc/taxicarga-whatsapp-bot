import logging
from datetime import time as dt_time

from django.utils import timezone

from .models import BotSchedule, ConfiguracionBot, WhatsAppChannel

logger = logging.getLogger(__name__)

SPECIAL_OBJECT_KEYWORDS = [
    "piano",
    "caja fuerte",
    "caja de seguridad",
    "maquinaria",
    "mármol",
    "vidrio grande",
    "vitrina grande",
    "refrigeradora industrial",
    "congeladora industrial",
    "servidor",
    "rack",
    "equipo médico",
    "equipo dental",
    "objeto pesado",
]

OFFICE_KEYWORDS = ["oficina", "corporativo", "empresa", "archivo", "almacén", "almacen"]


def _check_schedules(dia_semana, hora_actual, channel=None):
    filters = {"day_of_week": dia_semana, "is_active": True}
    if channel:
        filters["channel"] = channel
    schedules = BotSchedule.objects.filter(**filters)
    for s in schedules:
        inicio = s.start_time
        fin = s.end_time
        if isinstance(inicio, str):
            inicio = dt_time.fromisoformat(inicio)
        if isinstance(fin, str):
            fin = dt_time.fromisoformat(fin)
        if inicio <= fin:
            if inicio <= hora_actual <= fin:
                return True, f"{inicio:%H-%M}-{fin:%H-%M}"
        else:
            if hora_actual >= inicio or hora_actual <= fin:
                return True, f"{inicio:%H-%M}-{fin:%H-%M}"
    return False, None


def _check_legacy_schedule(conf, now):
    dia_local = now.strftime("%A").lower()
    dias_map = {
        "monday": "lunes", "tuesday": "martes", "wednesday": "miercoles",
        "thursday": "jueves", "friday": "viernes", "saturday": "sabado", "sunday": "domingo",
    }
    dia_local = dias_map.get(dia_local, dia_local)
    dia_activo = getattr(conf, f"{dia_local}_activo", False)
    if not dia_activo:
        return False, None
    hora_actual = now.time()
    inicio = conf.hora_inicio_bot
    fin = conf.hora_fin_bot
    if isinstance(inicio, str):
        inicio = dt_time.fromisoformat(inicio)
    if isinstance(fin, str):
        fin = dt_time.fromisoformat(fin)
    if inicio <= fin:
        dentro = inicio <= hora_actual <= fin
    else:
        dentro = hora_actual >= inicio or hora_actual <= fin
    return dentro, f"{inicio:%H:%M}-{fin:%H:%M}"


def _is_in_schedule(conf, dia_semana, hora_actual, now, channel=None):
    filters = {"day_of_week": dia_semana, "is_active": True}
    if channel:
        filters["channel"] = channel
    has_schedules = BotSchedule.objects.filter(**filters).exists()
    if has_schedules:
        dentro, rango = _check_schedules(dia_semana, hora_actual, channel=channel)
        return dentro, rango
    dentro, rango = _check_legacy_schedule(conf, now)
    return dentro, rango


def _objetos_especiales_detectados(lead):
    textos = [lead.lista_objetos or "", lead.objetos_pesados or ""]
    texto_completo = " ".join(textos).lower()
    encontrados = [kw for kw in SPECIAL_OBJECT_KEYWORDS if kw in texto_completo]
    return encontrados


def evaluar_mixto_inteligente(lead):
    motivos = []

    # A. Ruta fuera de Lima/Callao
    try:
        from apps.ia.conversation_engine import _route_requires_manual_review
        if _route_requires_manual_review(lead):
            motivos.append("Provincia o ruta fuera de Lima/Callao")
    except Exception as e:
        logger.warning("No se pudo evaluar ruta: %s", e)

    # B. Objetos especiales
    objetos = _objetos_especiales_detectados(lead)
    if objetos:
        motivos.append(f"Objeto(s) especial(es): {', '.join(objetos)}")

    # C. Pisos altos por escaleras
    if lead.piso_origen is not None and lead.piso_origen > 5 and lead.ascensor_origen is False:
        motivos.append(f"Piso origen {lead.piso_origen} sin ascensor")
    if lead.piso_destino is not None and lead.piso_destino > 5 and lead.ascensor_destino is False:
        motivos.append(f"Piso destino {lead.piso_destino} sin ascensor")

    # D. Oficina / corporativo
    tipo = (lead.tipo_servicio or "").lower()
    if any(kw in tipo for kw in OFFICE_KEYWORDS):
        motivos.append("Mudanza de oficina o corporativo")

    # E. Embalaje full
    modalidad = (lead.modalidad_servicio or "").lower()
    if "embalaje full" in modalidad or "embalajefull" in modalidad:
        motivos.append("Servicio de embalaje full")

    # F. Confianza IA
    confianza_suficiente = True
    if hasattr(lead, "confianza_extraccion") and lead.confianza_extraccion:
        if lead.confianza_extraccion == "baja":
            confianza_suficiente = False
            motivos.append("Confianza baja en extracción de datos")
    else:
        logger.info("Lead %d no tiene campo confianza_extraccion, se omite evaluación", lead.id)

    # G. Históricos suficientes
    historicos_suficientes = True
    try:
        from apps.cotizador.services import _find_similar_services
        similares = _find_similar_services(lead)
        if len(similares) < 3:
            historicos_suficientes = False
            motivos.append("Faltan históricos similares para cotizar automáticamente")
    except Exception as e:
        logger.warning("No se pudo evaluar históricos: %s", e)
        historicos_suficientes = False

    requiere_asesor = len(motivos) > 0
    puede_bot_cotizar = not requiere_asesor

    log_msg = (
        f"[Mixto Inteligente]\n"
        f"lead_id={lead.id}\n"
        f"telefono={lead.cliente.telefono if lead.cliente_id else '?'}\n"
        f"puede_bot_cotizar={puede_bot_cotizar}\n"
        f"requiere_asesor={requiere_asesor}\n"
        f"motivos={motivos}\n"
        f"historicos_suficientes={historicos_suficientes}\n"
        f"confianza_suficiente={confianza_suficiente}\n"
        f"decision={'BOT_COTIZA' if puede_bot_cotizar else 'DERIVAR_ASESOR'}"
    )
    logger.info(log_msg)

    return {
        "puede_bot_cotizar": puede_bot_cotizar,
        "requiere_asesor": requiere_asesor,
        "motivos": motivos,
        "confianza_suficiente": confianza_suficiente,
        "historicos_suficientes": historicos_suficientes,
    }


ESTADOS_AVANZADOS = [
    "cotizado",
    "reservado",
    "confirmado",
    "programado",
    "servicio_agendado",
]


def evaluar_conversacion_avanzada(lead):
    motivos = []
    bloquear = False

    if not lead:
        return {"bloquear_bot": False, "motivos": []}

    # A. Lead ya cotizado / en estado avanzado
    if lead.estado in ESTADOS_AVANZADOS:
        motivos.append(f"Lead en estado avanzado: {lead.estado}")
        bloquear = True
    if hasattr(lead, "etapa_conversacion") and lead.etapa_conversacion in ESTADOS_AVANZADOS:
        motivos.append(f"Lead en etapa avanzada: {lead.etapa_conversacion}")
        bloquear = True

    # B. Antigüedad de conversación > 3 días
    try:
        from apps.clientes.models import Conversacion
        primera = Conversacion.objects.filter(cliente=lead.cliente).order_by("fecha").first()
        if primera:
            dias = (timezone.now() - primera.fecha).days
            if dias > 3:
                motivos.append(f"Conversación iniciada hace {dias} días")
                bloquear = True
    except Exception:
        pass

    # C. Más de 10 mensajes (cuenta cada registro como un mensaje entrante/saliente)
    try:
        from apps.clientes.models import Conversacion
        total = Conversacion.objects.filter(cliente=lead.cliente).count()
        if total > 10:
            motivos.append(f"Más de 10 mensajes en conversación ({total})")
            bloquear = True
    except Exception:
        pass

    # D. Atención humana previa
    if lead.atencion_humana or lead.requiere_asesor or lead.bot_pausado:
        motivos.append("Lead con atención humana previa")
        bloquear = True

    # E. Derivación previa
    if lead.motivo_derivacion:
        motivos.append("Lead con derivación previa")
        bloquear = True

    logger.info(
        "[ConversationGuardV2]\n"
        "lead_id=%d\n"
        "motivos=%s\n"
        "bloquear_bot=%s",
        lead.id,
        motivos,
        bloquear,
    )

    return {"bloquear_bot": bloquear, "motivos": motivos}


MENSAJE_DERIVACION_GUARD = (
    "Gracias, un asesor revisará tu consulta y te responderá en breve."
)

CONVERSACION_ADVANCED_PATTERNS = [
    r"ya pagué",
    r"ya pague",
    r"\byape\b",
    r"\bplin\b",
    r"transferencia",
    r"depósito",
    r"deposito",
    r"comprobante",
    r"ya tengo reserva",
    r"mi reserva",
    r"me dijeron",
    r"ya coordiné",
    r"ya coordine",
    r"hablé con el asesor",
    r"hable con el asesor",
    r"cambiar fecha",
    r"cambiar dirección",
    r"cambiar direccion",
    r"a qué hora viene el camión",
    r"a que hora viene el camion",
    r"a qué hora viene",
    r"\bchofer\b",
    r"\bpersonal\b",
    r"\bayudante\b",
    r"no llegaron",
    r"llegaron tarde",
    r"estoy esperando",
]

NORMAL_COTIZACION_PATTERNS = [
    r"\bpiso\b",
    r"\bascensor\b",
    r"embalaje",
    r"origen",
    r"destino",
    r"objetos?",
    r"precio",
    r"cotiza",
    r"cuánto cuesta",
    r"cuanto cuesta",
    r"medidas?",
    r"peso",
    r"camión",
    r"camion",
    r"mudanza",
    r"flete",
    r"traslado",
    r"transporte",
    r"servicio",
]


def should_bot_handle_lead(lead, incoming_message, mode=None):
    result = {
        "allow_bot": True,
        "pause_bot": False,
        "reason": "",
        "message_to_client": None,
    }

    if not lead:
        return result

    if lead.atencion_humana or lead.bot_pausado or lead.requiere_asesor:
        result["allow_bot"] = False
        result["pause_bot"] = True
        result["reason"] = "lead_en_atencion_humana"
        logger.info(
            "[Conversation Guard]\n"
            "lead_id=%d\n"
            "telefono=%s\n"
            "estado=%s\n"
            "allow_bot=%s\n"
            "pause_bot=%s\n"
            "reason=%s",
            lead.id,
            lead.cliente.telefono if lead.cliente_id else "?",
            lead.estado,
            result["allow_bot"],
            result["pause_bot"],
            result["reason"],
        )
        return result

    if incoming_message:
        msg_lower = incoming_message.lower()

        import re
        for pattern in CONVERSACION_ADVANCED_PATTERNS:
            if re.search(pattern, msg_lower):
                result["allow_bot"] = False
                result["pause_bot"] = True
                result["reason"] = "posible_conversacion_humana_por_whatsapp_business"
                result["message_to_client"] = MENSAJE_DERIVACION_GUARD

                lead.atencion_humana = True
                lead.bot_pausado = True
                lead.motivo_derivacion = "Posible conversación activa por WhatsApp Business"
                lead.fecha_derivacion = timezone.now()
                lead.save(update_fields=[
                    "atencion_humana", "bot_pausado",
                    "motivo_derivacion", "fecha_derivacion",
                ])
                logger.info(
                    "[Conversation Guard]\n"
                    "lead_id=%d\n"
                    "telefono=%s\n"
                    "estado=%s\n"
                    "mensaje=%s\n"
                    "pattern=%s\n"
                    "allow_bot=%s\n"
                    "pause_bot=%s\n"
                    "reason=%s",
                    lead.id,
                    lead.cliente.telefono if lead.cliente_id else "?",
                    lead.estado,
                    incoming_message[:100],
                    pattern,
                    result["allow_bot"],
                    result["pause_bot"],
                    result["reason"],
                )
                return result

    return result


def _marcar_derivacion(lead, motivos):
    lead.requiere_asesor = True
    lead.motivo_derivacion = ", ".join(motivos)
    lead.bot_pausado = True
    lead.atencion_humana = True
    lead.fecha_derivacion = timezone.now()
    lead.save(update_fields=[
        "requiere_asesor", "motivo_derivacion", "bot_pausado",
        "atencion_humana", "fecha_derivacion",
    ])
    logger.info(
        "Lead %d derivado a asesor humano. Motivos: %s",
        lead.id, ", ".join(motivos),
    )


def should_bot_reply(now=None, lead=None, channel=None):
    conf = ConfiguracionBot.obtener(channel=channel)
    now = now or timezone.localtime()
    hora_actual = now.time()
    dia_semana = now.weekday()

    logger.info(
        "should_bot_reply | bot_activo=%s | modo_atencion=%s | dia=%d | hora=%s",
        conf.bot_activo,
        conf.modo_atencion,
        dia_semana,
        hora_actual.strftime("%H:%M"),
    )

    # 1. bot apagado
    if not conf.bot_activo:
        logger.info("[Bot Control]\nbot_activo=False\ndecision=BOT_NO_RESPONDE\nreason=bot_apagado")
        return False

    # 2. override
    if conf.override_activo and conf.override_modo != "none":
        if conf.override_hasta and timezone.now() > conf.override_hasta:
            conf.override_activo = False
            conf.override_modo = "none"
            conf.save(update_fields=["override_activo", "override_modo"])
        else:
            if conf.override_modo == "force_bot":
                if lead and evaluar_conversacion_avanzada(lead)["bloquear_bot"]:
                    lead._v2_blocked = True
                    logger.info(
                        "[Bot Control]\noverride=%s\ndecision=BOT_NO_RESPONDE\nreason=v2_conversacion_avanzada",
                        conf.override_modo,
                    )
                    return False
                logger.info(
                    "[Bot Control]\noverride=%s\ndecision=BOT_RESPONDE\nreason=override_manual",
                    conf.override_modo,
                )
                if lead and conf.modo_atencion == "mixto":
                    evaluar_mixto_inteligente(lead)
                return True
            if conf.override_modo == "force_human":
                logger.info(
                    "[Bot Control]\noverride=%s\ndecision=BOT_NO_RESPONDE\nreason=override_manual",
                    conf.override_modo,
                )
                return False
            if conf.override_modo == "force_mixto":
                if lead and lead.lista_objetos:
                    evaluation = evaluar_mixto_inteligente(lead)
                    if evaluation["requiere_asesor"]:
                        _marcar_derivacion(lead, evaluation["motivos"])
                        logger.info(
                            "[Bot Control]\noverride=%s\ndecision=BOT_NO_RESPONDE\nreason=derivar_asesor",
                            conf.override_modo,
                        )
                        return False
                if lead and evaluar_conversacion_avanzada(lead)["bloquear_bot"]:
                    lead._v2_blocked = True
                    logger.info(
                        "[Bot Control]\noverride=%s\ndecision=BOT_NO_RESPONDE\nreason=v2_conversacion_avanzada",
                        conf.override_modo,
                    )
                    return False
                logger.info(
                    "[Bot Control]\noverride=%s\ndecision=BOT_RESPONDE\nreason=mixto_simple",
                    conf.override_modo,
                )
                return True

    # 3. modo atencion humano
    if conf.modo_atencion == "humano":
        logger.info("[Bot Control]\noverride=none\ndecision=BOT_NO_RESPONDE\nreason=modo_humano")
        return False

    # 4. evaluar horario (para modo bot y mixto)
    dentro_horario, rango = _is_in_schedule(conf, dia_semana, hora_actual, now, channel=channel)

    if conf.modo_atencion == "mixto":
        if not dentro_horario:
            logger.info(
                "[Bot Control]\noverride=none\ndecision=BOT_NO_RESPONDE\nreason=fuera_de_horario",
            )
            return False
        if lead and (lead.requiere_asesor or lead.bot_pausado):
            logger.info(
                "[Bot Control]\noverride=none\ndecision=BOT_NO_RESPONDE\nreason=lead_ya_derivado",
            )
            return False
        if lead and lead.lista_objetos:
            evaluation = evaluar_mixto_inteligente(lead)
            if evaluation["requiere_asesor"]:
                _marcar_derivacion(lead, evaluation["motivos"])
                logger.info(
                    "[Bot Control]\noverride=none | mixto_inteligente\ndecision=BOT_NO_RESPONDE\nreason=derivar_asesor",
                )
                return False
        if lead and evaluar_conversacion_avanzada(lead)["bloquear_bot"]:
            lead._v2_blocked = True
            logger.info(
                "[Bot Control]\noverride=none | v2_conversacion_avanzada\ndecision=BOT_NO_RESPONDE\nreason=v2_conversacion_avanzada",
            )
            return False
        logger.info(
            "[Bot Control]\noverride=none | mixto_inteligente | horario=%s\ndecision=BOT_RESPONDE\nreason=mixto_simple",
            rango or "legacy",
        )
        return True

    # 5. modo bot: horarios programados (BotSchedule + legacy)
    if conf.modo_atencion == "bot":
        if dentro_horario:
            if lead and evaluar_conversacion_avanzada(lead)["bloquear_bot"]:
                lead._v2_blocked = True
                logger.info(
                    "[Bot Control]\noverride=none | horario=%s | v2_conversacion_avanzada\ndecision=BOT_NO_RESPONDE\nreason=v2_conversacion_avanzada",
                    rango,
                )
                return False
            logger.info(
                "[Bot Control]\noverride=none | horario=%s\ndecision=BOT_RESPONDE\nreason=horario_normal",
                rango,
            )
            return True
        logger.info(
            "[Bot Control]\noverride=none\ndecision=BOT_NO_RESPONDE\nreason=fuera_de_horario",
        )
        return False

    logger.info("[Bot Control]\ndecision=BOT_NO_RESPONDE\nreason=modo_desconocido")
    return False


def extract_event(payload):
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        metadata = value.get("metadata", {})
        message = value["messages"][0]
        message_type = message.get("type", "")
        if not message_type:
            if "text" in message:
                message_type = "text"
            elif "image" in message:
                message_type = "image"

        event = {
            "phone": message["from"],
            "phone_number_id": metadata.get("phone_number_id", ""),
            "message_id": message.get("id", ""),
            "type": message_type,
            "text": "",
            "media_id": "",
            "mime_type": "",
            "sha256": "",
            "caption": "",
        }
        if event["type"] == "text":
            event["text"] = message.get("text", {}).get("body", "")
        elif event["type"] in {"image", "audio", "document"}:
            media = message.get(event["type"], {})
            event.update(
                {
                    "media_id": media.get("id", ""),
                    "mime_type": media.get("mime_type", ""),
                    "sha256": media.get("sha256", ""),
                    "caption": media.get("caption", ""),
                }
            )
        elif event["type"] == "location":
            location = message.get("location", {})
            event["text"] = f"{location.get('latitude', '')},{location.get('longitude', '')}"
        return event
    except (KeyError, IndexError, TypeError):
        return None


def extract_message(payload):
    event = extract_event(payload)
    if not event:
        return None, None
    return event["phone"], event["text"]
