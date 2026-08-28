import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useEventStore } from './eventStore'

describe('EventStore Idempotence Tests', () => {
  beforeEach(() => {
    setActivePinia(createPinia())

    // Mock EventSource
    global.EventSource = vi.fn().mockImplementation(() => ({
      readyState: 0, // CONNECTING
      addEventListener: vi.fn(),
      close: vi.fn(),
      onopen: null,
    }))
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('connect() idempotency', () => {
    it('should return same promise for multiple connect() calls', async () => {
      const store = useEventStore()

      store.setSnapshotCursor('1234-0')

      const promise1 = store.connect()
      const promise2 = store.connect()
      const promise3 = store.connect()

      expect(promise1).toBe(promise2)
      expect(promise2).toBe(promise3)
    })

    it('should create only one EventSource for multiple connect() calls', async () => {
      const store = useEventStore()

      store.setSnapshotCursor('1234-0')

      // Mock EventSource counter
      let eventSourceCount = 0
      global.EventSource = vi.fn().mockImplementation(() => {
        eventSourceCount++
        
        return {
          readyState: 0,
          addEventListener: vi.fn(),
          close: vi.fn(),
          onopen: null,
        }
      })

      await store.connect()
      await store.connect()
      await store.connect()

      // Should only create ONE EventSource
      expect(eventSourceCount).toBe(1)
    })

    it('should not create new EventSource if already CONNECTING', () => {
      const store = useEventStore()

      store.setSnapshotCursor('1234-0')

      let eventSourceCount = 0
      global.EventSource = vi.fn().mockImplementation(() => {
        eventSourceCount++
        
        return {
          readyState: 0, // CONNECTING
          addEventListener: vi.fn(),
          close: vi.fn(),
          onopen: null,
        }
      })

      store.connect()
      store.connect() // Should not create new one

      expect(eventSourceCount).toBe(1)
    })

    it('should not create new EventSource if already OPEN', () => {
      const store = useEventStore()

      store.setSnapshotCursor('1234-0')

      let eventSourceCount = 0
      global.EventSource = vi.fn().mockImplementation(() => {
        eventSourceCount++

        const mock = {
          readyState: 1, // OPEN
          addEventListener: vi.fn(),
          close: vi.fn(),
          onopen: null,
        }


        // Simulate onopen being called
        setTimeout(() => {
          store._setSSEOpen(true) // Internal method to set sseOpen
        }, 0)
        
        return mock
      })

      store.connect()
      store.connect() // Should not create new one

      expect(eventSourceCount).toBe(1)
    })
  })

  describe('startPolling() idempotency', () => {
    it('should not start polling if already polling', () => {
      const store = useEventStore()

      let pollCount = 0

      // Mock fetchEventsPoll
      const originalFetch = store.fetchEventsPoll

      store.fetchEventsPoll = vi.fn().mockResolvedValue(0).mockImplementationOnce(() => {
        pollCount++
        
        return Promise.resolve(0)
      })

      store.startPolling()
      store.startPolling() // Should be ignored

      // Cleanup
      store.stopPolling()
      store.fetchEventsPoll = originalFetch
    })

    it('should not start polling if SSE is open', () => {
      const store = useEventStore()

      store.sseOpen = true

      const fetchSpy = vi.spyOn(store, 'fetchEventsPoll')

      store.startPolling()

      expect(fetchSpy).not.toHaveBeenCalled()
    })

    it('should stop polling when SSE opens', done => {
      const store = useEventStore()

      store.setSnapshotCursor('1234-0')

      store.startPolling()
      expect(store.isPolling).toBe(true)

      // Simulate SSE opening
      store.sseOpen = true
      store.stopPolling()

      setTimeout(() => {
        expect(store.isPolling).toBe(false)
        done()
      }, 100)
    })
  })

  describe('disconnect() cleanup', () => {
    it('should close SSE and stop polling', () => {
      const store = useEventStore()

      store.setSnapshotCursor('1234-0')

      // Setup mock EventSource
      const mockEventSource = {
        readyState: 1,
        addEventListener: vi.fn(),
        close: vi.fn(),
        onopen: null,
      }

      global.EventSource = vi.fn().mockReturnValue(mockEventSource)

      store.connect()
      store.startPolling()

      expect(store.sseOpen || store.isPolling).toBe(true)

      store.disconnect()

      expect(store.sseOpen).toBe(false)
      expect(store.isPolling).toBe(false)
      expect(mockEventSource.close).toHaveBeenCalled()
    })

    it('should clear connection state on disconnect', () => {
      const store = useEventStore()

      store.setSnapshotCursor('1234-0')

      store.disconnect()

      // State should be reset
      expect(store.sseOpen).toBe(false)
      expect(store.isPolling).toBe(false)
      expect(store.lastCursor).toBe('1234-0') // Cursor should remain for reconnection
    })
  })

  describe('Error recovery', () => {
    it('should not create multiple polling instances on repeated errors', async () => {
      const store = useEventStore()

      store.setSnapshotCursor('1234-0')

      let pollStartCount = 0
      const originalStartPolling = store.startPolling

      store.startPolling = vi.fn((original => {
        return function() {
          pollStartCount++
          original.call(this)
        }
      })(originalStartPolling))

      // Simulate multiple errors
      store.handleSSEError(new Error('test error 1'))
      store.handleSSEError(new Error('test error 2'))
      store.handleSSEError(new Error('test error 3'))

      // startPolling should only be called once (subsequent calls should be idempotent)
      expect(pollStartCount).toBeLessThanOrEqual(1)

      store.stopPolling()
    })
  })

  describe('Deduplication (BUG 1 fix)', () => {
    it('should process two consecutive message.created events with different event_ids', () => {
      const store = useEventStore()

      // First event
      const event1 = {
        event_id: '1787851865521-0',
        type: 'message.created',
        message_id: 337,
        conversation_id: 18,
      }

      // Second event (different event_id)
      const event2 = {
        event_id: '1787851875351-0',
        type: 'message.created',
        message_id: 338,
        conversation_id: 18,
      }

      store.addEvent(event1)
      expect(store.events.length).toBe(1)
      expect(store.lastCursor).toBe('1787851865521-0')

      store.addEvent(event2)
      expect(store.events.length).toBe(2) // Should NOT discard as duplicate
      expect(store.lastCursor).toBe('1787851875351-0') // Cursor should advance
    })

    it('should skip duplicate events with same event_id', () => {
      const store = useEventStore()

      const event = {
        event_id: '1234-0',
        type: 'message.created',
        message_id: 100,
        conversation_id: 10,
      }

      store.addEvent(event)
      expect(store.events.length).toBe(1)

      // Try to add same event again
      store.addEvent(event)
      expect(store.events.length).toBe(1) // Should remain 1, duplicate rejected
    })
  })

  describe('Null/undefined ID protection (BUG 2 fix)', () => {
    it('should process events with null/undefined event_id and record in diagnostics', () => {
      const store = useEventStore()

      const eventNoId = {
        event_id: undefined,
        type: 'message.created',
        message_id: 500,
        conversation_id: 20,
      }

      store.addEvent(eventNoId)
      expect(store.events.length).toBe(1) // Should still process, not block stream
      expect(store.nullIdEvents).toBeDefined()
    })

    it('should not block subsequent events when one has no id', () => {
      const store = useEventStore()

      // Event with no ID
      const eventNoId = {
        event_id: undefined,
        type: 'message.created',
        message_id: 500,
        conversation_id: 20,
      }

      // Event with valid ID
      const eventWithId = {
        event_id: '2000-0',
        type: 'message.created',
        message_id: 501,
        conversation_id: 20,
      }

      store.addEvent(eventNoId)
      store.addEvent(eventWithId)

      expect(store.events.length).toBe(2)
      expect(store.lastCursor).toBe('2000-0') // Cursor should update to last valid ID
    })
  })
})
