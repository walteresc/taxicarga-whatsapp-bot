import hmac
import hashlib
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import requests

from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp
from apps.whatsapp_bot_v4.models import ConversationOwnership, WebhookEvent
from .conversation_service import ConversationService
from .bot_control_service import can_bot_respond

logger = logging.getLogger(__name__)


def verify_ycloud_signature(request):
    """Validar firma HMAC de YCloud. Formato: Ycloud-Signature: t=timestamp,s=signature"""

    # YCloud envía: Ycloud-Signature: t=1787110642,s=02cafad34935614384b99f99366ef91b264eba3a51127a40c1472d9b32c2930a
    signature_header = request.headers.get('Ycloud-Signature', '')

    if not signature_header:
        logger.error("[YCloud] Missing Ycloud-Signature header")
        return False

    # Extraer timestamp y signature: t=...,s=...
    parts = {}
    for part in signature_header.split(','):
        if '=' in part:
            key, value = part.split('=', 1)
            parts[key.strip()] = value.strip()

    timestamp = parts.get('t', '')
    signature = parts.get('s', '')

    if not signature:
        logger.error("[YCloud] Missing signature in Ycloud-Signature header")
        return False

    body = request.body

    # Intentar dos formatos de firma:
    # 1. Solo body
    expected1 = hmac.new(
        settings.YCLOUD_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    # 2. timestamp.body (formato común)
    signed_content = f"{timestamp}.{body.decode('utf-8')}" if isinstance(body, bytes) else f"{timestamp}.{body}"
    expected2 = hmac.new(
        settings.YCLOUD_WEBHOOK_SECRET.encode(),
        signed_content.encode() if isinstance(signed_content, str) else signed_content,
        hashlib.sha256
    ).hexdigest()

    match1 = hmac.compare_digest(signature, expected1)
    match2 = hmac.compare_digest(signature, expected2)

    logger.warning(f"[YCloud] Signature check - body_only={match1}, timestamp.body={match2}, signature={signature}")
    logger.warning(f"[YCloud] Hashes - expected1={expected1}, expected2={expected2}")

    return match1 or match2


@csrf_exempt
@require_http_methods(["POST"])
def ycloud_webhook(request):
    """Webhook de YCloud - reemplaza a Meta Graph API"""

    # Log inmediato
    print(f"[YCloud] WEBHOOK RECEIVED AT {timezone.now()}")
    logger.warning(f"[YCloud] WEBHOOK RECEIVED AT {timezone.now()}")

    if not verify_ycloud_signature(request):
        logger.warning("[YCloud] Invalid YCloud signature")
        return JsonResponse({'error': 'Invalid signature'}, status=401)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("[YCloud] Invalid JSON in YCloud webhook")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    logger.warning(f"[YCloud] FULL PAYLOAD:\n{json.dumps(payload, indent=2)}")

    import uuid

    # YCloud usa 'type' no 'event'
    event_type = payload.get('type') or payload.get('event')
    data = payload.get('data', {})

    # Generar ID único: usar 'id' de data o 'id' del evento o generar UUID
    message_id = data.get('id') or payload.get('id') or str(uuid.uuid4())

    logger.warning(f"[YCloud] Event: {event_type}, Message ID: {message_id}")

    # Idempotencia: no procesar dos veces
    if WebhookEvent.objects.filter(
        source='ycloud',
        external_message_id=message_id
    ).exists():
        logger.info(f"Duplicate YCloud message {message_id}, skipping")
        return JsonResponse({'status': 'skipped'})

    # Registrar evento
    try:
        WebhookEvent.objects.create(
            source='ycloud',
            external_message_id=message_id,
            event_type=event_type
        )
    except Exception as e:
        logger.error(f"[YCloud] Error creating WebhookEvent: {e}", exc_info=True)

    # Procesar según tipo (pasar payload completo, no data)
    try:
        logger.warning(f"[YCloud] ROUTING: event_type={event_type}")
        if event_type == 'whatsapp.inbound_message.received':
            logger.warning(f"[YCloud] CALLING handle_inbound_message")
            handle_inbound_message(payload)
        elif event_type == 'whatsapp.smb.message.echoes':
            logger.warning(f"[YCloud] CALLING handle_advisor_message")
            handle_advisor_message(payload)
        elif event_type == 'whatsapp.message.updated':
            logger.warning(f"[YCloud] CALLING handle_message_update")
            handle_message_update(payload)
        elif event_type == 'whatsapp.smb.history':
            logger.info(f"History event, ignoring")
        else:
            logger.warning(f"Unknown YCloud event type: {event_type}")
    except Exception as e:
        logger.error(f"[YCloud] Error processing YCloud event: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'status': 'ok'})


def handle_inbound_message(data):
    """Cliente envió mensaje a través de YCloud

    data = payload (contiene whatsappInboundMessage)
    """
    # YCloud v2 estructura: payload.whatsappInboundMessage
    msg_data = data.get('whatsappInboundMessage', {})

    phone_number = msg_data.get('from', '').lstrip('+')
    message_text = msg_data.get('text', {}).get('body', '')
    message_id = msg_data.get('id')
    contact_name = msg_data.get('fromName', '')  # YCloud proporciona nombre del contacto

    logger.warning(f"[YCloud] Extracted - phone={phone_number}, text={message_text[:50]}, id={message_id}, name={contact_name}")

    if not phone_number or not message_text:
        logger.warning(f"Incomplete inbound message: phone={phone_number}, text={message_text}")
        return

    # Crear cliente si no existe, con nombre si YCloud lo proporciona
    from apps.clientes.models import Cliente
    cliente, created = Cliente.objects.get_or_create(
        telefono=f"+{phone_number}",
        defaults={'nombre': contact_name} if contact_name else {}
    )

    # Actualizar nombre si estaba vacío y ahora tenemos uno
    if not cliente.nombre and contact_name:
        cliente.nombre = contact_name
        cliente.save()

    # Obtener conversación más reciente o crear una nueva
    conversation = ConversacionWhatsApp.objects.filter(cliente=cliente).order_by('-actualizada_en').first()

    if not conversation:
        conversation = ConversacionWhatsApp.objects.create(cliente=cliente)

    # Guardar mensaje del cliente
    msg = MensajeWhatsApp.objects.create(
        conversacion=conversation,
        meta_message_id=message_id,
        direccion=MensajeWhatsApp.ENTRANTE,
        origen=MensajeWhatsApp.ORIGEN_CLIENTE,
        tipo='texto',
        contenido=message_text,
        estado='recibido',
        fecha_mensaje=timezone.now()
    )

    # Cliente escribió → activar bot si estaba pausado globalmente
    if conversation.bot_pausado:
        conversation.bot_pausado = False
        conversation.save(update_fields=['bot_pausado'])

    # NO resetear ownership: asesor devuelve control explícitamente
    # Si no hay ownership, crear con BOT mode
    from apps.whatsapp_bot_v4.models import ConversationOwnership
    try:
        ownership = ConversationOwnership.objects.get(conversation=conversation)
        # No cambiar ownership aquí - dejar que asesor devuelva control explícitamente
    except ConversationOwnership.DoesNotExist:
        # Primera vez: crear con BOT mode
        ConversationOwnership.objects.create(
            conversation=conversation,
            owner_type=ConversationOwnership.OWNER_BOT,
            control_mode=ConversationOwnership.MODE_AUTOMATIC
        )

    logger.info(f"Inbound message saved: conversation={conversation.id}, message_id={message_id}")

    # EXTRACCIÓN DE DATOS: Siempre extraer, incluso si bot pausado globalmente
    try:
        extract_and_fill_lead_data(conversation, message_text)
    except Exception as e:
        logger.error(f"Error extracting lead data: {e}", exc_info=True)

    # PUNTO 1+2: Validación global y de conversación
    if not can_bot_respond(conversation.id):
        logger.info(f"Bot cannot respond for conversation {conversation.id}")
        return

    # Procesar con bot (llamar ConversationService)
    try:
        process_bot_response(phone_number, message_text, conversation)
    except Exception as e:
        logger.error(f"Error processing bot response: {e}", exc_info=True)


def handle_advisor_message(data):
    """Asesor escribió desde WhatsApp Web (YCloud detectó)"""
    logger.warning(f"[YCloud] handle_advisor_message PAYLOAD: {json.dumps(data)}")

    # Estructura: data['whatsappMessage']['to'] es el CLIENTE (not 'from' que es el bot)
    msg_data = data.get('whatsappMessage', {})
    client_phone = msg_data.get('to', '').lstrip('+')  # CLIENTE es 'to', no 'from'
    message_text = msg_data.get('text', {}).get('body', '')
    message_id = msg_data.get('id')

    logger.warning(f"[YCloud] Advisor extracted - client_phone={client_phone}, text={message_text[:50] if message_text else 'EMPTY'}, id={message_id}")

    if not client_phone:
        logger.warning("Incomplete advisor message - no client_phone")
        return

    # Buscar conversación del CLIENTE
    try:
        from apps.clientes.models import Cliente
        cliente = Cliente.objects.get(telefono=f"+{client_phone}")
        conversation = ConversacionWhatsApp.objects.filter(cliente=cliente).order_by('-actualizada_en').first()
        if not conversation:
            logger.warning(f"[YCloud] Conversation not found for {client_phone}")
            return
    except Cliente.DoesNotExist:
        logger.warning(f"[YCloud] Cliente not found for {client_phone}")
        return

    # Guardar mensaje del asesor
    MensajeWhatsApp.objects.create(
        conversacion=conversation,
        meta_message_id=message_id,
        direccion=MensajeWhatsApp.SALIENTE,
        origen=MensajeWhatsApp.ORIGEN_ASESOR,
        tipo='texto',
        contenido=message_text,
        estado='enviado'
    )

    # Pausa bot automática
    ownership, _ = ConversationOwnership.objects.get_or_create(conversation=conversation)
    ownership.owner_type = ConversationOwnership.OWNER_ADVISOR
    ownership.last_human_message_at = timezone.now()
    ownership.save()

    logger.info(f"Advisor message detected via YCloud, bot paused for conversation {conversation.id}")


def handle_message_update(data):
    """Actualización de estado de mensaje (sent, delivered, read)"""
    message_id = data.get('id')
    status = data.get('status')

    try:
        msg = MensajeWhatsApp.objects.get(meta_message_id=message_id)
        msg.estado = status
        msg.save(update_fields=['estado'])
        logger.info(f"Message {message_id} status updated to {status}")
    except MensajeWhatsApp.DoesNotExist:
        logger.warning(f"Message {message_id} not found for status update")


def process_bot_response(phone_number, message_text, conversation):
    """Procesar respuesta del bot con OpenAI

    PUNTO 3: Validación antes de LLM
    PUNTO 4: Validación antes de enviar
    """
    from openai import OpenAI
    from django.conf import settings

    # PUNTO 3: Validar nuevamente antes de LLM
    if not can_bot_respond(conversation.id):
        logger.warning(f"Response blocked pre-LLM: control changed for conversation {conversation.id}")
        return

    logger.info(f"Processing bot response for {phone_number}: {message_text}")

    # Obtener historial de conversación (últimos 15 mensajes para incluir contexto del asesor)
    historial = list(MensajeWhatsApp.objects.filter(conversacion=conversation).order_by('fecha_mensaje').values('origen', 'contenido'))[-15:]

    messages = []
    for msg in historial:
        if msg['origen'] == MensajeWhatsApp.ORIGEN_CLIENTE:
            role = "user"
            content = msg['contenido']
        elif msg['origen'] == MensajeWhatsApp.ORIGEN_ASESOR:
            # Asesor: prefijo para que OpenAI entienda el contexto
            role = "user"
            content = f"[ASESOR]: {msg['contenido']}"
        else:  # BOT
            role = "assistant"
            content = msg['contenido']

        messages.append({"role": role, "content": content})

    # Agregar mensaje actual del cliente
    messages.append({"role": "user", "content": message_text})

    # Llamar a OpenAI
    try:
        logger.info(f"Creating OpenAI client with key: {settings.OPENAI_API_KEY[:20]}...")
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        logger.info(f"OpenAI client created. Calling with model: {settings.OPENAI_MODEL}")
        logger.info(f"Messages to send: {messages}")

        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": """Eres asistente para empresa de mudanzas.

INSTRUCCIONES CRÍTICAS:
- LEE EL CONTEXTO COMPLETO incluyendo mensajes de asesor (marcados [ASESOR])
- NUNCA contradijas lo que dijo el asesor. Si asesor sugirió algo, APOYA la sugerencia
- Una pregunta a la vez. 1-2 oraciones máximo
- Sé amable y profesional

FLUJO:
1. Recopila: origen, destino, qué se mueve, embalaje sí/no
2. Da PRECIO (lo principal)
3. Solo si cliente reserva: pide fecha
4. Si solo consulta: no insistas en datos adicionales

Ejemplo: Si asesor dice "pueden enviar fotos", NO digas "no es necesario". Continúa respetando esa sugerencia."""},
                *messages
            ],
            temperature=0.7,
            max_tokens=80
        )
        response_text = response.choices[0].message.content
        logger.info(f"OpenAI response received: {response_text}")
    except Exception as e:
        logger.error(f"Error calling OpenAI: {e}", exc_info=True)
        response_text = "Disculpa, hay un problema técnico. Por favor intenta más tarde."

    # PUNTO 4: Validar nuevamente justo antes de enviar
    if not can_bot_respond(conversation.id):
        logger.warning(f"Response blocked pre-send: control changed to asesor for conversation {conversation.id}")
        return

    send_via_ycloud(phone_number, response_text)

    # Guardar respuesta
    MensajeWhatsApp.objects.create(
        conversacion=conversation,
        direccion=MensajeWhatsApp.SALIENTE,
        origen=MensajeWhatsApp.ORIGEN_BOT,
        tipo='texto',
        contenido=response_text,
        estado='enviado'
    )


def send_via_ycloud(phone_number, message_text):
    """Enviar mensaje via YCloud API v2"""
    import requests

    # ENDPOINT CORRECTO
    url = "https://api.ycloud.com/v2/whatsapp/messages"

    headers = {
        'X-API-Key': settings.YCLOUD_API_KEY,
        'Content-Type': 'application/json'
    }

    # Normalizar números (asegurar E.164 format: +XXXXXXXXXXX)
    recipient = phone_number if phone_number.startswith('+') else f'+{phone_number}'
    sender = settings.YCLOUD_SENDER_PHONE if settings.YCLOUD_SENDER_PHONE.startswith('+') else f'+{settings.YCLOUD_SENDER_PHONE}'

    # PAYLOAD CORRECTO (text debe ser objeto con body)
    payload = {
        'from': sender,
        'to': recipient,
        'type': 'text',
        'text': {
            'body': message_text
        }
    }

    logger.info(f"[YCloud] Sending to {recipient}: {message_text[:50]}")
    logger.warning(f"[YCloud] PAYLOAD: {json.dumps(payload)}")

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)

        logger.warning(f"[YCloud] STATUS: {response.status_code}")
        logger.warning(f"[YCloud] RESPONSE: {response.text}")

        if response.status_code == 200 or response.status_code == 202:
            logger.info(f"[YCloud] Message accepted: {response.json().get('id')}")
            return response.json()
        else:
            logger.error(f"[YCloud] Error {response.status_code}: {response.text}")
            return None
    except requests.RequestException as e:
        logger.error(f"[YCloud] Request error: {e}")
        return None


def extract_and_fill_lead_data(conversation, message_text):
    """Extraer datos del mensaje y llenar ficha del Lead.
    Se ejecuta SIEMPRE, incluso con bot pausado globalmente.
    """
    from openai import OpenAI
    from apps.leads.models import Lead
    from django.conf import settings

    if not conversation.lead_id:
        logger.info(f"[DataExtraction] No lead for conversation {conversation.id}")
        return

    lead = conversation.lead

    # Prompt para extracción
    extraction_prompt = """Analiza este mensaje de cliente y extrae los siguientes datos si están presentes:
- Origen (dirección o distrito)
- Destino (dirección o distrito)
- Tipo de servicio (mudanza, carga, etc)
- Piso origen
- Piso destino
- Tiene ascensor origen
- Tiene ascensor destino
- Objetos a mover (sofá, cama, escritorio, etc)
- Requiere embalaje
- Fecha aproximada

Responde SOLO con JSON sin explicación:
{"origen": "...", "destino": "...", "tipo": "...", ...}
Si no encuentras un dato, omítelo del JSON.

Mensaje: {message}"""

    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Eres un asistente que extrae datos de mensajes de clientes. Responde SOLO con JSON."},
                {"role": "user", "content": extraction_prompt.format(message=message_text)}
            ],
            temperature=0.3,
            max_tokens=200
        )

        import json
        data = json.loads(response.choices[0].message.content)

        # Llenar campos del Lead
        if data.get('origen'):
            lead.distrito_origen = data['origen'][:100]
        if data.get('destino'):
            lead.distrito_destino = data['destino'][:100]
        if data.get('tipo'):
            lead.tipo_servicio = data['tipo'][:50]
        if data.get('piso_origen'):
            lead.piso_origen = int(data['piso_origen']) if str(data['piso_origen']).isdigit() else None
        if data.get('piso_destino'):
            lead.piso_destino = int(data['piso_destino']) if str(data['piso_destino']).isdigit() else None
        if 'ascensor_origen' in data:
            lead.ascensor_origen = data['ascensor_origen'].lower() in ['si', 'sí', 'true', '1']
        if 'ascensor_destino' in data:
            lead.ascensor_destino = data['ascensor_destino'].lower() in ['si', 'sí', 'true', '1']
        if data.get('objetos'):
            lead.lista_objetos = data['objetos'][:500]
        if 'embalaje' in data:
            lead.modalidad_servicio = "con_embalaje" if data['embalaje'].lower() in ['si', 'sí', 'true', '1'] else "solo_transporte"
        if data.get('fecha'):
            lead.fecha_servicio = data['fecha'][:100]

        lead.save()
        logger.info(f"[DataExtraction] Lead {lead.id} updated with: {list(data.keys())}")

    except Exception as e:
        logger.warning(f"[DataExtraction] Error extracting data: {e}")


def process_pending_conversations():
    """Al activar bot: revisar conversaciones donde cliente escribió sin respuesta"""
    from datetime import timedelta
    from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp

    # Conversaciones activas en últimas 24h
    conversations = ConversacionWhatsApp.objects.filter(
        creada_en__gte=timezone.now() - timedelta(hours=24),
        estado_atencion__in=['bot', 'asesor']
    ).select_related('cliente')

    for conversation in conversations:
        # Último mensaje de cliente
        last_client_msg = MensajeWhatsApp.objects.filter(
            conversacion=conversation,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE
        ).order_by('-fecha_mensaje').first()

        if not last_client_msg:
            continue

        # Hay respuesta del bot después del último mensaje del cliente?
        last_bot_msg = MensajeWhatsApp.objects.filter(
            conversacion=conversation,
            origen=MensajeWhatsApp.ORIGEN_BOT,
            fecha_mensaje__gt=last_client_msg.fecha_mensaje
        ).first()

        # Si no hay respuesta del bot, procesar
        if not last_bot_msg:
            logger.info(f"[PendingConv] Conv {conversation.id}: cliente sin respuesta desde {last_client_msg.fecha_mensaje}")
            try:
                process_bot_response(
                    conversation.cliente.telefono.lstrip('+'),
                    last_client_msg.contenido,
                    conversation
                )
            except Exception as e:
                logger.error(f"[PendingConv] Error processing {conversation.id}: {e}", exc_info=True)
