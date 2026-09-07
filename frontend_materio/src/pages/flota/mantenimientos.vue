<script setup>
import { computed, onMounted, ref } from 'vue'

import CrudResourcePage from '@/components/crud/CrudResourcePage.vue'
import { maintenanceService, vehiclesService } from '@/services/flotaService'

const vehicleOptions = ref([])

onMounted(async () => {
  try {
    const data = await vehiclesService.list({ pageSize: 100, ordering: 'plate' })
    vehicleOptions.value = data.results.map(v => ({
      title: `${v.plate} · ${v.brand} ${v.model}`,
      value: v.id,
    }))
  } catch {
    vehicleOptions.value = []
  }
})

const columns = [
  { key: 'vehiclePlate', label: 'Vehículo' },
  { key: 'performedOn', label: 'Fecha' },
  { key: 'odometer', label: 'Kilometraje', format: r => r.odometer?.toLocaleString('es-PE') ?? '—' },
  { key: 'nextServiceOdometer', label: 'Próximo (km)', format: r => r.nextServiceOdometer?.toLocaleString('es-PE') ?? '—' },
  { key: 'work', label: 'Trabajo', format: r => (r.work?.length > 60 ? `${r.work.slice(0, 60)}…` : r.work) },
]

const fields = computed(() => [
  { key: 'vehicleId', label: 'Vehículo', type: 'select', options: vehicleOptions.value, required: true, cols: 12 },
  { key: 'performedOn', label: 'Fecha del mantenimiento', type: 'date', required: true, cols: 6 },
  { key: 'odometer', label: 'Kilometraje actual', type: 'text', required: true, cols: 6 },
  { key: 'nextServiceOdometer', label: 'Próximo mantenimiento (km)', type: 'text', required: true, cols: 6 },
  { key: 'work', label: 'Trabajo realizado', type: 'textarea', required: true, cols: 12 },
  { key: 'notes', label: 'Observaciones', type: 'textarea', cols: 12 },
])
</script>

<template>
  <CrudResourcePage
    title="Mantenimientos"
    subtitle="Histórico de mantenimiento de la flota"
    singular="mantenimiento"
    :service="maintenanceService"
    :columns="columns"
    :fields="fields"
    search-label="Buscar por placa o trabajo"
    label-field="vehiclePlate"
    toggle-field=""
  />
</template>
