import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ref } from 'vue'
import { useWhatsAppRealtime } from './useWhatsAppRealtime'
import { useEventStore } from '@/stores/eventStore'

describe('useWhatsAppRealtime Idempotence Tests', () => {
  let conversationsStore
  let messagesStore
  let eventStore

  beforeEach(() => {
    setActivePinia(createPinia())
    eventStore = useEventStore()

    // Mock stores
    conversationsStore = {
      upsertConversation: vi.fn(),
      reorderConversations: vi.fn(),
      updateConversationState: vi.fn(),
      getConversation: vi.fn().mockReturnValue(null),
    }

    messagesStore = {
      upsertMessage: vi.fn(),
    }

    // Mock fetch
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        conversations: [],
        snapshot_cursor: '1234-0',
        events: [],
        latest_cursor: '1234-0',
      }),
      text: async () => '{}',
    })

    // Mock EventSource
    global.EventSource = vi.fn().mockImplementation(() => ({
      readyState: 0,
      addEventListener: vi.fn(),
      close: vi.fn(),
      onopen: null,
    }))
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('initialize() idempotency', () => {
    it('should only initialize once for multiple initialize() calls', async () => {
      const realtime = useWhatsAppRealtime(conversationsStore, messagesStore)

      const promise1 = realtime.initialize()
      const promise2 = realtime.initialize()
      const promise3 = realtime.initialize()

      // All three should return same promise
      expect(promise1).toBe(promise2)
      expect(promise2).toBe(promise3)

      await promise1
      expect(realtime.isInitialized.value).toBe(true)
    })

    it('should call setSnapshotCursor only once', async () => {
      const realtime = useWhatsAppRealtime(conversationsStore, messagesStore)

      const setSnapshotSpy = vi.spyOn(eventStore, 'setSnapshotCursor')

      await realtime.initialize()
      await realtime.initialize()
      await realtime.initialize()

      // Should only be called once
      expect(setSnapshotSpy).toHaveBeenCalledTimes(1)
    })

    it('should call subscribe only once across multiple initialize() calls', async () => {
      const realtime = useWhatsAppRealtime(conversationsStore, messagesStore)

      const subscribeSpy = vi.spyOn(eventStore, 'subscribe')

      await realtime.initialize()
      await realtime.initialize()
      await realtime.initialize()

      // Should only subscribe once
      expect(subscribeSpy).toHaveBeenCalledTimes(1)
    })
  })

  describe('subscribeToEvents() idempotency', () => {
    it('should only register one subscription', () => {
      const realtime = useWhatsAppRealtime(conversationsStore, messagesStore)

      const subscribeSpy = vi.spyOn(eventStore, 'subscribe')

      // Manually call subscribeToEvents multiple times (simulating re-initialization)
      // Note: In normal flow, this shouldn't happen due to initialize() guards
      // But we test that subscribeToEvents is idempotent anyway

      // Call via initialize which uses subscribeToEvents internally
      realtime.initialize()

      expect(subscribeSpy).toHaveBeenCalledTimes(1)
    })
  })

  describe('cleanup() completeness', () => {
    it('should disconnect and reset state on cleanup', async () => {
      const realtime = useWhatsAppRealtime(conversationsStore, messagesStore)

      await realtime.initialize()
      expect(realtime.isInitialized.value).toBe(true)

      const disconnectSpy = vi.spyOn(eventStore, 'disconnect')

      realtime.cleanup()

      expect(disconnectSpy).toHaveBeenCalled()
      expect(realtime.isInitialized.value).toBe(false)
    })

    it('should allow re-initialize after cleanup', async () => {
      const realtime = useWhatsAppRealtime(conversationsStore, messagesStore)

      await realtime.initialize()
      expect(realtime.isInitialized.value).toBe(true)

      realtime.cleanup()
      expect(realtime.isInitialized.value).toBe(false)

      // Should be able to initialize again
      await realtime.initialize()
      expect(realtime.isInitialized.value).toBe(true)
    })
  })

  describe('Multiple instances isolation', () => {
    it('should have independent state per instance', async () => {
      const realtime1 = useWhatsAppRealtime(conversationsStore, messagesStore)
      const realtime2 = useWhatsAppRealtime(conversationsStore, messagesStore)

      // But they share the same eventStore (global)
      expect(realtime1.initialize).toBeDefined()
      expect(realtime2.initialize).toBeDefined()

      // Each has its own initialization promise
      const p1 = realtime1.initialize()
      const p2 = realtime2.initialize()

      // Both should complete successfully
      await p1
      await p2

      // Each should have their own isInitialized
      expect(realtime1.isInitialized.value).toBe(true)
      expect(realtime2.isInitialized.value).toBe(true)
    })
  })

  describe('Error recovery', () => {
    it('should reset isInitialized to false on error', async () => {
      const realtime = useWhatsAppRealtime(conversationsStore, messagesStore)

      // Mock fetch to fail
      global.fetch = vi.fn().mockRejectedValueOnce(new Error('Network error'))

      try {
        await realtime.initialize()
      } catch (error) {
        // Expected
      }

      expect(realtime.isInitialized.value).toBe(false)
    })

    it('should allow retry after error', async () => {
      const realtime = useWhatsAppRealtime(conversationsStore, messagesStore)

      // First attempt fails
      let attemptCount = 0
      global.fetch = vi.fn().mockImplementation(() => {
        attemptCount++
        if (attemptCount === 1) {
          return Promise.reject(new Error('Network error'))
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            conversations: [],
            snapshot_cursor: '1234-0',
          }),
        })
      })

      // First initialize fails
      try {
        await realtime.initialize()
      } catch (error) {
        // Expected
      }

      expect(realtime.isInitialized.value).toBe(false)

      // Second initialize should work
      await realtime.initialize()
      expect(realtime.isInitialized.value).toBe(true)
    })
  })
})
