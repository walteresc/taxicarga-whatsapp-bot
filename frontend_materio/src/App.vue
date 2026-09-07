<script setup>
import { useRoute } from 'vue-router'
import { watch } from 'vue'
import { useEventStore } from '@/stores/eventStore'

const route = useRoute()

// TRABAJO A: Initialize eventStore early to ensure diagnostics object is created
useEventStore()

// Aplicar clase 'inbox-route' solo en bandeja-entrada
watch(() => route.path, newPath => {
  const isBandeja = newPath.includes('bandeja-entrada')
  if (isBandeja) {
    document.documentElement.classList.add('inbox-route')
  } else {
    document.documentElement.classList.remove('inbox-route')
  }
}, { immediate: true })
</script>

<template>
  <VApp class="app-container">
    <RouterView />
  </VApp>
</template>

<style>
/* Solo la bandeja es una pantalla de altura fija sin scroll de documento.
   El resto de pantallas usan el flujo normal (min-height) para que el
   contenido y la paginación del final sean siempre alcanzables. */
html.inbox-route:root,
html.inbox-route body,
html.inbox-route #app {
  block-size: 100%;
  overflow: hidden !important;
}

/* Hide navbar completely in inbox route */
html.inbox-route .layout-navbar {
  display: none !important;
  height: 0 !important;
  min-height: 0 !important;
  max-height: 0 !important;
  overflow: hidden !important;
}

html.inbox-route .layout-page-content {
  padding-block-start: 0 !important;
  padding-top: 0 !important;
  margin-block-start: 0 !important;
  margin-top: 0 !important;
}

html.inbox-route .layout-content-wrapper {
  margin-block-start: 0 !important;
  margin-top: 0 !important;
  padding-block-start: 0 !important;
  padding-top: 0 !important;
}
</style>

<style scoped>
html.inbox-route .app-container {
  block-size: 100dvh;
  overflow: hidden;
}
</style>
