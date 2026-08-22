/**
 * Event Store for FASE 5B real-time updates
 *
 * Handles event polling with automatic backoff and cursor recovery.
 * No external dependencies (Redis/Channels) - REST polling based.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useEventStore = defineStore('events', () => {
  // State
  const events = ref([])
  const lastCursor = ref(0)
  const isPolling = ref(false)
  const pollInterval = ref(5000) // Start with 5 seconds
  const maxPollInterval = ref(30000) // Max 30 seconds
  const minPollInterval = ref(1000) // Min 1 second
  const pollingError = ref(null)
  const lastPollTime = ref(null)

  // Polling strategy: exponential backoff on errors, reset on success
  const backoffMultiplier = ref(1)
  const maxBackoff = ref(2) // Max 2x multiplier

  /**
   * Calculate next poll interval with exponential backoff
   */
  const calculateNextInterval = (error) => {
    if (error) {
      backoffMultiplier.value = Math.min(
        backoffMultiplier.value * 1.5,
        maxBackoff.value
      )
    } else {
      backoffMultiplier.value = 1 // Reset on success
    }

    const calculated = pollInterval.value * backoffMultiplier.value
    return Math.min(calculated, maxPollInterval.value)
  }

  /**
   * Fetch new events from server
   */
  const fetchEvents = async () => {
    try {
      const params = new URLSearchParams({
        cursor: lastCursor.value,
      })

      const response = await fetch(
        `/dashboard/whatsapp/api/events/stream/?${params}`,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
          },
        }
      )

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data = await response.json()

      // Update cursor
      if (data.latest_cursor) {
        lastCursor.value = data.latest_cursor
      }

      // Add new events
      if (data.events && data.events.length > 0) {
        events.value.push(...data.events)
      }

      // Clear error state on success
      pollingError.value = null
      lastPollTime.value = new Date()

      return data.events?.length || 0
    } catch (error) {
      pollingError.value = error.message
      console.error('Event polling error:', error)
      throw error
    }
  }

  /**
   * Start polling for events
   */
  const startPolling = async () => {
    if (isPolling.value) return

    isPolling.value = true
    let intervalId = null

    const poll = async () => {
      try {
        const newEvents = await fetchEvents()

        // Adjust interval based on activity
        if (newEvents > 0) {
          pollInterval.value = minPollInterval.value // More active when getting events
        } else {
          // Slower polling when idle
          pollInterval.value = Math.min(
            pollInterval.value + 1000,
            maxPollInterval.value
          )
        }

        // Schedule next poll
        if (isPolling.value) {
          intervalId = setTimeout(poll, calculateNextInterval(false))
        }
      } catch (error) {
        const nextInterval = calculateNextInterval(true)

        if (isPolling.value) {
          intervalId = setTimeout(poll, nextInterval)
        }
      }
    }

    // Start polling
    poll()

    return () => {
      // Cleanup function
      if (intervalId) clearTimeout(intervalId)
      isPolling.value = false
    }
  }

  /**
   * Stop polling
   */
  const stopPolling = () => {
    isPolling.value = false
  }

  /**
   * Get events of specific type
   */
  const getEventsByType = (type) => {
    return events.value.filter(e => e.type === type)
  }

  /**
   * Get conversation-related events
   */
  const getConversationEvents = (conversationId) => {
    return events.value.filter(
      e => e.data?.conversation_id === conversationId
    )
  }

  /**
   * Clear all events (for testing)
   */
  const clear = () => {
    events.value = []
    lastCursor.value = 0
    pollingError.value = null
  }

  // Computed
  const eventCount = computed(() => events.value.length)
  const isConnected = computed(() => !pollingError.value)

  return {
    // State
    events,
    lastCursor,
    isPolling,
    pollInterval,
    pollingError,
    lastPollTime,

    // Computed
    eventCount,
    isConnected,

    // Methods
    fetchEvents,
    startPolling,
    stopPolling,
    getEventsByType,
    getConversationEvents,
    clear,
    calculateNextInterval,
  }
})
