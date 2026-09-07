<script setup>
import { useRouter } from 'vue-router'

import CrudResourcePage from '@/components/crud/CrudResourcePage.vue'
import { carriersService } from '@/services/carriersService'

const router = useRouter()

const columns = [
  { key: 'name', label: 'Nombre / Razón social' },
  { key: 'documentId', label: 'RUC / DNI', format: r => r.documentId || '—' },
  { key: 'phone', label: 'Teléfono', format: r => r.phone || '—' },
  { key: 'vehicleCount', label: 'Vehículos', align: 'end', format: r => r.vehicleCount ?? 0 },
]

const fields = [
  { key: 'name', label: 'Nombre o razón social', type: 'text', required: true, cols: 12 },
  { key: 'documentId', label: 'RUC / DNI', type: 'text', cols: 6 },
  { key: 'phone', label: 'Teléfono', type: 'text', cols: 6 },
  { key: 'email', label: 'Email', type: 'text', cols: 12 },
  { key: 'isDriver', label: 'También es conductor de sus vehículos', type: 'switch', cols: 12 },
  { key: 'active', label: 'Activo', type: 'switch', cols: 6 },
  { key: 'notes', label: 'Notas', type: 'textarea', cols: 12 },
]
</script>

<template>
  <CrudResourcePage
    title="Transportistas afiliados"
    subtitle="Transportistas externos. Cada uno puede tener uno o más vehículos y conductores."
    singular="transportista"
    :service="carriersService"
    :columns="columns"
    :fields="fields"
    search-label="Buscar por nombre, documento, teléfono o email"
    label-field="name"
  >
    <template #before-table>
      <VAlert
        type="info" variant="tonal" density="compact" class="mb-4"
        text="Los vehículos de cada transportista se cargan desde Transportistas → Vehículos."
      >
        <template #append>
          <VBtn size="small" variant="text" @click="router.push('/campo/transportistas/vehiculos')">
            Ir a Vehículos
          </VBtn>
        </template>
      </VAlert>
    </template>
  </CrudResourcePage>
</template>
