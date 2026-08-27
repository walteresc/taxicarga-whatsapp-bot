/**
 * FASE 5B: Messages store (Timeline)
 *
 * Canonical state for messages within a conversation.
 * Updated by real-time events from SSE + polling.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { normalizeMessage } from '@/utils/messageNormalizer'

export const useMessagesStore = defineStore('messages', () => {
  const messages = ref({})

  /**
   * Insert or update message in conversation.
   * messages[conversation_id] = [{ id, timestamp, sender, ... }]
   * Normalizes sender values to: client, advisor, bot
   */
  const upsertMessage = (msg) => {
    const normalizedMsg = normalizeMessage(msg)
    const conversationId = normalizedMsg.conversationId
    const id = normalizedMsg.id

    if (!messages.value[conversationId]) {
      messages.value[conversationId] = []
    }

    const existing = messages.value[conversationId].findIndex(m => m.id === id)
    let upsertResult = 'inserted'

    if (existing >= 0) {
      // CRITICAL: Use splice for Vue 3 reactivity — array[i] = value does NOT trigger updates
      messages.value[conversationId].splice(existing, 1, { ...messages.value[conversationId][existing], ...normalizedMsg })
      upsertResult = 'updated'
    } else {
      messages.value[conversationId].push(normalizedMsg)
    }

    // TRABAJO A: Log upsert
    console.log(`[messagesStore.upsertMessage] ${upsertResult} message_id=${id} in conv_id=${conversationId}`)

    // Record upsert in diagnostics
    if (typeof window !== 'undefined' && window.__WHATSAPP_REALTIME_DIAGNOSTICS__) {
      const diagnostics = Object.values(window.__WHATSAPP_REALTIME_DIAGNOSTICS__)[0]
      if (diagnostics) {
        diagnostics.upsertCount = (diagnostics.upsertCount || 0) + 1
      }
    }

    // Sort by timestamp ASC
    messages.value[conversationId].sort((a, b) => {
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
   * Mutates existing array (or creates new one) to ensure reactivity in computed properties.
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

      // Ensure array exists
      if (!messages.value[conversationId]) {
        messages.value[conversationId] = []
      }

      let loaded = []
      if (Array.isArray(data)) {
        loaded = data.map(normalizeMessage)
        console.log('[messagesStore] Loaded array: count=' + data.length)
      } else if (data.messages) {
        loaded = data.messages.map(normalizeMessage)
        console.log('[messagesStore] Loaded from data.messages: count=' + data.messages.length)
      } else {
        console.log('[messagesStore] No messages found in response, data keys:', Object.keys(data))
      }

      // Mutate the array instead of replacing it (for reactivity)
      messages.value[conversationId].splice(0, Infinity, ...loaded)

      // Sort by timestamp
      if (messages.value[conversationId].length > 0) {
        messages.value[conversationId].sort((a, b) => {
          const aTime = new Date(a.timestamp || a.fecha_mensaje || 0).getTime()
          const bTime = new Date(b.timestamp || b.fecha_mensaje || 0).getTime()
          return aTime - bTime
        })
        console.log('[messagesStore] After sort: count=' + messages.value[conversationId].length + ', IDs:', messages.value[conversationId].map(m => m.id || m.message_id).join(','))
      }
    } catch (error) {
      console.error(`[messagesStore] Failed to load messages for conversation ${conversationId}:`, error.message)
      // Clear on error (mutate instead of replace)
      if (!messages.value[conversationId]) {
        messages.value[conversationId] = []
      } else {
        messages.value[conversationId].splice(0, Infinity)
      }
    }
  }

  /**
   * Clear messages for a conversation.
   */
  const clearConversation = (conversationId) => {
    if (messages.value[conversationId]) {
      messages.value[conversationId].splice(0, Infinity)
    }
  }

  /**
   * Clear all messages (for logout).
   * Delete all keys without replacing the object (preserves references to computed properties).
   */
  const clear = () => {
    Object.keys(messages.value).forEach(key => {
      delete messages.value[key]
    })
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
