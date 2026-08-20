<script setup>
import { useRoute } from 'vue-router'
import { watch } from 'vue'

const route = useRoute()

// Aplicar clase 'inbox-route' solo en bandeja-entrada
watch(() => route.path, (newPath) => {
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
html:root {
  height: 100%;
}

body {
  height: 100%;
}

#app {
  height: 100%;
}

/* Only for inbox route */
html.inbox-route,
html.inbox-route body {
  overflow: hidden !important;
}

html.inbox-route #app {
  overflow: hidden !important;
}
</style>

<style scoped>
.app-container {
  height: 100dvh;
  overflow: hidden;
}
</style>
