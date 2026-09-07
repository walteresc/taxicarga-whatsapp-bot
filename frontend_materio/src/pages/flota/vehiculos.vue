<script setup>
import { ref } from 'vue'

import CrudResourcePage from '@/components/crud/CrudResourcePage.vue'
import ExpiryAlerts from '@/components/flota/ExpiryAlerts.vue'
import { vehiclesService } from '@/services/flotaService'

const alertsRef = ref(null)
const onChanged = () => alertsRef.value?.reload()

const fmtDate = v => v || '—'

const columns = [
  { key: 'plate', label: 'Placa' },
  { key: 'brand', label: 'Marca', format: r => `${r.brand} ${r.model}` },
  { key: 'year', label: 'Año', format: r => r.year || '—' },
  { key: 'capacityTons', label: 'Cap. (t)' },
  { key: 'soatExpiresOn', label: 'SOAT', format: r => fmtDate(r.soatExpiresOn) },
  { key: 'technicalReviewExpiresOn', label: 'Rev. técnica', format: r => fmtDate(r.technicalReviewExpiresOn) },
]

const fields = [
  { key: 'plate', label: 'Placa', type: 'text', required: true, cols: 6 },
  { key: 'year', label: 'Año', type: 'text', cols: 6 },
  { key: 'brand', label: 'Marca', type: 'text', required: true, cols: 6 },
  { key: 'model', label: 'Modelo', type: 'text', required: true, cols: 6 },
  { key: 'capacityTons', label: 'Capacidad (toneladas)', type: 'text', required: true, cols: 6 },
  { key: 'capacityM3', label: 'Capacidad (m³)', type: 'text', cols: 6 },
  { key: 'soatExpiresOn', label: 'Vencimiento SOAT', type: 'date', cols: 6 },
  { key: 'technicalReviewExpiresOn', label: 'Vencimiento revisión técnica', type: 'date', cols: 6 },
  { key: 'fireExtinguisherExpiresOn', label: 'Vencimiento extintor', type: 'date', cols: 6 },
  { key: 'active', label: 'Activo', type: 'switch', cols: 6 },
  { key: 'notes', label: 'Observaciones', type: 'textarea', cols: 12 },
]
</script>

<template>
  <CrudResourcePage
    title="Vehículos"
    subtitle="Flota de camiones"
    singular="vehículo"
    :service="vehiclesService"
    :columns="columns"
    :fields="fields"
    search-label="Buscar por placa, marca o modelo"
    label-field="plate"
    @changed="onChanged"
  >
    <template #before-table>
      <ExpiryAlerts ref="alertsRef" />
    </template>
  </CrudResourcePage>
</template>
