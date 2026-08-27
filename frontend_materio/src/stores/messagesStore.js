/**
 * FASE 5B: Messages store (Timeline)
 *
 * Canonical state for messages within a conversation.
 * Updated by real-time events from SSE + polling.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useMessagesStore = defineStore('messages', () => {
  const messages = ref({})

  /**
   * Insert or update message in conversation.
   * messages[conversation_id] = [{ id, timestamp, sender_type, ... }]
   */
  const upsertMessage = (msg) => {
    const { conversation_id, id } = msg

    if (!messages.value[conversation_id]) {
      messages.value[conversation_id] = []
    }

    const existing = messages.value[conversation_id].findIndex(m => m.id === id)

    if (existing >= 0) {
      messages.value[conversation_id][existing] = { ...messages.value[conversation_id][existing], ...msg }
    } else {
      messages.value[conversation_id].push(msg)
    }

    // Sort by timestamp ASC
    messages.value[conversation_id].sort((a, b) => {
      const aTime = new Date(a.timestamp || 0).getTime()
      const bTime = new Date(b.timestamp || 0).getTime()
      return aTime - bTime
    })
  }

  /**
   * Get all messages for a conversation.
   */
  const getMessages = (conversationId) => {
    return messages.value[conversationId] || []
  }

  /**
   * Load initial messages for a conversation from REST.
   */
  const loadConversationMessages = async (conversationId) => {
    try {
      // FIXED: Use correct Spanish endpoint name "mensajes" not "messages"
      const url = `/dashboard/whatsapp/conversaciones/${conversationId}/mensajes/`
      console.log('[messagesStore] loadConversationMessages START: conversationId=' + conversationId + ', url=' + url)

      const response = await fetch(url)
      console.log('[messagesStore] HTTP response: status=' + response.status)

      // Check for HTTP errors before attempting JSON parse
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP ${response.status}: ${errorText.substring(0, 100)}`)
      }

      const data = await response.json()
      console.log('[messagesStore] Response JSON received, type:', typeof data, 'isArray:', Array.isArray(data))

      if (Array.isArray(data)) {
        messages.value[conversationId] = data
        console.log('[messagesStore] Loaded array: count=' + data.length)
      } else if (data.messages) {
        messages.value[conversationId] = data.messages
        console.log('[messagesStore] Loaded from data.messages: count=' + data.messages.length)
      } else {
        messages.value[conversationId] = []
        console.log('[messagesStore] No messages found in response, data keys:', Object.keys(data))
      }

      // Sort by timestamp
      if (messages.value[conversationId] && messages.value[conversationId].length > 0) {
        messages.value[conversationId].sort((a, b) => {
          const aTime = new Date(a.timestamp || a.fecha_mensaje || 0).getTime()
          const bTime = new Date(b.timestamp || b.fecha_mensaje || 0).getTime()
          return aTime - bTime
        })
        console.log('[messagesStore] After sort: count=' + messages.value[conversationId].length + ', IDs:', messages.value[conversationId].map(m => m.id || m.message_id).join(','))
      }
    } catch (error) {
      console.error(`[messagesStore] Failed to load messages for conversation ${conversationId}:`, error.message)
      messages.value[conversationId] = []
    }
  }

  /**
   * Clear messages for a conversation.
   */
  const clearConversation = (conversationId) => {
    messages.value[conversationId] = []
  }

  /**
   * Clear all messages (for logout).
   */
  const clear = () => {
    messages.value = {}
  }

  return {
    messages,
    upsertMessage,
    getMessages,
    loadConversationMessages,
    clearConversation,
    clear,
    count: computed(() => Object.values(messages.value).flat().length),
  }
})
