// API Service para conversaciones WhatsApp

const DASHBOARD_BASE = '/dashboard/whatsapp/conversaciones'

export const conversationService = {
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
          name: conv.name || 'Desconocido',
          phone: conv.phone,
          channel: conv.channel.name,
          channelIcon: conv.channel.icon,
          avatar: conv.avatar,
          status: conv.estado_atencion === 'asesor' ? 'ASESOR' : 'BOT',
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

  // Obtener estado global del bot
  async getBotStatus() {
    try {
      const response = await fetch(`${DASHBOARD_BASE}/bot-status/`, {
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'include',
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      return {
        status: data.is_paused ? 'PAUSADO' : 'ACTIVO',
        is_paused: data.is_paused,
      }
    } catch (error) {
      console.error('Error fetching bot status:', error)
      throw error
    }
  },

  // Pausar bot globalmente
  async pauseBot() {
    try {
      const response = await fetch(`${DASHBOARD_BASE}/pause-global/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': this.getCsrfToken(),
        },
        credentials: 'include',
      })
      return response.ok
    } catch (error) {
      console.error('Error pausing bot:', error)
      throw error
    }
  },

  // Activar bot globalmente
  async activateBot() {
    try {
      const response = await fetch(`${DASHBOARD_BASE}/activate-global/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': this.getCsrfToken(),
        },
        credentials: 'include',
      })
      return response.ok
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
