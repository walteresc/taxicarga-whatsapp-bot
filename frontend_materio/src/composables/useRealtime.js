/**
 * Composable for real-time event handling in Vue components
 * Abstracts event store polling and auto-cleanup on unmount
 */

import { onMounted, onUnmounted } from 'vue'
import { useEventStore } from '@/stores/eventStore'

export function useRealtime() {
  const eventStore = useEventStore()

  onMounted(() => {
    if (!eventStore.isPolling) {
      eventStore.startPolling()
    }
  })

  onUnmounted(() => {
    // Optional: Stop polling when last component unmounts
    // For now, keep polling globally to sync across tabs
  })

  return {
    // Access to store
    events: eventStore.events,
    isConnected: eventStore.isConnected,
    eventCount: eventStore.eventCount,

    // Helper methods
    getEventsByType: eventStore.getEventsByType,
    getConversationEvents: eventStore.getConversationEvents,

    // Manual control
    fetchEvents: eventStore.fetchEvents,
    stopPolling: eventStore.stopPolling,
  }
}
