<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { fetchPizarra, pizarraAssign } from '@/services/pizarraService'
import { driversService } from '@/services/personnelService'

const props = defineProps({
  // fila de la reserva: { id, code, route, serviceDate, serviceTime, executionMode }
  booking: { type: Object, required: true },
})
const emit = defineEmits(['close', 'assigned'])

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const resources = ref([])
const drivers = ref([])

const form = reactive({
  resourceId: null,
  driverId: null,
  start: props.booking.serviceTime || '08:00',
  end: '',
})

const resourceItems = computed(() => resources.value.map(r => ({
  title: r.sublabel ? `${r.label} — ${r.sublabel}` : r.label,
  value: r.id,
  driverId: r.driverId,
  driverName: r.driverName,
})))
const driverItems = computed(() => drivers.value.map(d => ({ title: d.name, value: d.id })))

const onResource = id => {
  const r = resourceItems.value.find(x => x.value === id)
  if (r?.driverId && !form.driverId) form.driverId = r.driverId
}

onMounted(async () => {
  if (!props.booking.serviceDate) {
    error.value = 'La reserva no tiene fecha de servicio. Definila primero en el detalle.'
    loading.value = false
    return
  }
  try {
    const [board, drv] = await Promise.all([
      fetchPizarra(props.booking.serviceDate),
      driversService.list({ status: 'active', pageSize: 200 }).catch(() => ({ results: [] })),
    ])
    resources.value = (board.resources || []).filter(r => r.kind === 'propio')
    drivers.value = drv.results || []
  } catch (e) {
    error.value = e.message || 'No se pudo cargar la disponibilidad.'
  } finally {
    loading.value = false
  }
})

const submit = async () => {
  if (!form.resourceId) { error.value = 'Elegí un vehículo.'; return }
  saving.value = true
  error.value = ''
  try {
    await pizarraAssign({
      serviceId: props.booking.id,
      resourceId: form.resourceId,
      start: form.start || undefined,
      end: form.end || undefined,
      driverId: form.driverId || undefined,
    })
    emit('assigned')
    emit('close')
  } catch (e) {
    error.value = e.message || 'No se pudo asignar.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <VDialog :model-value="true" max-width="520" persistent @update:model-value="$emit('close')">
    <VCard>
      <VCardTitle class="d-flex align-center justify-space-between pt-4">
        <span>Asignar {{ booking.code }}</span>
        <VBtn icon="ri-close-line" variant="text" size="small" @click="$emit('close')" />
      </VCardTitle>
      <VDivider />

      <VCardText>
        <div class="text-body-2 text-medium-emphasis mb-3">
          {{ booking.route }} · {{ booking.serviceDate || 'sin fecha' }}
        </div>

        <VAlert v-if="error" type="error" variant="tonal" density="compact" class="mb-3">{{ error }}</VAlert>
        <div v-if="loading" class="text-center py-6"><VProgressCircular indeterminate color="primary" /></div>

        <template v-else>
          <VAlert
            v-if="booking.executionMode === 'tercerizado'"
            type="info" variant="tonal" density="compact" class="mb-3"
          >
            Esta reserva está marcada para transportistas. Al asignar un vehículo propio pasará a nuestro equipo.
          </VAlert>

          <VSelect
            v-model="form.resourceId" :items="resourceItems"
            label="Vehículo" prepend-inner-icon="ri-car-line" class="mb-3"
            :no-data-text="'Sin vehículos disponibles ese día'"
            @update:model-value="onResource"
          />
          <VAutocomplete
            v-model="form.driverId" :items="driverItems"
            label="Conductor (opcional)" prepend-inner-icon="ri-user-line" clearable class="mb-3"
          />
          <div class="d-flex flex-wrap ga-6">
            <AppTimeField v-model="form.start" label="Hora de inicio" density="comfortable" />
            <AppTimeField v-model="form.end" label="Hora de fin (opcional)" density="comfortable" />
          </div>
        </template>
      </VCardText>

      <VCardActions class="px-4 pb-4">
        <VSpacer />
        <VBtn variant="text" :disabled="saving" @click="$emit('close')">Cancelar</VBtn>
        <VBtn color="primary" :loading="saving" :disabled="loading || !form.resourceId" @click="submit">
          Asignar
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
