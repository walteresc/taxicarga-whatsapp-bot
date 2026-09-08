<script setup>
import { computed, onMounted, ref } from 'vue'

import { maintenanceService, vehiclesService } from '@/services/flotaService'

const props = defineProps({
  vehicle: { type: Object, default: null },
  vehicleId: { type: [Number, String], default: null },
})
defineEmits(['close'])

const KM_AVISO = 1000

const veh = ref(props.vehicle)
const maints = ref([])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    const id = props.vehicle?.id ?? props.vehicleId
    if (!veh.value && props.vehicleId) veh.value = await vehiclesService.get(props.vehicleId)
    const data = await maintenanceService.list({ vehicleId: id, pageSize: 20, ordering: '-performedOn' })
    maints.value = data.results
  } catch (e) {
    error.value = e.message || 'No se pudo cargar el detalle.'
  } finally {
    loading.value = false
  }
})

const km = n => (n == null ? '—' : `${Number(n).toLocaleString('es-PE')} km`)

const last = computed(() => maints.value[0] || null)
const remaining = computed(() => {
  if (!last.value || last.value.nextServiceOdometer == null || last.value.odometer == null) return null
  return last.value.nextServiceOdometer - last.value.odometer
})
const remainingColor = computed(() => {
  const r = remaining.value
  if (r == null) return 'default'
  if (r <= 0) return 'error'
  if (r <= KM_AVISO) return 'warning'
  return 'success'
})

// Semáforo de vencimientos de documentos.
const docStatus = dateStr => {
  if (!dateStr) return { color: 'grey', label: 'Sin dato' }
  const days = Math.ceil((new Date(`${dateStr}T00:00`) - new Date()) / 86400000)
  if (days < 0) return { color: 'error', label: `Vencido hace ${-days} d` }
  if (days <= 30) return { color: 'warning', label: `Vence en ${days} d` }
  return { color: 'success', label: `${dateStr}` }
}
const docs = computed(() => [
  { label: 'SOAT', date: veh.value?.soatExpiresOn },
  { label: 'Revisión técnica', date: veh.value?.technicalReviewExpiresOn },
  { label: 'Extintor', date: veh.value?.fireExtinguisherExpiresOn },
])
</script>

<template>
  <VDialog :model-value="true" max-width="720" scrollable @update:model-value="$emit('close')">
    <VCard>
      <VCardTitle class="d-flex align-center justify-space-between">
        <div>
          <span class="text-h6">{{ veh?.plate || 'Vehículo' }}</span>
          <span v-if="veh" class="text-body-2 text-medium-emphasis ms-2">
            {{ veh.brand }} {{ veh.model }}<span v-if="veh.year"> · {{ veh.year }}</span>
          </span>
        </div>
        <VBtn icon="ri-close-line" variant="text" size="small" @click="$emit('close')" />
      </VCardTitle>

      <VDivider />
      <VCardText>
        <div v-if="veh" class="d-flex flex-wrap ga-2 mb-4">
          <VChip size="small" :color="veh.active ? 'success' : 'secondary'">
            {{ veh.active ? 'Activo' : 'Inactivo' }}
          </VChip>
          <VChip size="small" variant="tonal">Capacidad {{ veh.capacityTons }} t</VChip>
          <VChip v-if="veh.capacityM3" size="small" variant="tonal">{{ veh.capacityM3 }} m³</VChip>
        </div>

        <div class="text-overline text-medium-emphasis">Documentos</div>
        <div class="d-flex flex-wrap ga-2 mb-4">
          <VChip
            v-for="d in docs" :key="d.label"
            size="small" :color="docStatus(d.date).color" variant="tonal"
          >
            {{ d.label }}: {{ docStatus(d.date).label }}
          </VChip>
        </div>

        <div class="text-overline text-medium-emphasis">Mantenimiento por kilometraje</div>
        <div v-if="last" class="d-flex flex-wrap align-center ga-2 mb-4">
          <span class="text-body-2 text-medium-emphasis">
            Último: {{ last.performedOn }} · odómetro {{ km(last.odometer) }} · próximo a {{ km(last.nextServiceOdometer) }}
          </span>
          <VChip size="small" :color="remainingColor">
            {{ remaining == null ? 'Sin cálculo'
              : (remaining <= 0 ? `Vencido por ${km(-remaining)}` : `Faltan ${km(remaining)}`) }}
          </VChip>
        </div>
        <p v-else class="text-body-2 text-medium-emphasis mb-4">Sin mantenimientos registrados.</p>

        <div class="text-overline text-medium-emphasis mb-1">Historial de mantenimientos</div>
        <VAlert v-if="error" type="error" variant="tonal" density="compact" class="mb-2">{{ error }}</VAlert>
        <div v-if="loading" class="text-center py-6"><VProgressCircular indeterminate color="primary" size="28" /></div>
        <VTable v-else-if="maints.length" density="compact">
          <thead>
            <tr>
              <th>Fecha</th><th>Odómetro</th><th>Próximo</th><th>Faltan</th><th>Trabajo</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in maints" :key="m.id">
              <td>{{ m.performedOn }}</td>
              <td>{{ km(m.odometer) }}</td>
              <td>{{ km(m.nextServiceOdometer) }}</td>
              <td>
                <span :class="(m.nextServiceOdometer - m.odometer) <= 0 ? 'text-error' : ''">
                  {{ km(m.nextServiceOdometer - m.odometer) }}
                </span>
              </td>
              <td class="text-medium-emphasis">{{ m.work }}</td>
            </tr>
          </tbody>
        </VTable>
        <p v-else class="text-body-2 text-medium-emphasis">Sin registros.</p>
      </VCardText>
    </VCard>
  </VDialog>
</template>
