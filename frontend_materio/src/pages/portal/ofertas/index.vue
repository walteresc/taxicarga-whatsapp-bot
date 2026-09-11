<script setup>
import { onMounted, ref } from 'vue'

import { carrierOffers } from '@/services/portalService'

const STATE = {
  pending: { label: 'Enviada', color: 'info' },
  countered_us: { label: 'Contraoferta de Lima Express', color: 'warning' },
  countered_you: { label: 'Contraofertaste', color: 'warning' },
  accepted: { label: 'Adjudicada', color: 'success' },
  rejected: { label: 'No seleccionada', color: 'error' },
  withdrawn: { label: 'Retirada', color: 'default' },
  expired: { label: 'Vencida', color: 'default' },
}
const soles = n => (n == null ? '—' : `S/ ${Math.round(n).toLocaleString('es-PE')}`)

const rows = ref([])
const loading = ref(true)
onMounted(async () => {
  try { rows.value = (await carrierOffers()).results } finally { loading.value = false }
})
</script>

<template>
  <div>
    <h1 class="text-h5 font-weight-bold mb-4">Mis ofertas</h1>

    <VProgressLinear v-if="loading" indeterminate />
    <div v-else-if="!rows.length" class="text-center text-medium-emphasis py-10 text-body-2">
      Todavía no ofertaste nada.
    </div>

    <VRow v-else>
      <VCol v-for="o in rows" :key="o.id" cols="12" md="6">
        <VCard>
          <VCardText>
            <div class="d-flex align-center ga-2 mb-2">
              <span class="text-subtitle-1 font-weight-bold">{{ o.publicationCode }}</span>
              <VChip size="x-small" :color="STATE[o.state]?.color">{{ STATE[o.state]?.label || o.state }}</VChip>
            </div>
            <div class="text-body-2 mb-1">
              <VIcon icon="ri-map-pin-line" size="14" /> {{ o.origin }} → {{ o.destination }}
              <span v-if="o.date"> · {{ new Date(o.date).toLocaleDateString('es-PE') }}</span>
            </div>
            <div class="d-flex align-center ga-4 mt-2">
              <span class="text-body-2 text-medium-emphasis">Primera oferta: {{ soles(o.firstAmount) }}</span>
              <span class="text-body-1 font-weight-bold">{{ soles(o.currentAmount) }}</span>
            </div>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>
