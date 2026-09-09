<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { customerLoads } from '@/services/customerPortalService'

const router = useRouter()

const STATUS = {
  draft: { label: 'Borrador', color: 'default' },
  quoted: { label: 'Precio listo', color: 'info' },
  negotiating: { label: 'En negociación', color: 'warning' },
  booked: { label: 'Reservado', color: 'primary' },
  scheduled: { label: 'Programado', color: 'primary' },
  in_progress: { label: 'En curso', color: 'success' },
  completed: { label: 'Finalizado', color: 'success' },
}
const soles = n => (n == null ? null : `S/ ${Math.round(n).toLocaleString('es-PE')}`)

const rows = ref([])
const loading = ref(true)
onMounted(async () => {
  try { rows.value = (await customerLoads()).results } finally { loading.value = false }
})
</script>

<template>
  <div>
    <div class="d-flex align-center mb-4">
      <h1 class="text-h5 font-weight-bold">Mis cargas</h1>
      <VSpacer />
      <VBtn color="primary" prepend-icon="ri-add-line" @click="router.push('/portal/cliente/publicar')">Publicar carga</VBtn>
    </div>

    <VProgressLinear v-if="loading" indeterminate />
    <div v-else-if="!rows.length" class="text-center text-medium-emphasis py-10">
      Todavía no publicaste ninguna carga.
    </div>

    <VRow v-else>
      <VCol v-for="l in rows" :key="l.code" cols="12" md="6">
        <VCard :to="`/portal/cliente/carga/${l.code}`" hover>
          <VCardText>
            <div class="d-flex align-center ga-2 mb-2">
              <span class="text-subtitle-1 font-weight-bold">{{ l.code }}</span>
              <VChip size="x-small" :color="STATUS[l.status]?.color">{{ STATUS[l.status]?.label || l.status }}</VChip>
            </div>
            <div class="text-body-2 mb-1">
              <VIcon icon="ri-map-pin-line" size="14" /> {{ l.origin }} → {{ l.destination }}
            </div>
            <div class="text-body-2 text-medium-emphasis">
              {{ l.date ? new Date(l.date).toLocaleDateString('es-PE') : 'Fecha por confirmar' }}
              <span v-if="l.schedule"> · {{ l.schedule }}</span>
            </div>
            <div v-if="soles(l.price?.amount)" class="text-body-1 font-weight-medium mt-2">
              {{ soles(l.price.amount) }}
              <span v-if="l.price.mode === 'auto'" class="text-caption text-medium-emphasis">(estimado)</span>
            </div>
            <div v-else-if="l.price?.mode === 'advisor'" class="text-body-2 text-medium-emphasis mt-2">
              Un asesor te confirmará el precio.
            </div>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>
