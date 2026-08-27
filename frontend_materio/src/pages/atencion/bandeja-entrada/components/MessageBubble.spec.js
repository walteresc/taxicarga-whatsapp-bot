/**
 * MessageBubble component tests
 * Verifies correct rendering for client, bot, advisor messages
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MessageBubble from './MessageBubble.vue'

describe('MessageBubble', () => {
  it('should render customer message with correct styling and BEM classes', () => {
    const wrapper = mount(MessageBubble, {
      props: {
        message: {
          id: 1,
          senderType: 'customer',
          senderName: 'Walter',
          contentType: 'text',
          text: 'Hola, ¿cómo están?',
          timestamp: '2026-08-26T20:00:00+00:00',
          status: 'recibido',
        },
      },
    })

    const container = wrapper.find('[data-sender="customer"]')
    expect(container.exists()).toBe(true)
    expect(container.classes()).toContain('message-container')
    expect(container.classes()).toContain('message-container--customer')

    const bubble = wrapper.find('.message-bubble--customer')
    expect(bubble.exists()).toBe(true)
    expect(bubble.classes()).toContain('message-bubble')

    const text = wrapper.text()
    expect(text).toContain('Hola, ¿cómo están?')
  })

  it('should render bot message with right alignment', () => {
    const wrapper = mount(MessageBubble, {
      props: {
        message: {
          id: 2,
          senderType: 'bot',
          senderName: 'Bot Taxi',
          contentType: 'text',
          text: 'Buenos días, ¿en qué puedo ayudarte?',
          timestamp: '2026-08-26T20:01:00+00:00',
          status: 'sent',
        },
      },
    })

    const container = wrapper.find('[data-sender="bot"]')
    expect(container.classes()).toContain('message-container--bot')

    const bubble = wrapper.find('.message-bubble--bot')
    expect(bubble.exists()).toBe(true)

    const text = wrapper.text()
    expect(text).toContain('Buenos días')
  })

  it('should render advisor message with distinct styling', () => {
    const wrapper = mount(MessageBubble, {
      props: {
        message: {
          id: 3,
          senderType: 'advisor',
          senderName: 'Juan Pérez',
          contentType: 'text',
          text: 'Entiendo tu solicitud',
          timestamp: '2026-08-26T20:02:00+00:00',
          status: 'delivered',
        },
      },
    })

    const container = wrapper.find('[data-sender="advisor"]')
    expect(container.classes()).toContain('message-container--advisor')

    const bubble = wrapper.find('.message-bubble--advisor')
    expect(bubble.exists()).toBe(true)

    const senderName = wrapper.find('.sender-name')
    expect(senderName.exists()).toBe(true)
    expect(senderName.text()).toBe('Juan Pérez')
  })

  it('should display sender name for bot and advisor only', () => {
    // Client message should NOT show sender name
    const clientWrapper = mount(MessageBubble, {
      props: {
        message: {
          id: 1,
          senderType: 'customer',
          senderName: 'Walter',
          type: 'text',
          text: 'Test',
          timestamp: '2026-08-26T20:00:00+00:00',
        },
      },
    })

    expect(clientWrapper.find('.sender-name').exists()).toBe(false)

    // Bot message SHOULD show sender name
    const botWrapper = mount(MessageBubble, {
      props: {
        message: {
          id: 2,
          senderType: 'bot',
          senderName: 'Bot Taxi',
          contentType: 'text',
          text: 'Test',
          timestamp: '2026-08-26T20:01:00+00:00',
        },
      },
    })

    expect(botWrapper.find('.sender-name').exists()).toBe(true)
    expect(botWrapper.find('.sender-name').text()).toBe('Bot Taxi')
  })

  it('should format timestamp and display it', () => {
    const wrapper = mount(MessageBubble, {
      props: {
        message: {
          id: 1,
          senderType: 'customer',
          senderName: 'Walter',
          type: 'text',
          text: 'Hola',
          timestamp: '2026-08-26T20:34:15.730622+00:00',
          status: 'recibido',
        },
      },
    })

    const messageFooter = wrapper.find('.message-footer')
    expect(messageFooter.exists()).toBe(true)

    // Should display some time (format may vary by timezone)
    const text = wrapper.text()
    expect(text).toContain(':') // Should have time format with colon
    expect(text).toMatch(/\d{1,2}:\d{2}/) // HH:MM format
  })

  it('should handle long text with word wrapping', () => {
    const longText = 'Este es un mensaje muy largo que debería hacer wrap en la burbuja porque tiene muchas palabras y no cabe en una sola línea'

    const wrapper = mount(MessageBubble, {
      props: {
        message: {
          id: 1,
          senderType: 'customer',
          senderName: 'Walter',
          contentType: 'text',
          text: longText,
          timestamp: '2026-08-26T20:00:00+00:00',
        },
      },
    })

    const messageText = wrapper.find('.message-text')
    expect(messageText.exists()).toBe(true)
    expect(messageText.text()).toBe(longText)

    // Verify component has BEM modifier class for customer
    const bubble = wrapper.find('.message-bubble')
    expect(bubble.exists()).toBe(true)
    expect(bubble.classes()).toContain('message-bubble--customer')
  })

  it('should include data-testid for Playwright', () => {
    const wrapper = mount(MessageBubble, {
      props: {
        message: {
          id: 145,
          senderType: 'customer',
          senderName: 'Walter',
          contentType: 'text',
          text: 'REAL-0010',
          timestamp: '2026-08-26T22:34:15+00:00',
        },
      },
    })

    expect(wrapper.attributes('data-testid')).toBe('message-row-145')
    expect(wrapper.find('[data-testid="message-bubble-145"]').exists()).toBe(true)
    expect(wrapper.attributes('data-sender')).toBe('customer')
  })

  it('should support all required fields: text, time, status', () => {
    const wrapper = mount(MessageBubble, {
      props: {
        message: {
          id: 1,
          senderType: 'customer',
          senderName: 'Walter',
          type: 'text',
          text: 'Mensaje de prueba',
          timestamp: '2026-08-26T20:00:00+00:00',
          status: 'recibido',
        },
      },
    })

    // Should render all elements
    expect(wrapper.find('.message-bubble').exists()).toBe(true)
    expect(wrapper.find('.message-text').exists()).toBe(true)
    expect(wrapper.find('.message-footer').exists()).toBe(true)

    const containerText = wrapper.text()
    expect(containerText).toContain('Mensaje de prueba')
    expect(containerText).toMatch(/\d{1,2}:\d{2}/) // Should contain time format
  })
})
