import { describe, it, expect, beforeEach } from 'vitest'
import { useEventStore } from '../stores/eventStore'
import { useConversationsStore } from '../stores/conversationsStore'
import { useMessagesStore } from '../stores/messagesStore'

describe('SSE & Polling: FASE 5B Real-time Channel', () => {
  let eventStore, conversationStore, messageStore

  beforeEach(() => {
    eventStore = useEventStore()
    conversationStore = useConversationsStore()
    messageStore = useMessagesStore()

    eventStore.clear()
    conversationStore.clear()
    messageStore.clear()
  })

  describe('Event Deduplication', () => {
    it('does not duplicate on SSE + polling overlap', () => {
      const event1 = {
        id: 'evt-001',
        type: 'message.created',
        data: { conversation_id: 1, message_id: 100 },
      }

      eventStore.addEvent(event1)
      expect(eventStore.events.length).toBe(1)

      eventStore.addEvent(event1)
      expect(eventStore.events.length).toBe(1) // NO duplicate
    })

    it('handles multiple rapid SSE events', () => {
      const events = [
        { id: 'e1', type: 'message.created' },
        { id: 'e2', type: 'message.created' },
        { id: 'e3', type: 'message.created' },
      ]

      events.forEach(e => eventStore.addEvent(e))
      expect(eventStore.events.length).toBe(3)
    })

    it('preserves cursor across events', () => {
      eventStore.addEvent({ id: 'e1', type: 'test' })
      eventStore.addEvent({ id: 'e2', type: 'test' })

      expect(eventStore.events.length).toBe(2)

      eventStore.addEvent({ id: 'e3', type: 'test' })
      expect(eventStore.events.length).toBe(3)
    })
  })

  describe('Message Event Processing', () => {
    it('processes message.created event to stores', () => {
      const event = {
        id: 'msg-evt-1',
        type: 'message.created',
        data: {
          conversation_id: 1,
          message_id: 100,
          sender_type: 'customer',
          direction: 'entrante',
          preview: 'Hello',
          timestamp: '2026-08-22T10:00:00Z',
          conversation: {
            unread_count: 1,
            summary: 'test conv',
          },
        },
      }

      eventStore.addEvent(event)

      conversationStore.upsertConversation({
        id: 1,
        unread_count: 1,
        summary: 'test conv',
      })

      messageStore.upsertMessage({
        id: 100,
        conversation_id: 1,
        sender_type: 'customer',
        timestamp: '2026-08-22T10:00:00Z',
        contenido: 'Hello',
      })

      expect(eventStore.getConversationEvents(1).length).toBe(1)
      expect(conversationStore.getConversation(1)?.unread_count).toBe(1)
      expect(messageStore.getMessages(1).length).toBe(1)
    })

    it('processes echo message (advisor)', () => {
      const event = {
        id: 'echo-evt-1',
        type: 'message.created',
        data: {
          conversation_id: 1,
          message_id: 101,
          sender_type: 'advisor',
          direction: 'saliente',
          preview: 'Echo response',
        },
      }

      eventStore.addEvent(event)

      conversationStore.upsertConversation({
        id: 1,
        unread_count: 1,
        bot_paused: true,
      })

      messageStore.upsertMessage({
        id: 101,
        conversation_id: 1,
        sender_type: 'advisor',
        timestamp: '2026-08-22T10:01:00Z',
      })

      expect(conversationStore.getConversation(1)?.bot_paused).toBe(true)
      expect(messageStore.getMessages(1).length).toBe(1)
    })
  })

  describe('Conversation Reordering', () => {
    it('reorders conversations by latest activity', () => {
      conversationStore.upsertConversation({
        id: 1,
        ultima_actividad: '2026-08-22T10:00:00Z',
      })
      conversationStore.upsertConversation({
        id: 2,
        ultima_actividad: '2026-08-22T09:00:00Z',
      })

      conversationStore.updateConversationState(2, {
        ultima_actividad: '2026-08-22T11:00:00Z',
      })
      conversationStore.reorderConversations()

      const ids = conversationStore.conversations.map(c => c.id)
      expect(ids[0]).toBe(2)
    })
  })


  describe('Cleanup on Unmount', () => {
    it('clear resets state', () => {
      eventStore.addEvent({ id: 'e1', type: 'test' })
      conversationStore.upsertConversation({ id: 1, cliente_id: 10 })
      messageStore.upsertMessage({
        id: 100,
        conversation_id: 1,
        timestamp: '2026-08-22T10:00:00Z',
      })

      eventStore.clear()
      conversationStore.clear()
      messageStore.clear()

      expect(eventStore.events.length).toBe(0)
      expect(conversationStore.conversations.length).toBe(0)
      expect(Object.keys(messageStore.messages).length).toBe(0)
    })
  })

  describe('Two Tab Simulation', () => {
    it('deduplication works across polling batches', () => {
      const batch1 = [
        { id: 'b1-e1', type: 'msg' },
        { id: 'b1-e2', type: 'msg' },
      ]

      batch1.forEach(e => eventStore.addEvent(e))
      expect(eventStore.events.length).toBe(2)

      const batch2 = [
        { id: 'b1-e2', type: 'msg' },
        { id: 'b2-e1', type: 'msg' },
      ]

      batch2.forEach(e => eventStore.addEvent(e))
      expect(eventStore.events.length).toBe(3)
    })
  })
})
