<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { trackShipment } from '@/services/shipmentsService'

const route = useRoute()
const data = ref(null)
const loading = ref(true)
const error = ref('')

const STATE = {
  registrado: 'default', asignado: 'info', recogido: 'info', en_ruta: 'warning',
  en_destino: 'warning', entregado: 'success', fallido: 'error', devuelto: 'default', cancelado: 'default',
}

onMounted(async () => {
  try { data.value = await trackShipment(route.params.token) }
  catch (e) { error.value = e.message || 'No se encontró el envío.' } finally { loading.value = false }
})
</script>

<template>
  <div class="track-wrap">
    <VCard max-width="480" class="mx-auto" elevation="3">
      <VCardText class="pa-6">
        <div class="text-h6 font-weight-bold mb-1">Lima Express</div>
        <div class="text-body-2 text-medium-emphasis mb-4">Seguimiento de envío</div>

        <VProgressLinear v-if="loading" indeterminate />
        <VAlert v-else-if="error" type="error" variant="tonal">{{ error }}</VAlert>

        <template v-else-if="data">
          <div class="d-flex align-center ga-2 mb-1">
            <span class="text-h6">{{ data.code }}</span>
            <VChip size="small" :color="STATE[data.state]">{{ data.stateLabel }}</VChip>
          </div>
          <div class="text-body-2 text-medium-emphasis mb-4">{{ data.route }} · para {{ data.recipient }}</div>

          <VAlert v-if="data.state === 'en_destino' && data.pickupPoint" type="warning" variant="tonal" class="mb-4">
            Tu paquete está en <strong>{{ data.pickupPoint }}</strong>, esperando que lo recojas.
          </VAlert>

          <VAlert v-if="data.deliveredAt" type="success" variant="tonal" class="mb-4">
            Entregado{{ data.deliveredTo ? ` a ${data.deliveredTo}` : '' }} el
            {{ new Date(data.deliveredAt).toLocaleString('es-PE') }}
          </VAlert>

          <VTimeline density="compact" side="end" truncate-line="both">
            <VTimelineItem v-for="(ev, i) in data.events" :key="i" size="x-small" :dot-color="STATE[ev.state]">
              <div class="text-body-2 font-weight-medium">{{ ev.label }}</div>
              <div class="text-caption text-medium-emphasis">
                {{ ev.detail }}<span v-if="ev.detail"> · </span>{{ new Date(ev.at).toLocaleString('es-PE') }}
              </div>
            </VTimelineItem>
          </VTimeline>
        </template>
      </VCardText>
    </VCard>
    <p class="text-center text-caption text-medium-emphasis mt-3">Lima Express</p>
  </div>
</template>

<style scoped>
.track-wrap {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 24px 16px;
  background: rgb(var(--v-theme-background));
}
</style>
