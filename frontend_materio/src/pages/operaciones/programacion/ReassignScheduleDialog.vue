<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { fetchPizarra, pizarraEdit, pizarraMove } from '@/services/pizarraService'
import { driversService } from '@/services/personnelService'

const props = defineProps({
  // fila de la programación: { id, date, serviceCode, startTime, endTime, vehicleId, driverId }
  row: { type: Object, required: true },
})
const emit = defineEmits(['close', 'saved'])

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const resources = ref([])
const drivers = ref([])

const form = reactive({
  resourceId: props.row.vehicleId ? `v${props.row.vehicleId}` : null,
  driverId: props.row.driverId || null,
  start: props.row.startTime || '08:00',
  end: props.row.endTime || '',
})

const resourceItems = computed(() => resources.value.map(r => ({
  title: r.sublabel ? `${r.label} — ${r.sublabel}` : r.label,
  value: r.id,
  driverId: r.driverId,
})))
const driverItems = computed(() => drivers.value.map(d => ({ title: d.name, value: d.id })))

const onResource = id => {
  const r = resourceItems.value.find(x => x.value === id)
  if (r?.driverId && !form.driverId) form.driverId = r.driverId
}

onMounted(async () => {
  try {
    const [board, drv] = await Promise.all([
      fetchPizarra(props.row.date),
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
  const curResource = props.row.vehicleId ? `v${props.row.vehicleId}` : null
  try {
    if (form.resourceId !== curResource) {
      await pizarraMove({ assignmentId: props.row.id, resourceId: form.resourceId, start: form.start || undefined })
    } else if (form.start !== props.row.startTime || (form.end || '') !== (props.row.endTime || '')) {
      await pizarraEdit({ assignmentId: props.row.id, start: form.start || undefined, end: form.end || '' })
    }
    if ((form.driverId || null) !== (props.row.driverId || null)) {
      await pizarraEdit({ assignmentId: props.row.id, driverId: form.driverId || null })
    }
    emit('saved')
    emit('close')
  } catch (e) {
    error.value = e.message || 'No se pudo reasignar.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <VDialog :model-value="true" max-width="520" persistent @update:model-value="$emit('close')">
    <VCard>
      <VCardTitle class="d-flex align-center justify-space-between pt-4">
        <span>Reasignar {{ row.serviceCode }}</span>
        <VBtn icon="ri-close-line" variant="text" size="small" @click="$emit('close')" />
      </VCardTitle>
      <VDivider />

      <VCardText>
        <VAlert v-if="error" type="error" variant="tonal" density="compact" class="mb-3">{{ error }}</VAlert>
        <div v-if="loading" class="text-center py-6"><VProgressCircular indeterminate color="primary" /></div>

        <template v-else>
          <VSelect
            v-model="form.resourceId" :items="resourceItems"
            label="Vehículo" prepend-inner-icon="ri-car-line" class="mb-3"
            no-data-text="Sin vehículos disponibles ese día"
            @update:model-value="onResource"
          />
          <VAutocomplete
            v-model="form.driverId" :items="driverItems"
            label="Conductor" prepend-inner-icon="ri-user-line" clearable class="mb-3"
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
        <VBtn color="primary" :loading="saving" :disabled="loading || !form.resourceId" @click="submit">Guardar</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
