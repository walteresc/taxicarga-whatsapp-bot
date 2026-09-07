<script setup>
/**
 * Avisos de vencimientos de la flota: SOAT, revisión técnica, extintor y
 * mantenimiento por kilometraje. Se alimenta de GET /api/v2/vehicles/alerts/.
 * Solo aparece si hay algo que avisar.
 */
import { onMounted, ref } from 'vue'

import { fetchVehicleAlerts } from '@/services/flotaService'

const items = ref([])
const loading = ref(true)
const error = ref('')

const STATUS = {
  overdue: { color: 'error', label: 'Vencido' },
  due_soon: { color: 'warning', label: 'Por vencer' },
}

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    items.value = await fetchVehicleAlerts()
  } catch (err) {
    error.value = err.message || 'No se pudieron cargar los avisos.'
  } finally {
    loading.value = false
  }
}

const alertText = a => {
  if (a.type === 'service') {
    return a.remainingKm <= 0
      ? `Mantenimiento vencido (${Math.abs(a.remainingKm).toLocaleString('es-PE')} km pasados)`
      : `Mantenimiento en ${a.remainingKm.toLocaleString('es-PE')} km`
  }
  if (a.daysLeft < 0) return `${a.label} vencido hace ${Math.abs(a.daysLeft)} d`

  return `${a.label} vence en ${a.daysLeft} d (${a.date})`
}

defineExpose({ reload: load })
onMounted(load)
</script>

<template>
  <VCard v-if="loading || error || items.length" class="mb-4" variant="tonal" color="warning">
    <VCardText>
      <div class="d-flex align-center ga-2 mb-2">
        <VIcon icon="ri-alarm-warning-line" />
        <span class="text-subtitle-1 font-weight-bold">Vencimientos próximos</span>
        <VProgressCircular v-if="loading" indeterminate size="18" width="2" class="ms-2" />
      </div>

      <div v-if="error" class="text-body-2">
        {{ error }}
      </div>

      <div v-else-if="!loading && !items.length" class="text-body-2 text-medium-emphasis">
        Sin vencimientos próximos.
      </div>

      <VList v-else density="compact" bg-color="transparent" class="pa-0">
        <VListItem v-for="it in items" :key="it.vehicleId" class="px-0">
          <template #title>
            <span class="font-weight-medium">{{ it.vehicle }}</span>
          </template>
          <template #subtitle>
            <div class="d-flex flex-wrap ga-1 mt-1">
              <VChip
                v-for="(a, i) in it.alerts"
                :key="i"
                size="x-small"
                :color="STATUS[a.status]?.color || 'default'"
              >
                {{ alertText(a) }}
              </VChip>
            </div>
          </template>
        </VListItem>
      </VList>
    </VCardText>
  </VCard>
</template>
