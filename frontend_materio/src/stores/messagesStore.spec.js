/**
 * FASE 5B: Messages store tests
 * Reproduces REAL-0010 timeline issue: response.messages not preserved
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useMessagesStore } from './messagesStore'

// Fixture: Real response from /dashboard/whatsapp/conversaciones/1/mensajes/
const REAL_ENDPOINT_RESPONSE = {
  messages: [
    {
      id: 1,
      senderType: 'customer',
      senderName: 'Walter',
      source: 'whatsapp_customer',
      badge: null,
      type: 'text',
      text: 'Mensaje de prueba desde webhook',
      timestamp: '2023-08-26T13:20:00+00:00',
      status: 'recibido',
      avatar: null,
    },
    {
      id: 145,
      senderType: 'customer',
      senderName: 'Walter',
      source: 'whatsapp_customer',
      badge: null,
      type: 'text',
      text: 'FASE5B-SSE-WALTER-REAL-0010',
      timestamp: '2026-08-26T22:34:15.730622+00:00',
      status: 'recibido',
      avatar: null,
    },
  ],
  total: 2,
  conversation_id: 1,
}

describe('messagesStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('loadConversationMessages', () => {
    it('should parse data.messages from real endpoint response', async () => {
      const store = useMessagesStore()

      // Mock fetch
      global.fetch = vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => REAL_ENDPOINT_RESPONSE,
      }))

      // Load messages
      const conversationId = 1
      await store.loadConversationMessages(conversationId)

      // Verify parser extracted data.messages
      const messages = store.getMessages(conversationId)
      console.log('[TEST] Loaded messages:', messages)

      expect(messages).toHaveLength(2)
      expect(messages[0].id).toBe(1)
      expect(messages[1].id).toBe(145)
      expect(messages[1].text).toBe('FASE5B-SSE-WALTER-REAL-0010')
    })

    it('should preserve all fields from REST response', async () => {
      const store = useMessagesStore()

      global.fetch = vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => REAL_ENDPOINT_RESPONSE,
      }))

      const conversationId = 1
      await store.loadConversationMessages(conversationId)

      const messages = store.getMessages(conversationId)
      const real0010 = messages.find(m => m.id === 145)

      // All fields normalized to canonical format
      expect(real0010).toBeDefined()
      expect(real0010.senderType).toBe('customer')
      expect(real0010.senderName).toBe('Walter')
      expect(real0010.contentType).toBe('text')
      expect(real0010.text).toBe('FASE5B-SSE-WALTER-REAL-0010')
      expect(real0010.timestamp).toBeDefined()
      expect(real0010.status).toBe('recibido')
    })

    it('should NOT confuse data.total with message count', async () => {
      const store = useMessagesStore()

      // Response with total !== array length (common mistake)
      const response = {
        messages: [{ id: 1, text: 'msg1', timestamp: '2026-01-01T00:00:00+00:00' }],
        total: 100, // Different from array length
        conversation_id: 1,
      }

      global.fetch = vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => response,
      }))

      const conversationId = 1
      await store.loadConversationMessages(conversationId)

      const messages = store.getMessages(conversationId)
      // Must return 1 message, not 100
      expect(messages).toHaveLength(1)
    })

    it('should use consistent key (Number or String)', async () => {
      const store = useMessagesStore()

      global.fetch = vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => REAL_ENDPOINT_RESPONSE,
      }))

      // Load with number key
      const conversationId = 1
      await store.loadConversationMessages(conversationId)

      // Read with number key
      const messages1 = store.getMessages(1)
      // Read with string key
      const messages2 = store.getMessages('1')

      // Both should return same data (JavaScript handles this)
      expect(messages1).toHaveLength(2)
      expect(messages2).toHaveLength(2)
      expect(messages1).toEqual(messages2)
    })

    it('should REAL-0010 appear exactly once after load + upsert', async () => {
      const store = useMessagesStore()

      global.fetch = vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => REAL_ENDPOINT_RESPONSE,
      }))

      const conversationId = 1
      await store.loadConversationMessages(conversationId)

      // Then upsert same message (replay scenario)
      store.upsertMessage({
        id: 145,
        conversation_id: 1,
        text: 'FASE5B-SSE-WALTER-REAL-0010',
        timestamp: '2026-08-26T22:34:15.730622+00:00',
      })

      const messages = store.getMessages(conversationId)
      const real0010Count = messages.filter(m => m.id === 145).length

      expect(real0010Count).toBe(1) // Exactly once, not duplicated
    })
  })

  describe('upsertMessage', () => {
    it('should sort by timestamp ASC', () => {
      const store = useMessagesStore()

      store.upsertMessage({
        id: 1,
        conversation_id: 1,
        text: 'second',
        timestamp: '2026-08-26T22:34:15+00:00',
      })

      store.upsertMessage({
        id: 2,
        conversation_id: 1,
        text: 'first',
        timestamp: '2026-01-01T00:00:00+00:00',
      })

      const messages = store.getMessages(1)
      expect(messages[0].id).toBe(2) // Earlier timestamp first
      expect(messages[1].id).toBe(1) // Later timestamp second
    })
  })

  describe('getMessages', () => {
    it('should return empty array if conversation not found', () => {
      const store = useMessagesStore()
      const messages = store.getMessages(999)
      expect(messages).toEqual([])
    })
  })
})
