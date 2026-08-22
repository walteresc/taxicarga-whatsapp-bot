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
      const response = await fetch(`/dashboard/whatsapp/conversaciones/${conversationId}/messages/`)
      const data = await response.json()

      if (Array.isArray(data)) {
        messages.value[conversationId] = data
      } else if (data.messages) {
        messages.value[conversationId] = data.messages
      }

      // Sort
      if (messages.value[conversationId]) {
        messages.value[conversationId].sort((a, b) => {
          const aTime = new Date(a.timestamp || 0).getTime()
          const bTime = new Date(b.timestamp || 0).getTime()
          return aTime - bTime
        })
      }
    } catch (error) {
      console.error(`Failed to load messages for conversation ${conversationId}:`, error)
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
