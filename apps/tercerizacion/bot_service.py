"""Bot de transportistas (Fase 3).

Flujo separado del bot de clientes por completo: estado propio
(TransportistaBotState), envío propio, nunca toca ConversationAgent/
BotConversationState. Se activa solo si TRANSPORTISTA_BOT_ENABLED=True y
respeta la pausa global del bot (bot_control_service.can_bot_respond) — el
flag apaga solo este flujo, la pausa apaga los dos.

Regla dura: si el mensaje no encaja en ningún paso reconocido, el bot NO
responde nada — nunca improvisa, cede el control al asesor humano en
silencio (el mensaje ya quedó persistido y visible en el timeline).
"""

import logging
import re
from decimal import Decimal, InvalidOperation

from django.conf import settings

from apps.whatsapp.models import MensajeAdjunto, MensajeWhatsApp

from .models import OfertaTransportista, PublicacionCarga, TransportistaBotState
from .services import extraer_codigo_oferta, lineas_detalle_permitido

logger = logging.getLogger(__name__)

_OFERTAR_RE = re.compile(r"\bofert(ar|o|amos|a)\b|\bofre(c|zc)\w*\b", re.IGNORECASE)
_CONSULTAR_RE = re.compile(r"\bconsult(ar|a|o)\b|\bduda\b|\bpregunta\b", re.IGNORECASE)
_FOTOS_RE = re.compile(r"\bfotos?\b|\bimagen(es)?\b|\bfoto\b", re.IGNORECASE)
_PRECIO_RE = re.compile(r"(\d+(?:\.\d+)?)")


def _es_ofertar(texto):
    return bool(_OFERTAR_RE.search(texto or ""))


def _es_consultar(texto):
    return bool(_CONSULTAR_RE.search(texto or ""))


def _pide_fotos(texto):
    return bool(_FOTOS_RE.search(texto or ""))


def _extraer_precio(texto):
    """Primer número que aparece en el texto. Simplificación deliberada: no
    distingue separador decimal de separador de miles (asume montos chicos
    de mudanza local, no tarifas con miles — ej. '350', '350.50')."""
    if not texto:
        return None
    match = _PRECIO_RE.search(texto)
    if not match:
        return None
    try:
        return Decimal(match.group(1))
    except InvalidOperation:
        return None


def _detalle_bot(publicacion):
    servicio = publicacion.servicio
    partes = [
        f"Detalle de OFERTA-{publicacion.codigo}:",
        *lineas_detalle_permitido(servicio),
        "",
        "Responde *ofertar* si quieres dar un precio, o *consultar* si tienes dudas.",
    ]
    return "\n".join(partes)


def _responder(conversation, texto):
    """Envía y persiste una respuesta del bot de transportistas — mismo canal
    de envío (send_via_ycloud) que ya usa el bot de clientes en producción,
    pero con sender_type/source correctamente etiquetados como bot (a
    diferencia de ese path legacy, que los deja en su default de cliente —
    ver hallazgo de la investigación previa a esta fase)."""
    from apps.whatsapp_bot_v4.services.ycloud_webhook_service import send_via_ycloud

    telefono = (conversation.cliente.telefono or "").lstrip("+")
    resultado = send_via_ycloud(telefono, texto)
    exito = bool(resultado and resultado.get("success"))

    MensajeWhatsApp.objects.create(
        conversacion=conversation,
        direccion=MensajeWhatsApp.SALIENTE,
        origen=MensajeWhatsApp.ORIGEN_BOT,
        sender_type=MensajeWhatsApp.SENDER_BOT,
        source=MensajeWhatsApp.SOURCE_BOT,
        tipo="texto",
        contenido=texto,
        estado="enviado" if exito else "error",
        error_detalle="" if exito else str((resultado or {}).get("message", "")),
    )

    if not exito:
        logger.error(f"[TransportistaBot] Envío falló para conv {conversation.id}: {resultado}")


def _avisar_asesor_fotos(conversation, publicacion):
    """Nota interna (nunca sale por WhatsApp) para que el asesor vea, en el
    timeline de la conversación del TRANSPORTISTA, que pidieron fotos — y
    decida él qué compartir, reusando 'Reenviar' desde la conversación del
    cliente real."""
    cliente_real = publicacion.servicio.cliente
    n_fotos = 0
    if cliente_real:
        n_fotos = MensajeAdjunto.objects.filter(
            mensaje__conversacion__cliente=cliente_real,
            formato=MensajeAdjunto.FORMATO_IMAGEN,
        ).count()

    MensajeWhatsApp.objects.create(
        conversacion=conversation,
        direccion=MensajeWhatsApp.SALIENTE,
        origen=MensajeWhatsApp.ORIGEN_SISTEMA,
        sender_type=MensajeWhatsApp.SENDER_SYSTEM,
        source=MensajeWhatsApp.SOURCE_SYSTEM,
        tipo="texto",
        contenido=(
            f"🔔 El transportista pidió fotos de la carga OFERTA-{publicacion.codigo}. "
            f"Hay {n_fotos} foto(s) en la conversación del cliente. Usa \"Reenviar\" "
            f"para compartir las que autorices."
        ),
        estado="enviado",
    )


def can_transportista_bot_respond(conversation_id, state=None):
    """Tres capas de pausa, INDEPENDIENTES de can_bot_respond (bot de
    clientes) a propósito — el usuario necesita poder combinar cualquier
    estado de un bot con cualquier estado del otro:
    1. TRANSPORTISTA_BOT_ENABLED (settings/.env) — kill-switch de despliegue.
    2. BotGlobalConfig.transportistas_paused — interruptor global diario,
       togglable en vivo desde el CRM, sin tocar is_paused (bot de clientes).
    3. TransportistaBotState.pausado — override por conversación individual.
    """
    if not settings.TRANSPORTISTA_BOT_ENABLED:
        return False

    from apps.whatsapp_bot_v4.models import BotGlobalConfig
    config = BotGlobalConfig.objects.first()
    if config and config.transportistas_paused:
        return False

    if state is None:
        state = TransportistaBotState.objects.filter(conversacion_id=conversation_id).first()
    if state and state.pausado:
        return False

    return True


def process_transportista_bot_response(conversation, message):
    """Punto de entrada — llamado desde process_bot_for_conversation_async
    cuando la conversación ya fue identificada como transportista. NUNCA
    adjudica ni cierra publicaciones; solo conversa, registra ofertas, y
    avisa al asesor cuando hace falta un humano."""
    texto = message.contenido or ""
    state, _ = TransportistaBotState.objects.get_or_create(conversacion=conversation)

    if not can_transportista_bot_respond(conversation.id, state=state):
        logger.info(f"[TransportistaBot] Pausado para conversation {conversation.id}")
        return

    # Un código válido siempre tiene prioridad: permite (re)identificar la
    # carga, incluso para cambiar a una publicación distinta en la misma
    # conversación.
    codigo = extraer_codigo_oferta(texto)
    if codigo:
        publicacion = PublicacionCarga.objects.filter(codigo=codigo).first()
        if not publicacion:
            # Ya se registró en tercerizacion_codigo_no_encontrado — nada más que hacer.
            return
        if publicacion.estado != PublicacionCarga.ESTADO_ABIERTA:
            _responder(
                conversation,
                f"La publicación OFERTA-{codigo} ya no está abierta "
                f"({publicacion.get_estado_display()}).",
            )
            return

        state.publicacion_activa = publicacion
        state.paso = TransportistaBotState.PASO_ESPERANDO_INTENCION
        state.save(update_fields=["publicacion_activa", "paso", "actualizado_en"])
        _responder(conversation, _detalle_bot(publicacion))
        return

    publicacion = state.publicacion_activa
    if not publicacion:
        # Sin código, sin contexto activo — no reconoce, cede al asesor en silencio.
        return

    publicacion.refresh_from_db()
    if publicacion.estado != PublicacionCarga.ESTADO_ABIERTA:
        _responder(
            conversation,
            f"La publicación OFERTA-{publicacion.codigo} ya no está abierta "
            f"({publicacion.get_estado_display()}).",
        )
        return

    if _pide_fotos(texto):
        _responder(conversation, "Lo consultaré con el equipo y te aviso.")
        _avisar_asesor_fotos(conversation, publicacion)
        return

    if state.paso == TransportistaBotState.PASO_ESPERANDO_INTENCION:
        if _es_ofertar(texto):
            state.paso = TransportistaBotState.PASO_RECOGIENDO_PRECIO
            state.save(update_fields=["paso", "actualizado_en"])
            _responder(
                conversation,
                "Perfecto. ¿Cuánto ofreces por esta carga? Responde solo el "
                "monto en soles, por ejemplo: 350",
            )
            return
        if _es_consultar(texto):
            _responder(conversation, _detalle_bot(publicacion))
            return
        return  # no reconoce -> silencio

    if state.paso in (TransportistaBotState.PASO_RECOGIENDO_PRECIO, TransportistaBotState.PASO_CONVERSANDO):
        precio = _extraer_precio(texto)
        if precio is not None:
            oferta, creada = OfertaTransportista.objects.update_or_create(
                publicacion=publicacion,
                cliente=conversation.cliente,
                defaults={
                    "precio_ofertado": precio,
                    "mensaje_origen": message,
                    "estado": OfertaTransportista.ESTADO_PENDIENTE,
                },
            )
            state.paso = TransportistaBotState.PASO_CONVERSANDO
            state.save(update_fields=["paso", "actualizado_en"])
            verbo = "Registrado" if creada else "Actualizado"
            _responder(
                conversation,
                f"{verbo}: S/ {precio} por OFERTA-{publicacion.codigo}. Un "
                f"asesor la revisará. Si quieres cambiar tu oferta, responde "
                f"con el nuevo monto.",
            )
            return
        if _es_consultar(texto):
            _responder(conversation, _detalle_bot(publicacion))
            return
        return  # no reconoce -> silencio

    return
