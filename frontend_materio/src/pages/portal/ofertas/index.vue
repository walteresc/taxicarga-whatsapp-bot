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
    <VCard>
      <VTable>
        <thead>
          <tr><th>Carga</th><th>Ruta</th><th>Fecha</th><th class="text-right">Primera</th><th class="text-right">Actual</th><th>Estado</th></tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="6" class="text-center py-8"><VProgressCircular indeterminate /></td></tr>
          <tr v-else-if="!rows.length"><td colspan="6" class="text-center text-medium-emphasis py-10">Todavía no ofertaste nada.</td></tr>
          <tr v-for="o in rows" v-else :key="o.id">
            <td class="font-weight-medium">{{ o.publicationCode }}</td>
            <td>{{ o.origin }} → {{ o.destination }}</td>
            <td>{{ o.date ? new Date(o.date).toLocaleDateString('es-PE') : '—' }}</td>
            <td class="text-right">{{ soles(o.firstAmount) }}</td>
            <td class="text-right font-weight-medium">{{ soles(o.currentAmount) }}</td>
            <td><VChip size="small" :color="STATE[o.state]?.color">{{ STATE[o.state]?.label || o.state }}</VChip></td>
          </tr>
        </tbody>
      </VTable>
    </VCard>
  </div>
</template>
