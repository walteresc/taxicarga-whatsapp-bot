/**
 * Full integration test: ConversationPanel + MessageTimeline rendering
 * Tests the COMPLETE PIPELINE: store → computed → template → DOM
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import ConversationPanel from './ConversationPanel.vue'
import { useMessagesStore } from '@/stores/messagesStore'

const REAL_DATA = [
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
    id: 2,
    sender: 'customer',
    senderName: 'Walter',
    source: 'whatsapp_customer',
    badge: null,
    type: 'text',
    text: 'FASE5B-SSE-WALTER-REAL-008',
    timestamp: '2026-08-26T20:45:51.507481+00:00',
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
    timestamp: '2026-08-26T20:50:14.895715+00:00',
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
    timestamp: '2026-08-26T21:13:06.360960+00:00',
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
    timestamp: '2026-08-26T22:31:21.721902+00:00',
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
]

describe('ConversationPanel full rendering with real data', () => {
  let pinia

  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)

    // Mock fetch
    global.fetch = vi.fn(async url => {
      if (url.includes('/mensajes/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            messages: REAL_DATA,
            total: REAL_DATA.length,
            conversation_id: 1,
          }),
        }
      }
      return {
        ok: false,
        status: 404,
        json: async () => ({ error: 'Not found' }),
      }
    })
  })

  it('FULL PIPELINE: store loads → computed returns 6 → template renders 6 bubbles', async () => {
    const vuetify = createVuetify()
    const store = useMessagesStore()

    console.log('[FULL] === STEP 1: MOUNT COMPONENT ===')

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
            template: `
              <div class="message-timeline-test">
                <div v-if="loading" class="loading-state">Loading...</div>
                <div v-else-if="messages.length === 0" class="empty-state">No messages</div>
                <div v-else>
                  <div v-for="msg in messages" :key="msg.id" class="message-bubble" :data-id="msg.id">
                    {{ msg.text }}
                  </div>
                </div>
              </div>
            `,
            props: ['messages', 'loading'],
          },
          ChatComposer: true,
        },
      },
    })

    console.log('[FULL] ✓ Component mounted')

    console.log('[FULL] === STEP 2: WAIT FOR LOAD ===')
    await new Promise(resolve => setTimeout(resolve, 500))
    await wrapper.vm.$nextTick()

    console.log('[FULL] ✓ Load complete')

    console.log('[FULL] === STEP 3: VERIFY COMPUTED ===')
    const computed = wrapper.vm.messages
    console.log('[FULL] Computed messages count:', computed.length)
    expect(computed).toHaveLength(6)
    console.log('[FULL] ✓ Computed has 6 messages')

    console.log('[FULL] === STEP 4: VERIFY PROPS PASSED TO TIMELINE ===')
    const messageTimelineComponent = wrapper.findComponent({ name: 'MessageTimeline' })
    const timelineProps = messageTimelineComponent.props()
    console.log('[FULL] Timeline received messages prop count:', timelineProps.messages.length)
    expect(timelineProps.messages).toHaveLength(6)
    console.log('[FULL] ✓ Timeline received 6 messages')

    console.log('[FULL] === STEP 5: VERIFY DOM BUBBLES ===')
    const bubbles = wrapper.findAll('.message-bubble')
    console.log('[FULL] DOM bubbles count:', bubbles.length)
    expect(bubbles).toHaveLength(6)
    console.log('[FULL] ✓ DOM has 6 bubbles')

    console.log('[FULL] === STEP 6: VERIFY EACH BUBBLE ===')
    bubbles.forEach((bubble, idx) => {
      const text = bubble.text()
      const dataId = bubble.attributes('data-id')
      console.log(`[FULL] Bubble ${idx}: data-id=${dataId} text="${text.substring(0, 40)}"`)
      expect(dataId).toBeDefined()
    })
    console.log('[FULL] ✓ All bubbles have data-id')

    console.log('[FULL] === STEP 7: VERIFY REAL-0010 ===')
    const real0010Bubble = wrapper.findAll('.message-bubble').find(b => b.text().includes('REAL-0010'))
    console.log('[FULL] REAL-0010 bubble:', real0010Bubble?.text().substring(0, 40))
    expect(real0010Bubble).toBeDefined()
    expect(real0010Bubble?.text()).toContain('REAL-0010')
    console.log('[FULL] ✓ REAL-0010 visible in DOM')

    console.log('[FULL] === STEP 8: VERIFY STORE STATE ===')
    console.log('[FULL] Store messages[1] count:', store.messages[1]?.length)
    expect(store.messages[1]).toHaveLength(6)
    console.log('[FULL] ✓ Store contains 6 messages')

    console.log('[FULL] === FULL PIPELINE SUCCESS ===')
  })

  it('ConversationPanel template uses correct structure', async () => {
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
          MessageTimeline: false, // Don't stub, render real
          ChatComposer: true,
        },
      },
    })

    await new Promise(resolve => setTimeout(resolve, 500))
    await wrapper.vm.$nextTick()

    // Verify structure
    const chatContent = wrapper.find('.chat-content')
    expect(chatContent.exists()).toBe(true)
    console.log('[STRUCT] ✓ .chat-content exists')

    const timeline = wrapper.find('.message-timeline')
    expect(timeline.exists()).toBe(true)
    console.log('[STRUCT] ✓ .message-timeline exists')

    const composer = wrapper.find('.chat-composer')
    expect(composer.exists()).toBe(true)
    console.log('[STRUCT] ✓ .chat-composer exists')
  })
})
