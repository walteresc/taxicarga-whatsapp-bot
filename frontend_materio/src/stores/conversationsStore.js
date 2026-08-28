/**
 * FASE 5B: Conversaciones store (Bandeja)
 *
 * Canonical state for conversations (channels list).
 * Updated by real-time events from SSE + polling.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// Backend estado_atencion (Spanish DB values) -> ChatComposer's canonical contract.
// ChatComposer.vue's attention-mode validator expects English 'bot'|'advisor'|'closed'
// (plus frontend-only 'unassigned' for when no conversation data is loaded yet).
const ATTENTION_MODE_MAP = {
  bot: 'bot',
  asesor: 'advisor',
  cerrada: 'closed',
}

const normalizeAttentionMode = raw => {
  if (!raw) return undefined

  return ATTENTION_MODE_MAP[raw] || raw
}

export const useConversationsStore = defineStore('conversations', () => {
  const conversations = ref([])

  /**
   * Insert or update conversation.
   * Normalizes field names from backend (snake_case → camelCase)
   */
  const upsertConversation = conv => {
    // Guard: reject invalid conversation IDs (redis event IDs, undefined, or non-integers)
    if (!conv.id || typeof conv.id !== 'number' || String(conv.id).includes('-')) {
      console.warn('[conversationsStore.upsertConversation] Rejecting invalid id:', conv.id)

      return
    }

    // Normalize field names
    const normalized = {
      ...conv,
      unread: conv.unread_count ?? conv.unread ?? 0,
      attentionMode: normalizeAttentionMode(conv.estado_atencion) ?? conv.attentionMode,
      estadoCotizacion: conv.estado_cotizacion ?? conv.estadoCotizacion,
      lastActivity: conv.ultima_actividad ?? conv.last_activity ?? conv.lastActivity,
    }

    const existing = conversations.value.findIndex(c => c.id === normalized.id)

    if (existing >= 0) {
      // CRITICAL: Use splice for Vue 3 reactivity — array[i] = value does NOT trigger updates
      conversations.value.splice(existing, 1, { ...conversations.value[existing], ...normalized })
    } else {
      conversations.value.push(normalized)
    }
  }

  /**
   * Reorder conversations by -ultima_actividad (most recent first).
   */
  const reorderConversations = () => {
    conversations.value.sort((a, b) => {
      const aTime = new Date(a.lastActivity || 0).getTime()
      const bTime = new Date(b.lastActivity || 0).getTime()

      return bTime - aTime
    })
  }

  /**
   * Update specific fields of a conversation.
   */
  const updateConversationState = (convId, data) => {
    const existing = conversations.value.findIndex(c => c.id === convId)
    if (existing >= 0) {
      // SSE conversation.updated sends 'attention_state' (see signals.py) — map it to
      // the same attentionMode contract used everywhere else, or the composer's
      // send input silently fails to appear/disappear on live attention changes.
      const patch = { ...data }
      if (data.attention_state !== undefined) {
        patch.attentionMode = normalizeAttentionMode(data.attention_state) ?? data.attention_state
      }

      // CRITICAL: Use splice for Vue 3 reactivity — array[i] = value does NOT trigger updates
      conversations.value.splice(existing, 1, { ...conversations.value[existing], ...patch })
    }
  }

  /**
   * Get conversation by ID.
   */
  const getConversation = id => {
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

      // Normalize each conversation and upsert (NOT splice) to ensure proper field mapping
      loaded.forEach(conv => {
        upsertConversation(conv)
      })

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
