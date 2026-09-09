<script setup>
import { onMounted, ref } from 'vue'

import { carrierAssignments } from '@/services/portalService'

const OP_STATE = {
  programado: { label: 'Programado', color: 'info' },
  en_ruta: { label: 'En ruta', color: 'primary' },
  en_servicio: { label: 'En servicio', color: 'primary' },
  finalizado: { label: 'Finalizado', color: 'success' },
}
const soles = n => (n == null ? '—' : `S/ ${Math.round(n).toLocaleString('es-PE')}`)

const rows = ref([])
const loading = ref(true)
onMounted(async () => {
  try { rows.value = (await carrierAssignments()).results } finally { loading.value = false }
})
</script>

<template>
  <div>
    <h1 class="text-h5 font-weight-bold mb-1">Mis asignaciones</h1>
    <p class="text-body-2 text-medium-emphasis mb-4">Servicios que te adjudicaron.</p>

    <VProgressLinear v-if="loading" indeterminate />
    <div v-else-if="!rows.length" class="text-center text-medium-emphasis py-10">Sin asignaciones.</div>

    <VRow v-else>
      <VCol v-for="a in rows" :key="a.id" cols="12" md="6">
        <VCard>
          <VCardText>
            <div class="d-flex align-center ga-2 mb-2">
              <span class="text-subtitle-1 font-weight-bold">{{ a.code }}</span>
              <VChip size="x-small" :color="OP_STATE[a.operationalState]?.color">
                {{ OP_STATE[a.operationalState]?.label || a.operationalState }}
              </VChip>
            </div>
            <div class="text-body-2 mb-1">
              <VIcon icon="ri-map-pin-line" size="14" /> {{ a.origin }} → {{ a.destination }}
            </div>
            <div class="text-body-2 mb-1">
              <VIcon icon="ri-calendar-line" size="14" />
              {{ a.date ? new Date(a.date).toLocaleDateString('es-PE') : '—' }}
              <span v-if="a.start"> · {{ a.start }}</span>
              <span v-if="a.vehiclePlate"> · {{ a.vehiclePlate }}</span>
            </div>
            <div class="text-body-2 mb-2 font-weight-medium">Pago acordado: {{ soles(a.amount) }}</div>
            <ul class="text-caption text-medium-emphasis" style="padding-left: 1rem;">
              <li v-for="(line, i) in a.lines" :key="i">{{ line }}</li>
            </ul>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>
