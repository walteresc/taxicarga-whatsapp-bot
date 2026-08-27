/**
 * FASE 5B: ConversationPanel integration test
 * Reproduces REAL-0010 timeline load and display
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import ConversationPanel from './ConversationPanel.vue'
import { useMessagesStore } from '@/stores/messagesStore'

// Fixture: Real API response
const REAL_API_RESPONSE = {
  messages: [
    {
      id: 1,
      sender: 'customer',
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
      id: 2,
      sender: 'customer',
      senderName: 'Walter',
      source: 'whatsapp_customer',
      badge: null,
      type: 'text',
      text: 'FASE5B-SSE-WALTER-REAL-008',
      timestamp: '2026-08-26T20:45:51+00:00',
      status: 'recibido',
      avatar: null,
    },
    {
      id: 3,
      sender: 'customer',
      senderName: 'Walter',
      source: 'whatsapp_customer',
      badge: null,
      type: 'text',
      text: 'FASE5B-SSE-WALTER-REAL-006',
      timestamp: '2026-08-26T20:50:14+00:00',
      status: 'recibido',
      avatar: null,
    },
    {
      id: 30,
      sender: 'customer',
      senderName: 'Walter',
      source: 'whatsapp_customer',
      badge: null,
      type: 'text',
      text: 'FASE5B-SSE-WALTER-REAL-007',
      timestamp: '2026-08-26T21:13:06+00:00',
      status: 'recibido',
      avatar: null,
    },
    {
      id: 144,
      sender: 'customer',
      senderName: 'Walter',
      source: 'whatsapp_customer',
      badge: null,
      type: 'text',
      text: 'FASE5B-SSE-WALTER-REAL-009',
      timestamp: '2026-08-26T22:31:21+00:00',
      status: 'recibido',
      avatar: null,
    },
    {
      id: 145,
      sender: 'customer',
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
  total: 6,
  conversation_id: 1,
}

describe('ConversationPanel integration', () => {
  let pinia

  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)

    // Mock fetch globally
    global.fetch = vi.fn(async (url) => {
      if (url.includes('/mensajes/')) {
        return {
          ok: true,
          status: 200,
          json: async () => REAL_API_RESPONSE,
        }
      }
      return {
        ok: false,
        status: 404,
        json: async () => ({ error: 'Not found' }),
      }
    })
  })

  it('should load 6 messages from REST and store in Pinia', async () => {
    const store = useMessagesStore()

    // Simulate what ConversationPanel does
    await store.loadConversationMessages(1)

    // Verify store was populated
    const messages = store.getMessages(1)
    expect(messages).toHaveLength(6)
    expect(messages[0].id).toBe(1)
    expect(messages[5].id).toBe(145)
  })

  it('should render MessageTimeline with 6 messages', async () => {
    const vuetify = createVuetify()

    // Mock child components to avoid full rendering
    const wrapper = mount(ConversationPanel, {
      props: {
        conversationId: 1,
        conversation: {
          id: 1,
          cliente: { nombre: 'Walter' },
          responsable: { nombre: 'Asesor' },
        },
      },
      global: {
        plugins: [pinia, vuetify],
        stubs: {
          EmptyConversationState: true,
          ConversationHeader: true,
          MessageTimeline: {
            template: '<div class="message-timeline-stub"><div v-for="msg in messages" :key="msg.id" class="message">{{ msg.text }}</div></div>',
            props: ['messages', 'loading'],
          },
          ChatComposer: true,
        },
      },
    })

    // Wait for onMounted -> loadMessages() to complete
    await new Promise(resolve => setTimeout(resolve, 200))
    await wrapper.vm.$nextTick()

    // Check if messages computed has 6 items
    const messages = wrapper.vm.messages
    console.log('[TEST] Messages computed:', messages.length)

    expect(messages).toHaveLength(6)
  })

  it('REAL-0010 should appear exactly once in timeline', async () => {
    const vuetify = createVuetify()

    const wrapper = mount(ConversationPanel, {
      props: {
        conversationId: 1,
        conversation: {
          id: 1,
          cliente: { nombre: 'Walter' },
          responsable: { nombre: 'Asesor' },
        },
      },
      global: {
        plugins: [pinia, vuetify],
        stubs: {
          EmptyConversationState: true,
          ConversationHeader: true,
          MessageTimeline: {
            template: '<div class="message-timeline-stub"><div v-for="msg in messages" :key="msg.id" class="message">{{ msg.text }}</div></div>',
            props: ['messages', 'loading'],
          },
          ChatComposer: true,
        },
      },
    })

    // Wait for onMounted -> loadMessages() to complete
    await new Promise(resolve => setTimeout(resolve, 200))
    await wrapper.vm.$nextTick()

    const messages = wrapper.vm.messages
    const real0010 = messages.filter(m => m.id === 145)

    expect(real0010).toHaveLength(1)
    expect(real0010[0].text).toBe('FASE5B-SSE-WALTER-REAL-0010')
  })

  it('should call loadConversationMessages when conversationId prop changes', async () => {
    const vuetify = createVuetify()

    const wrapper = mount(ConversationPanel, {
      props: {
        conversationId: null,
        conversation: null,
      },
      global: {
        plugins: [pinia, vuetify],
        stubs: {
          EmptyConversationState: true,
          ConversationHeader: true,
          MessageTimeline: true,
          ChatComposer: true,
        },
      },
    })

    // Change prop to trigger load
    await wrapper.setProps({
      conversationId: 1,
      conversation: { id: 1, cliente: { nombre: 'Walter' }, responsable: { nombre: 'Asesor' } },
    })

    // Wait for async load
    await new Promise(resolve => setTimeout(resolve, 100))
    await wrapper.vm.$nextTick()

    const messages = wrapper.vm.messages
    expect(messages).toHaveLength(6)
  })
})
