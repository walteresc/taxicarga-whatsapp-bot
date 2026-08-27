/**
 * CORRECCIÓN 1: Effective bot state test
 * Verifies that UI shows single coherent state when bot is paused
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ConversationHeader from './components/ConversationHeader.vue'
import ChatComposer from './components/ChatComposer.vue'
import { createVuetify } from 'vuetify'

describe('Effective bot state (CORRECCIÓN 1)', () => {
  let pinia
  const vuetify = createVuetify()

  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
  })

  describe('ConversationHeader', () => {
    it('global pausado + conversación activa → mostrar "Bot pausado globalmente"', () => {
      const wrapper = mount(ConversationHeader, {
        props: {
          conversation: {
            id: 1,
            name: 'Walter',
            channel: 'WhatsApp',
            attentionMode: 'bot',
          },
          botGlobalPaused: true,
          effectiveBotPaused: true,
        },
        global: { plugins: [vuetify] },
      })

      const text = wrapper.text()
      expect(text).toContain('Bot pausado globalmente')
      expect(text).not.toContain('Bot atendiendo')
      expect(text).not.toContain('pausada en esta conversación')
    })

    it('global activo + conversación pausada → mostrar "Bot pausado en esta conversación"', () => {
      const wrapper = mount(ConversationHeader, {
        props: {
          conversation: {
            id: 1,
            name: 'Walter',
            channel: 'WhatsApp',
            attentionMode: 'bot',
          },
          botGlobalPaused: false,
          effectiveBotPaused: true,
        },
        global: { plugins: [vuetify] },
      })

      const text = wrapper.text()
      expect(text).toContain('pausada en esta conversación')
      expect(text).not.toContain('pausado globalmente')
      expect(text).not.toContain('Bot atendiendo')
    })

    it('ambos activos → mostrar "Bot atendiendo"', () => {
      const wrapper = mount(ConversationHeader, {
        props: {
          conversation: {
            id: 1,
            name: 'Walter',
            channel: 'WhatsApp',
            attentionMode: 'bot',
          },
          botGlobalPaused: false,
          effectiveBotPaused: false,
        },
        global: { plugins: [vuetify] },
      })

      const text = wrapper.text()
      expect(text).toContain('Bot atendiendo')
      expect(text).not.toContain('pausado')
    })

    it('ambos pausados → mostrar "Bot pausado"', () => {
      const wrapper = mount(ConversationHeader, {
        props: {
          conversation: {
            id: 1,
            name: 'Walter',
            channel: 'WhatsApp',
            attentionMode: 'bot',
          },
          botGlobalPaused: true,
          effectiveBotPaused: true,
        },
        global: { plugins: [vuetify] },
      })

      const text = wrapper.text()
      expect(text).toContain('pausado')
      expect(text).not.toContain('Bot atendiendo')
    })

    it('no debe mostrar múltiples estados contradictorios', () => {
      const scenarios = [
        { globalPaused: true, conversationPaused: true },
        { globalPaused: true, conversationPaused: false },
        { globalPaused: false, conversationPaused: true },
        { globalPaused: false, conversationPaused: false },
      ]

      scenarios.forEach(({ globalPaused, conversationPaused }) => {
        const effectivePaused = globalPaused || conversationPaused
        const wrapper = mount(ConversationHeader, {
          props: {
            conversation: {
              id: 1,
              name: 'Walter',
              channel: 'WhatsApp',
              attentionMode: 'bot',
            },
            botGlobalPaused: globalPaused,
            effectiveBotPaused: effectivePaused,
          },
          global: { plugins: [vuetify] },
        })

        const text = wrapper.text()
        const statusCount = (
          (text.match(/Bot atendiendo/g) || []).length +
          (text.match(/pausado/g) || []).length
        )

        expect(statusCount).toBeLessThanOrEqual(2)
      })
    })
  })

  describe('ChatComposer', () => {
    it('bot pausado → mostrar "El bot está pausado" sin "Tomar conversación"', () => {
      const wrapper = mount(ChatComposer, {
        props: {
          attentionMode: 'bot',
          advisorName: 'Walter',
          effectiveBotPaused: true,
        },
        global: { plugins: [vuetify] },
      })

      const text = wrapper.text()
      expect(text).toContain('pausado')
      expect(text).not.toContain('atendiendo')
      expect(wrapper.find('.take-control-btn').exists()).toBe(false)
    })

    it('bot activo → mostrar "El bot está atendiendo" con "Tomar conversación"', () => {
      const wrapper = mount(ChatComposer, {
        props: {
          attentionMode: 'bot',
          advisorName: 'Walter',
          effectiveBotPaused: false,
        },
        global: { plugins: [vuetify] },
      })

      const text = wrapper.text()
      expect(text).toContain('atendiendo')
      expect(text).not.toContain('pausado')
      expect(wrapper.find('.take-control-btn').exists()).toBe(true)
    })

    it('no debe mostrar "Tomar conversación" cuando bot pausado', () => {
      const scenarios = [
        { pause: true, expectButton: false },
        { pause: false, expectButton: true },
      ]

      scenarios.forEach(({ pause, expectButton }) => {
        const wrapper = mount(ChatComposer, {
          props: {
            attentionMode: 'bot',
            advisorName: 'Walter',
            effectiveBotPaused: pause,
          },
          global: { plugins: [vuetify] },
        })

        if (expectButton) {
          expect(wrapper.find('.take-control-btn').exists()).toBe(true)
        } else {
          expect(wrapper.find('.take-control-btn').exists()).toBe(false)
        }
      })
    })
  })
})
