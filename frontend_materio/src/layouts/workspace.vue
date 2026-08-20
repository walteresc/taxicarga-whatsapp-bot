<script setup>
import { useRoute } from 'vue-router'
import NavItems from '@/layouts/components/NavItems.vue'
import logo from '@images/logo.svg?raw'
import VerticalNavLayout from '@layouts/components/VerticalNavLayout.vue'
import NavbarThemeSwitcher from '@/layouts/components/NavbarThemeSwitcher.vue'
import UserProfile from '@/layouts/components/UserProfile.vue'

const route = useRoute()
</script>

<template>
  <VerticalNavLayout class="workspace-layout-wrapper">
    <!-- 👉 navbar -->
    <template #navbar="{ toggleVerticalOverlayNavActive }">
      <div class="d-flex h-100 align-center">
        <IconBtn class="ms-n3 d-lg-none" @click="toggleVerticalOverlayNavActive(true)">
          <VIcon icon="ri-menu-line" />
        </IconBtn>

        <div class="d-flex align-center cursor-pointer" style="user-select: none;">
          <IconBtn>
            <VIcon icon="ri-search-line" />
          </IconBtn>
          <span class="d-none d-md-flex align-center text-disabled">
            <span class="me-3">Search</span>
            <span class="meta-key">&#8984;K</span>
          </span>
        </div>

        <VSpacer />

        <IconBtn href="https://github.com/themeselection/materio-vuetify-vuejs-admin-template-free" target="_blank" rel="noopener noreferrer">
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
      <RouterLink to="/" class="app-logo app-title-wrapper">
        <div class="d-flex" v-html="logo" />
        <h1 class="font-weight-medium leading-normal text-xl text-uppercase">Materio</h1>
      </RouterLink>
      <IconBtn class="d-block d-lg-none" @click="toggleIsOverlayNavActive(false)">
        <VIcon icon="ri-close-line" />
      </IconBtn>
    </template>

    <template #vertical-nav-content>
      <NavItems />
    </template>

    <!-- 👉 Pages - FULLHEIGHT WORKSPACE -->
    <div class="workspace-content">
      <slot />
    </div>

    <!-- NO FOOTER in workspace layout -->
  </VerticalNavLayout>
</template>

<style lang="scss">
// Global styles for workspace layout
:deep(.workspace-layout-wrapper) {
  display: flex !important;
  flex-direction: column !important;
  height: 100dvh !important;

  .layout-page-content {
    display: flex !important;
    flex-direction: column !important;
    flex: 1 !important;
    min-height: 0 !important;
    overflow: hidden !important;
  }

  .v-main {
    height: 100% !important;
    overflow: hidden !important;
    padding: 0 !important;
    flex: 1 !important;
  }

  .v-main__wrap {
    height: 100% !important;
    overflow: hidden !important;
    padding: 0 !important;
    display: flex !important;
    flex-direction: column !important;
  }

  .v-container {
    height: 100% !important;
    width: 100% !important;
    padding: 0 !important;
    display: flex !important;
    flex-direction: column !important;
    overflow: hidden !important;
  }
}

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
</style>

<style scoped>
.workspace-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
</style>
