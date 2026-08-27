/**
 * FASE 5B: Conversaciones store (Bandeja)
 *
 * Canonical state for conversations (channels list).
 * Updated by real-time events from SSE + polling.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useConversationsStore = defineStore('conversations', () => {
  const conversations = ref([])

  /**
   * Insert or update conversation.
   */
  const upsertConversation = (conv) => {
    const existing = conversations.value.findIndex(c => c.id === conv.id)

    if (existing >= 0) {
      conversations.value[existing] = { ...conversations.value[existing], ...conv }
    } else {
      conversations.value.push(conv)
    }
  }

  /**
   * Reorder conversations by -ultima_actividad (most recent first).
   */
  const reorderConversations = () => {
    conversations.value.sort((a, b) => {
      const aTime = new Date(a.ultima_actividad || 0).getTime()
      const bTime = new Date(b.ultima_actividad || 0).getTime()
      return bTime - aTime
    })
  }

  /**
   * Update specific fields of a conversation.
   */
  const updateConversationState = (convId, data) => {
    const existing = conversations.value.findIndex(c => c.id === convId)
    if (existing >= 0) {
      conversations.value[existing] = { ...conversations.value[existing], ...data }
    }
  }

  /**
   * Get conversation by ID.
   */
  const getConversation = (id) => {
    return conversations.value.find(c => c.id === id)
  }

  /**
   * Load initial state from REST.
   * Mutates existing array to ensure reactivity in computed properties.
   */
  const loadInitial = async () => {
    try {
      const response = await fetch('/dashboard/whatsapp/conversaciones/api/active/')
      const data = await response.json()

      let loaded = []
      if (Array.isArray(data)) {
        loaded = data
      } else if (data.conversations) {
        loaded = data.conversations
      }

      // Mutate the array instead of replacing it (for reactivity)
      conversations.value.splice(0, Infinity, ...loaded)

      reorderConversations()
    } catch (error) {
      console.error('Failed to load initial conversations:', error)
    }
  }

  /**
   * Clear store (for logout).
   * Mutate the array instead of replacing it.
   */
  const clear = () => {
    conversations.value.splice(0, Infinity)
  }

  return {
    conversations,
    upsertConversation,
    reorderConversations,
    updateConversationState,
    getConversation,
    loadInitial,
    clear,
    count: computed(() => conversations.value.length),
  }
})
