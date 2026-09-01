/**
 * Message Normalizer - Canonical Frontend Contract
 *
 * Converts all message formats to a single canonical structure.
 * Applied at all entry points: REST, SSE, replay, snapshot.
 *
 * Canonical format:
 * {
 *   id, conversationId, externalMessageId,
 *   senderType: "customer" | "bot" | "advisor" | "unknown",
 *   direction: "inbound" | "outbound",
 *   contentType: "text" | "image" | "audio" | "video" | "document" | "location",
 *   text, timestamp, status, senderName, avatar, media
 * }
 */

/**
 * Normalize senderType to canonical values
 */
export const normalizeSenderType = raw => {
  if (!raw) return 'unknown'

  const map = {
    // Customer variants
    'customer': 'customer',
    'client': 'customer',
    'cliente': 'customer',
    'whatsapp_customer': 'customer',
    'entrante': 'customer',
    'inbound': 'customer',

    // Bot variants
    'bot': 'bot',
    'whatsapp_bot': 'bot',

    // Advisor variants
    'advisor': 'advisor',
    'adviser': 'advisor',
    'asesor': 'advisor',
    'agent': 'advisor',
    'whatsapp_advisor': 'advisor',

    // System
    'system': 'system',
  }

  return map[raw?.toLowerCase?.().trim()] || 'unknown'
}

/**
 * Normalize direction based on sender type or explicit field
 */
export const normalizeDirection = (raw, senderType) => {
  if (!raw) {
    // Infer from sender type
    return ['customer', 'system'].includes(senderType) ? 'inbound' : 'outbound'
  }

  const map = {
    'entrante': 'inbound',
    'inbound': 'inbound',
    'saliente': 'outbound',
    'outbound': 'outbound',
  }

  return map[raw?.toLowerCase?.().trim()] || 'inbound'
}

/**
 * Normalize content type to canonical values
 */
export const normalizeContentType = raw => {
  if (!raw) return 'text'

  const map = {
    'texto': 'text',
    'text': 'text',
    'message': 'text',

    'imagen': 'image',
    'image': 'image',

    'audio': 'audio',
    'voice': 'audio',

    'video': 'video',

    'documento': 'document',
    'document': 'document',
    'file': 'document',

    'ubicacion': 'location',
    'location': 'location',

    'internal-note': 'internal-note',
  }

  return map[raw?.toLowerCase?.().trim()] || 'text'
}

/**
 * Normalize message delivery status to canonical values.
 * Backend (MensajeWhatsApp.estado) uses Spanish DB values; some paths (SSE payload
 * in signals.py) send them raw/untranslated, so this is the frontend backstop even
 * when the backend serializer's own mapping (ESTADO_TO_STATUS) is bypassed.
 */
export const normalizeStatus = raw => {
  if (!raw) return 'unknown'

  const map = {
    recibido: 'received',
    received: 'received',
    pendiente: 'sending',
    sending: 'sending',
    enviado: 'sent',
    sent: 'sent',
    entregado: 'delivered',
    delivered: 'delivered',
    leido: 'read',
    read: 'read',
    error: 'failed',
    failed: 'failed',
  }

  return map[raw?.toLowerCase?.().trim()] || 'unknown'
}

/**
 * Extract text content from various field names
 * PRECEDENCE (highest to lowest): content > contenido > text > body > preview
 * preview is LAST: it's truncated and only a fallback
 */
export const extractText = msg => {
  // Explicit precedence: content (canonical English) > contenido (backend Spanish)
  if (msg.content && typeof msg.content === 'string') return msg.content
  if (msg.contenido && typeof msg.contenido === 'string') return msg.contenido
  if (msg.text && typeof msg.text === 'string') return msg.text
  if (msg.body && typeof msg.body === 'string') return msg.body

  // Preview is always last: it's truncated
  if (msg.preview && typeof msg.preview === 'string') return msg.preview
  
  return ''
}

/**
 * Normalize a single message to canonical format
 */
export const normalizeMessage = raw => {
  // Extract sender type from multiple possible fields
  const rawSenderType = raw.sender || raw.sender_type || raw.senderType || 'unknown'
  const senderType = normalizeSenderType(rawSenderType)

  // Normalize direction
  const rawDirection = raw.direction || raw.dirección || null
  const direction = normalizeDirection(rawDirection, senderType)

  // Normalize content type from multiple possible fields
  const rawContentType = raw.contentType || raw.content_type || raw.type || raw.tipo || null
  const contentType = normalizeContentType(rawContentType)

  return {
    // Identity
    id: raw.id || raw.message_id || null,
    // Stable v-for key across the optimistic → confirmed transition (id changes
    // from a local tempId to the real DB id) — see messagesStore.upsertMessage.
    clientMsgId: raw.clientMsgId || raw.client_msg_id || null,
    conversationId: raw.conversation_id || raw.conversationId || null,
    externalMessageId: raw.external_message_id || raw.externalMessageId || null,
    metaMessageId: raw.metaMessageId || raw.meta_message_id || null,

    // Sender info (explicit precedence: senderName > sender_name > nombre)
    senderType,
    senderName: raw.senderName || raw.sender_name || raw.nombre || '',
    avatar: raw.avatar || raw.avatar_url || null,

    // Message direction
    direction,

    // Content (extractText has explicit precedence: content > contenido > text > body > preview)
    contentType,
    text: extractText(raw),
    media: raw.media || raw.adjunto || null,
    attachments: raw.attachments || null,
    caption: raw.caption || null,
    replyTo: raw.replyTo || raw.reply_to || null,
    reactionEmoji: raw.reactionEmoji || raw.reaction_emoji || null,

    // Timing and status (explicit precedence: status > estado)
    timestamp: raw.timestamp || raw.fecha_mensaje || raw.created_at || null,
    status: normalizeStatus(raw.status || raw.estado),
    errorDetail: raw.errorDetail || raw.error_detalle || null,

    // Metadata (pass-through for compatibility)
    source: raw.source || null,
    badge: raw.badge || null,
  }
}

/**
 * Normalize an array of messages
 */
export const normalizeMessages = messages => {
  if (!Array.isArray(messages)) return []
  
  return messages.map(normalizeMessage)
}
