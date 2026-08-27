import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import BandejaEntrada from './index.vue'
import { conversationService } from '@/services/conversationService'

vi.mock('@/services/conversationService', () => ({
  conversationService: {
    getBotStatus: vi.fn(),
    pauseBot: vi.fn(),
    activateBot: vi.fn(),
    getActiveConversations: vi.fn().mockResolvedValue({ conversations: [] }),
  },
}))

vi.mock('@/composables/useAuthGuard', () => ({
  useAuthGuard: () => ({
    checkAuth: vi.fn().mockResolvedValue(true),
  }),
}))

vi.mock('vuetify', () => ({
  useDisplay: () => ({
    mdAndUp: { value: true },
  }),
}))

describe('BandejaEntrada Bot Status', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should display "Bot global activo" when is_paused=false', async () => {
    conversationService.getBotStatus.mockResolvedValue({
      is_paused: false,
    })

    const wrapper = mount(BandejaEntrada, {
      global: {
        stubs: {
          ConversationListComponent: true,
          ConversationPanelComponent: true,
          ContactDetailsComponent: true,
        },
      },
    })

    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 50))

    const statusText = wrapper.find('.status-text')
    expect(statusText.text()).toContain('Bot global activo')
  })

  it('should display "Bot global pausado" when is_paused=true', async () => {
    conversationService.getBotStatus.mockResolvedValue({
      is_paused: true,
    })

    const wrapper = mount(BandejaEntrada, {
      global: {
        stubs: {
          ConversationListComponent: true,
          ConversationPanelComponent: true,
          ContactDetailsComponent: true,
        },
      },
    })

    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 50))

    const statusText = wrapper.find('.status-text')
    expect(statusText.text()).toContain('Bot global pausado')
  })

  it('should show "Pausar bot" button when bot is active', async () => {
    conversationService.getBotStatus.mockResolvedValue({
      is_paused: false,
    })

    const wrapper = mount(BandejaEntrada, {
      global: {
        stubs: {
          ConversationListComponent: true,
          ConversationPanelComponent: true,
          ContactDetailsComponent: true,
        },
      },
    })

    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 50))

    const buttons = wrapper.findAll('button')
    const pauseButton = buttons.find(b => b.text().includes('Pausar bot'))
    expect(pauseButton).toBeDefined()
  })

  it('should show "Reanudar bot" button when bot is paused', async () => {
    conversationService.getBotStatus.mockResolvedValue({
      is_paused: true,
    })

    const wrapper = mount(BandejaEntrada, {
      global: {
        stubs: {
          ConversationListComponent: true,
          ConversationPanelComponent: true,
          ContactDetailsComponent: true,
        },
      },
    })

    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 50))

    const buttons = wrapper.findAll('button')
    const resumeButton = buttons.find(b => b.text().includes('Reanudar bot'))
    expect(resumeButton).toBeDefined()
  })

  it('should update state when pauseBot is called', async () => {
    conversationService.getBotStatus.mockResolvedValue({
      is_paused: false,
    })
    conversationService.pauseBot.mockResolvedValue({ is_paused: true })

    const wrapper = mount(BandejaEntrada, {
      global: {
        stubs: {
          ConversationListComponent: true,
          ConversationPanelComponent: true,
          ContactDetailsComponent: true,
        },
      },
    })

    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 50))

    // Call pauseBot
    await wrapper.vm.pauseBot()

    // Verify state changed
    expect(wrapper.vm.botGlobalPaused).toBe(true)
    expect(conversationService.pauseBot).toHaveBeenCalled()
  })

  it('should update state when activateBot is called', async () => {
    conversationService.getBotStatus.mockResolvedValue({
      is_paused: true,
    })
    conversationService.activateBot.mockResolvedValue({ is_paused: false })

    const wrapper = mount(BandejaEntrada, {
      global: {
        stubs: {
          ConversationListComponent: true,
          ConversationPanelComponent: true,
          ContactDetailsComponent: true,
        },
      },
    })

    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 50))

    // Call activateBot
    await wrapper.vm.activateBot()

    // Verify state changed
    expect(wrapper.vm.botGlobalPaused).toBe(false)
    expect(conversationService.activateBot).toHaveBeenCalled()
  })

  it('should use correct indicator colors: green when active, amber when paused', async () => {
    conversationService.getBotStatus.mockResolvedValue({
      is_paused: false,
    })

    const wrapper = mount(BandejaEntrada, {
      global: {
        stubs: {
          ConversationListComponent: true,
          ConversationPanelComponent: true,
          ContactDetailsComponent: true,
        },
      },
    })

    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 50))

    const dot = wrapper.find('.dot')
    expect(dot.classes()).toContain('active')

    // Change to paused
    wrapper.vm.botGlobalPaused = true
    await wrapper.vm.$nextTick()

    expect(dot.classes()).toContain('inactive')
  })
})
