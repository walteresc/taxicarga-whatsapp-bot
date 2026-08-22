import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ConversacionesRealtimeUpdate from '../ConversacionesRealtimeUpdate.vue'
import { useEventStore } from '@/stores/eventStore'

describe('ConversacionesRealtimeUpdate', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('mounts and exposes connection status', () => {
    const wrapper = mount(ConversacionesRealtimeUpdate)
    const status = wrapper.vm.connectionStatus

    expect(status).toHaveProperty('isConnected')
    expect(status).toHaveProperty('eventCount')
  })

  it('emits update-conversation on conversation_update event', async () => {
    const wrapper = mount(ConversacionesRealtimeUpdate)
    const eventStore = useEventStore()

    // Simulate event
    eventStore.events.push({
      type: 'conversation_update',
      data: {
        conversation_id: 225,
        preview: 'Updated preview',
        last_activity: '2026-08-22T10:00:00Z',
      },
    })

    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('update-conversation')).toBeTruthy()
  })

  it('shows connection warning when disconnected', async () => {
    const wrapper = mount(ConversacionesRealtimeUpdate)
    const eventStore = useEventStore()

    // Simulate disconnection
    eventStore.pollingError = 'Network error'

    await wrapper.vm.$nextTick()

    const warning = wrapper.find('.connection-warning')
    expect(warning.exists()).toBe(true)
  })

  it('calls callback on conversation update', async () => {
    const callback = vi.fn()
    const wrapper = mount(ConversacionesRealtimeUpdate, {
      props: {
        onConversationUpdate: callback,
      },
    })
    const eventStore = useEventStore()

    // Simulate event
    eventStore.events.push({
      type: 'conversation_update',
      data: {
        conversation_id: 226,
        preview: 'New message',
      },
    })

    await wrapper.vm.$nextTick()

    expect(callback).toHaveBeenCalledWith(226)
  })

  it('handles message_created events', async () => {
    const wrapper = mount(ConversacionesRealtimeUpdate)
    const eventStore = useEventStore()

    eventStore.events.push({
      type: 'message_created',
      data: {
        conversation_id: 225,
        message_id: 1234,
        sender_type: 'customer',
        timestamp: '2026-08-22T10:00:00Z',
      },
    })

    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('update-conversation')).toBeTruthy()
  })
})
