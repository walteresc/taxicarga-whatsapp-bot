// API Service para conversaciones WhatsApp

const DASHBOARD_BASE = '/dashboard/whatsapp/conversaciones'

// Mapear estado_atencion del backend a attentionMode unificado
const mapAttentionMode = conv => {
  if (conv.estado_atencion === 'cerrada') return 'closed'
  if (conv.estado_atencion === 'asesor') return 'advisor'
  if (conv.estado_atencion === 'bot') return 'bot'

  // Fallback: si no está cerrada y no tiene asesor, es unassigned
  return conv.responsable ? 'advisor' : 'unassigned'
}

export const conversationService = {
  // Iniciar una conversación desde un número que nunca escribió (no llegó por
  // webhook). El backend crea Cliente/Lead/Conversación; el composer queda
  // bloqueado hasta que el cliente responda (ver ChatComposer pendingTemplate).
  async createManualConversation(telefono, nombre = '') {
    const response = await fetch(`${DASHBOARD_BASE}/nueva/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': this.getCsrfToken(),
      },
      credentials: 'include',
      body: JSON.stringify({ telefono, nombre }),
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`)

    return data
  },

  // Marcar/quitar de las particiones Oficina/Transportistas/Campo — Oficina
  // es siempre manual; Transportistas y Campo también admiten esto como
  // refuerzo manual además de su detección automática/histórica, que sigue
  // corriendo igual (ver apps/dashboard/views_whatsapp.py::api_active_conversations).
  async setOficina(conversationId, esOficina) {
    return this._setCategoria(conversationId, 'oficina', 'es_oficina', esOficina)
  },
  async setTransportista(conversationId, esTransportista) {
    return this._setCategoria(conversationId, 'transportista', 'es_transportista', esTransportista)
  },
  async setCampo(conversationId, esCampo) {
    return this._setCategoria(conversationId, 'campo', 'es_campo', esCampo)
  },
  async _setCategoria(conversationId, urlSegment, bodyKey, value) {
    const response = await fetch(`${DASHBOARD_BASE}/${conversationId}/${urlSegment}/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': this.getCsrfToken(),
      },
      credentials: 'include',
      body: JSON.stringify({ [bodyKey]: value }),
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok || !data.success) throw new Error(data.error || `HTTP ${response.status}`)

    return data
  },

  // Obtener conversaciones activas con filtros
  async getActiveConversations(filters = {}) {
    try {
      const params = new URLSearchParams()
      if (filters.q) params.append('q', filters.q)
      if (filters.state) params.append('state', filters.state)
      if (filters.channel) params.append('channel', filters.channel)
      if (filters.advisor) params.append('advisor', filters.advisor)

      const url = `${DASHBOARD_BASE}/api/active/?${params.toString()}`

      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'include',
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()

      return {
        conversations: data.conversations.map(conv => ({
          id: conv.id,
          name: conv.name || conv.phone || 'Desconocido',
          profile_name: conv.profile_name,
          name_usable: conv.name_usable,
          phone: conv.phone,
          channel: conv.channel.name,
          channelIcon: conv.channel.icon,
          avatar: conv.avatar,
          attentionMode: mapAttentionMode(conv),
          estadoAtencion: conv.estado_atencion,
          estadoCotizacion: conv.estado_cotizacion,
          resumen: conv.resumen,
          preview: conv.preview,
          unread: conv.unread_count,
          lastActivity: conv.last_activity,
          leadId: conv.lead_id,
          responsable: conv.responsable,
          serviceData: conv.service_data,
        })),
      }
    } catch (error) {
      console.error('Error fetching conversations:', error)
      
      return { conversations: [] }
    }
  },

  // Obtener mensajes de una conversación
  async getConversationMessages(conversationId) {
    try {
      const response = await fetch(`${DASHBOARD_BASE}/${conversationId}/mensajes/`, {
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'include',
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()

      return {
        messages: data.messages,
        total: data.total,
        conversationId: data.conversation_id,
      }
    } catch (error) {
      console.error('Error fetching messages:', error)
      
      return { messages: [], total: 0 }
    }
  },

  // Enviar mensaje
  async sendMessage(conversationId, message) {
    try {
      const response = await fetch(`${DASHBOARD_BASE}/${conversationId}/accion/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRFToken': this.getCsrfToken(),
        },
        credentials: 'include',
        body: new URLSearchParams({
          action: 'reply',
          message: message.text,
        }),
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      
      return { status: 'ok', message }
    } catch (error) {
      console.error('Error sending message:', error)
      throw error
    }
  },

  // Tomar conversación
  async takeConversation(conversationId) {
    try {
      const response = await fetch(`${DASHBOARD_BASE}/${conversationId}/accion/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRFToken': this.getCsrfToken(),
        },
        credentials: 'include',
        body: new URLSearchParams({
          action: 'take',
        }),
      })

      
      return response.ok
    } catch (error) {
      console.error('Error taking conversation:', error)
      throw error
    }
  },

  // Devolver al bot
  async returnToBot(conversationId, instruction = 'esperar') {
    try {
      const response = await fetch(`${DASHBOARD_BASE}/${conversationId}/accion/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRFToken': this.getCsrfToken(),
        },
        credentials: 'include',
        body: new URLSearchParams({
          action: 'return_bot',
          instruction,
        }),
      })

      
      return response.ok
    } catch (error) {
      console.error('Error returning to bot:', error)
      throw error
    }
  },

  // Enviar a cotizar
  async sendToQuote(conversationId, reason = '') {
    try {
      const response = await fetch(`${DASHBOARD_BASE}/${conversationId}/accion/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRFToken': this.getCsrfToken(),
        },
        credentials: 'include',
        body: new URLSearchParams({
          action: 'quote',
          reason,
        }),
      })

      
      return response.ok
    } catch (error) {
      console.error('Error sending to quote:', error)
      throw error
    }
  },

  // Cerrar conversación
  async closeConversation(conversationId) {
    try {
      const response = await fetch(`${DASHBOARD_BASE}/${conversationId}/accion/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRFToken': this.getCsrfToken(),
        },
        credentials: 'include',
        body: new URLSearchParams({
          action: 'close',
        }),
      })

      
      return response.ok
    } catch (error) {
      console.error('Error closing conversation:', error)
      throw error
    }
  },

  // Editar a mano el nombre del contacto (prioridad sobre el de WhatsApp).
  // name vacío => vuelve al nombre de perfil de WhatsApp.
  async setContactName(conversationId, name) {
    const response = await fetch(`${DASHBOARD_BASE}/${conversationId}/contacto/nombre/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': this.getCsrfToken(),
      },
      credentials: 'include',
      body: JSON.stringify({ name }),
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)

    return response.json()
  },

  // Obtener estado global del bot
  async getBotStatus() {
    try {
      const response = await fetch('/webhooks/api/control/bot-status/', {
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'include',
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      
      return {
        is_paused: data.is_paused,  // true = paused, false = active
        paused_at: data.paused_at,
      }
    } catch (error) {
      console.error('Error fetching bot status:', error)
      throw error
    }
  },

  // Pausar bot globalmente
  async pauseBot() {
    try {
      const response = await fetch('/webhooks/api/control/pause-global/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': this.getCsrfToken(),
        },
        credentials: 'include',
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      
      return response.json()
    } catch (error) {
      console.error('Error pausing bot:', error)
      throw error
    }
  },

  // Activar bot globalmente
  async activateBot() {
    try {
      const response = await fetch('/webhooks/api/control/activate-global/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': this.getCsrfToken(),
        },
        credentials: 'include',
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      
      return response.json()
    } catch (error) {
      console.error('Error activating bot:', error)
      throw error
    }
  },

  // Obtener CSRF token de meta tag o cookies
  getCsrfToken() {
    // Primero intentar obtener del meta tag
    const metaTag = document.querySelector('meta[name="csrf-token"]')
    if (metaTag) {
      return metaTag.getAttribute('content')
    }

    // Si no hay meta tag, obtener de cookies
    const name = 'csrftoken'
    let cookieValue = null
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';')
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim()
        if (cookie.substring(0, name.length + 1) === name + '=') {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1))
          break
        }
      }
    }
    
    return cookieValue || ''
  },
}
