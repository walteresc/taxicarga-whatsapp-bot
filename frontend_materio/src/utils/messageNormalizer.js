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
export const normalizeSenderType = (raw) => {
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
export const normalizeContentType = (raw) => {
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
 * Extract text content from various field names
 */
export const extractText = (msg) => {
  return msg.text || msg.content || msg.body || msg.preview || ''
}

/**
 * Normalize a single message to canonical format
 */
export const normalizeMessage = (raw) => {
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
    conversationId: raw.conversation_id || raw.conversationId || null,
    externalMessageId: raw.external_message_id || raw.externalMessageId || null,

    // Sender info
    senderType,
    senderName: raw.senderName || raw.sender_name || raw.nombre || '',
    avatar: raw.avatar || raw.avatar_url || null,

    // Message direction
    direction,

    // Content
    contentType,
    text: extractText(raw),
    media: raw.media || raw.adjunto || null,

    // Timing and status
    timestamp: raw.timestamp || raw.fecha_mensaje || raw.created_at || null,
    status: raw.status || raw.estado || 'unknown',

    // Metadata (pass-through for compatibility)
    source: raw.source || null,
    badge: raw.badge || null,
  }
}

/**
 * Normalize an array of messages
 */
export const normalizeMessages = (messages) => {
  if (!Array.isArray(messages)) return []
  return messages.map(normalizeMessage)
}
