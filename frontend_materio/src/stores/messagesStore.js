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
  const upsertMessage = msg => {
    const normalizedMsg = normalizeMessage(msg)
    const conversationId = normalizedMsg.conversationId
    const id = normalizedMsg.id

    if (!messages.value[conversationId]) {
      messages.value[conversationId] = []
    }

    const list = messages.value[conversationId]

    let existing = list.findIndex(m => m.id === id)

    // Reconcile: a real (server-issued) advisor message can arrive via TWO races —
    // the send request's own REST response, or the SSE echo of that same message —
    // whichever wins first, under a DIFFERENT id than the optimistic "local-..."
    // bubble already in the list. If not matched by id, look for that stale
    // optimistic entry (by its own clientMsgId, or by content as a fallback for the
    // SSE path, which never knows the tempId) and reuse its EXACT array slot.
    //
    // This must replace IN PLACE rather than remove-then-push: v-for keys on
    // clientMsgId specifically so this transition never changes the DOM node's key.
    // Splicing out the old entry and pushing a new one (even synchronously, even
    // merged into one Vue flush) still changes the v-for key from tempId to the
    // real id, which tears down and recreates the DOM node — replaying its CSS
    // entrance animation. THAT replay, not an actual double-render, is what reads
    // as "appears, disappears, appears again".
    if (existing < 0) {
      const clientKey = normalizedMsg.clientMsgId || id
      existing = list.findIndex(m =>
        (m.clientMsgId && m.clientMsgId === clientKey)
        || (
          typeof m.id === 'string' && m.id.startsWith('local-')
          && m.status === 'sending'
          && m.contentType === normalizedMsg.contentType
          && (m.text || '') === (normalizedMsg.text || '')
        )
      )
      if (existing >= 0) {
        normalizedMsg.clientMsgId = list[existing].clientMsgId || list[existing].id
      }
    }

    let upsertResult = 'inserted'

    if (existing >= 0) {
      const prev = list[existing]
      const merged = { ...prev, ...normalizedMsg }

      // Outbound media messages publish their SSE snapshot the instant the row is
      // created — BEFORE the upload/adjunto exists — so that event always carries
      // attachments: null. If it arrives after the real HTTP reconcile (or a REST
      // reload) already attached the file, don't let it erase what we already have.
      if (!normalizedMsg.attachments && prev.attachments) {
        merged.attachments = prev.attachments
      }

      // CRITICAL: Use splice for Vue 3 reactivity — array[i] = value does NOT trigger updates
      list.splice(existing, 1, merged)
      upsertResult = 'updated'
    } else {
      list.push(normalizedMsg)
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
  const getMessages = conversationId => {
    return messages.value[conversationId] || []
  }

  /**
   * Remove a single message (used to drop an optimistic bubble once replaced
   * by its real, server-confirmed counterpart).
   */
  const removeMessage = (conversationId, id) => {
    const list = messages.value[conversationId]
    if (!list) return
    const idx = list.findIndex(m => m.id === id)
    if (idx >= 0) {
      list.splice(idx, 1)
    }
  }

  /**
   * Load initial messages for a conversation from REST.
   * Mutates existing array (or creates new one) to ensure reactivity in computed properties.
   */
  const loadConversationMessages = async conversationId => {
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
  const clearConversation = conversationId => {
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
    removeMessage,
    loadConversationMessages,
    clearConversation,
    clear,
    count: computed(() => Object.values(messages.value).flat().length),
  }
})
