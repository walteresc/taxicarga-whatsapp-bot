import { describe, it, expect, beforeEach } from 'vitest'
import { useConversationsStore } from '../stores/conversationsStore'
import { useMessagesStore } from '../stores/messagesStore'
import { useEventStore } from '../stores/eventStore'

describe('Stores: FASE 5B State Management', () => {
  describe('conversationsStore', () => {
    let store

    beforeEach(() => {
      store = useConversationsStore()
      store.clear()
    })

    it('upsertConversation adds new conversation', () => {
      const conv = {
        id: 1,
        cliente_id: 10,
        channel_id: 5,
        ultima_actividad: new Date().toISOString(),
        unread_count: 1,
      }

      store.upsertConversation(conv)
      expect(store.getConversation(1)).toBeDefined()
      expect(store.conversations.length).toBe(1)
    })

    it('upsertConversation updates existing', () => {
      const conv1 = { id: 1, cliente_id: 10, channel_id: 5, ultima_actividad: '2026-08-22T10:00:00Z', unread_count: 1 }
      const conv2 = { id: 1, cliente_id: 10, channel_id: 5, ultima_actividad: '2026-08-22T11:00:00Z', unread_count: 2 }

      store.upsertConversation(conv1)
      store.upsertConversation(conv2)

      expect(store.conversations.length).toBe(1)
      expect(store.getConversation(1).unread_count).toBe(2)
    })

    it('reorderConversations sorts by ultima_actividad DESC', () => {
      store.upsertConversation({ id: 1, ultima_actividad: '2026-08-22T10:00:00Z' })
      store.upsertConversation({ id: 2, ultima_actividad: '2026-08-22T11:00:00Z' })
      store.upsertConversation({ id: 3, ultima_actividad: '2026-08-22T09:00:00Z' })
      store.reorderConversations()

      const ids = store.conversations.map(c => c.id)

      expect(ids).toEqual([2, 1, 3])
    })

    it('updateConversationState updates fields', () => {
      store.upsertConversation({ id: 1, unread_count: 5, bot_paused: false })
      store.updateConversationState(1, { unread_count: 0, bot_paused: true })

      const conv = store.getConversation(1)

      expect(conv.unread_count).toBe(0)
      expect(conv.bot_paused).toBe(true)
    })

    it('clear resets store', () => {
      store.upsertConversation({ id: 1, cliente_id: 10 })
      store.clear()

      expect(store.conversations.length).toBe(0)
    })
  })

  describe('messagesStore', () => {
    let store

    beforeEach(() => {
      store = useMessagesStore()
      store.clear()
    })

    it('upsertMessage adds message', () => {
      const msg = { id: 101, conversation_id: 1, sender_type: 'customer', timestamp: '2026-08-22T10:00:00Z', contenido: 'test' }

      store.upsertMessage(msg)

      const msgs = store.getMessages(1)

      expect(msgs.length).toBe(1)
      expect(msgs[0].id).toBe(101)
    })

    it('upsertMessage sorts by timestamp ASC', () => {
      store.upsertMessage({ id: 1, conversation_id: 1, timestamp: '2026-08-22T10:00:00Z' })
      store.upsertMessage({ id: 2, conversation_id: 1, timestamp: '2026-08-22T09:00:00Z' })

      const msgs = store.getMessages(1)

      expect(msgs[0].id).toBe(2)
      expect(msgs[1].id).toBe(1)
    })

    it('upsertMessage updates existing', () => {
      store.upsertMessage({ id: 1, conversation_id: 1, timestamp: '2026-08-22T10:00:00Z' })
      store.upsertMessage({ id: 1, conversation_id: 1, timestamp: '2026-08-22T10:00:00Z', contenido: 'updated' })

      const msgs = store.getMessages(1)

      expect(msgs.length).toBe(1)
      expect(msgs[0].contenido).toBe('updated')
    })

    it('clearConversation empties one', () => {
      store.upsertMessage({ id: 1, conversation_id: 1, timestamp: '2026-08-22T10:00:00Z' })
      store.upsertMessage({ id: 2, conversation_id: 2, timestamp: '2026-08-22T10:00:00Z' })

      store.clearConversation(1)

      expect(store.getMessages(1).length).toBe(0)
      expect(store.getMessages(2).length).toBe(1)
    })

    it('clear resets all', () => {
      store.upsertMessage({ id: 1, conversation_id: 1, timestamp: '2026-08-22T10:00:00Z' })
      store.clear()

      expect(Object.keys(store.messages).length).toBe(0)
    })
  })

  describe('eventStore', () => {
    let store

    beforeEach(() => {
      store = useEventStore()
      store.clear()
    })

    it('addEvent deduplicates by ID', () => {
      const event = { id: 'evt1', type: 'message.created', data: { msg: 'test' } }

      store.addEvent(event)
      store.addEvent(event)

      expect(store.events.length).toBe(1)
      expect(store.events[0].id).toBe('evt1')
    })

    it('getEventsByType filters', () => {
      store.addEvent({ id: 'e1', type: 'message.created' })
      store.addEvent({ id: 'e2', type: 'conversation.updated' })
      store.addEvent({ id: 'e3', type: 'message.created' })

      const created = store.getEventsByType('message.created')

      expect(created.length).toBe(2)
    })

    it('getConversationEvents filters', () => {
      store.addEvent({ id: 'e1', type: 'message.created', data: { conversation_id: 1 } })
      store.addEvent({ id: 'e2', type: 'message.created', data: { conversation_id: 2 } })

      const conv1 = store.getConversationEvents(1)

      expect(conv1.length).toBe(1)
    })

    it('clear resets all', () => {
      store.addEvent({ id: 'e1', type: 'test' })
      expect(store.events.length).toBe(1)

      store.clear()
      expect(store.events.length).toBe(0)
    })
  })
})
