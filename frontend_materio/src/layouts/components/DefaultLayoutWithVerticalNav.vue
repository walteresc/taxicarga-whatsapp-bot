<script setup>
import { useRoute } from 'vue-router'
import { computed, onMounted, onUnmounted, watch } from 'vue'
import NavItems from '@/layouts/components/NavItems.vue'
import logo from '@images/logo.svg?raw'
import VerticalNavLayout from '@layouts/components/VerticalNavLayout.vue'

// Components
import NavbarThemeSwitcher from '@/layouts/components/NavbarThemeSwitcher.vue'
import UserProfile from '@/layouts/components/UserProfile.vue'

// FASE 5B: Real-time event streaming
import { useWhatsAppRealtime } from '@/composables/useWhatsAppRealtime'
import { useConversationsStore } from '@/stores/conversationsStore'
import { useMessagesStore } from '@/stores/messagesStore'
import { useAuthGuard } from '@/composables/useAuthGuard'

const route = useRoute()
const { checkAuth } = useAuthGuard()
const isInboxRoute = computed(() => route.path.includes('bandeja-entrada'))

// Initialize real-time streaming
const conversationsStore = useConversationsStore()
const messagesStore = useMessagesStore()
const { initialize, cleanup } = useWhatsAppRealtime(conversationsStore, messagesStore)

// La conexión SSE de tiempo real (WhatsApp) solo tiene consumidores reales
// en Bandeja de entrada (ningún otro módulo lee conversationsStore/
// messagesStore) — antes se abría al montar este layout, es decir en
// CUALQUIER página interna (dashboard, gerencia, catálogo...), y quedaba
// abierta indefinidamente mientras esa pestaña estuviera abierta. Con
// Gunicorn sirviendo un pool finito de hilos, cada pestaña interna abierta
// consumía uno para siempre sin necesidad, y alcanzaba para colgar la app
// para todo el mundo. Ahora se conecta solo al entrar a Bandeja de entrada
// y se desconecta al salir.
const connectRealtime = async () => {
  console.log('[LAYOUT] Entering bandeja-entrada, connecting real-time...')
  try {
    const isAuthenticated = await checkAuth()
    if (!isAuthenticated) {
      console.warn('[LAYOUT] Not authenticated, skipping real-time initialization')

      return
    }
    await initialize()
    console.log('[LAYOUT] initialize() completed successfully')
  } catch (error) {
    console.error('[LAYOUT] Failed to initialize real-time:', error.message, error.stack)
  }
}

onMounted(() => {
  if (isInboxRoute.value) connectRealtime()
})

watch(isInboxRoute, (entering, wasIn) => {
  if (entering && !wasIn) connectRealtime()
  else if (!entering && wasIn) cleanup()
})

onUnmounted(() => {
  cleanup()
})
</script>

<template>
  <VerticalNavLayout :class="{ 'hide-navbar': isInboxRoute }">
    <!-- 👉 navbar (hidden in bandeja-entrada) -->
    <template
      v-if="!isInboxRoute"
      #navbar="{ toggleVerticalOverlayNavActive }"
    >
      <div class="d-flex h-100 align-center">
        <!-- 👉 Vertical nav toggle in overlay mode -->
        <IconBtn
          class="ms-n3 d-lg-none"
          @click="toggleVerticalOverlayNavActive(true)"
        >
          <VIcon icon="ri-menu-line" />
        </IconBtn>

        <!-- 👉 Search -->
        <div
          class="d-flex align-center cursor-pointer"
          style="user-select: none;"
        >
          <!-- 👉 Search Trigger button -->
          <IconBtn>
            <VIcon icon="ri-search-line" />
          </IconBtn>

          <span class="d-none d-md-flex align-center text-disabled">
            <span class="me-3">Search</span>
            <span class="meta-key">&#8984;K</span>
          </span>
        </div>

        <VSpacer />

        <IconBtn
          href="https://github.com/themeselection/materio-vuetify-vuejs-admin-template-free"
          target="_blank"
          rel="noopener noreferrer"
        >
          <VIcon icon="ri-github-fill" />
        </IconBtn>

        <IconBtn>
          <VIcon icon="ri-notification-line" />
        </IconBtn>

        <NavbarThemeSwitcher class="me-2" />

        <UserProfile />
      </div>
    </template>

    <template #vertical-nav-header="{ toggleIsOverlayNavActive }">
      <RouterLink
        to="/"
        class="app-logo app-title-wrapper"
      >
        <!-- eslint-disable vue/no-v-html -->
        <div
          class="d-flex"
          v-html="logo"
        />
        <!-- eslint-enable -->

        <h1 class="font-weight-medium leading-normal text-xl text-uppercase">
          Materio
        </h1>
      </RouterLink>

      <IconBtn
        class="d-block d-lg-none"
        @click="toggleIsOverlayNavActive(false)"
      >
        <VIcon icon="ri-close-line" />
      </IconBtn>
    </template>

    <template #vertical-nav-content>
      <NavItems />
    </template>

    <!-- 👉 Pages -->
    <slot />
  </VerticalNavLayout>
</template>

<style lang="scss" scoped>
.meta-key {
  border: thin solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 6px;
  block-size: 1.5625rem;
  line-height: 1.3125rem;
  padding-block: 0.125rem;
  padding-inline: 0.25rem;
}

.app-logo {
  display: flex;
  align-items: center;
  column-gap: 0.75rem;

  .app-logo-title {
    font-size: 1.25rem;
    font-weight: 500;
    line-height: 1.75rem;
    text-transform: uppercase;
  }
}

:deep(.hide-navbar) {
  .layout-navbar {
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    max-height: 0 !important;
    overflow: hidden !important;
  }

  .layout-page-content {
    padding-block-start: 0 !important;
    margin-block-start: 0 !important;
  }

  .layout-content-wrapper {
    margin-block-start: 0 !important;
    padding-block-start: 0 !important;
  }
}
</style>
