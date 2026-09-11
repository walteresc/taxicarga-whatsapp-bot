<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import CrudResourcePage from '@/components/crud/CrudResourcePage.vue'
import CarrierDetailDialog from '@/components/transportistas/CarrierDetailDialog.vue'
import CarrierVehicleFormDialog from '@/components/transportistas/CarrierVehicleFormDialog.vue'
import CarrierDriverFormDialog from '@/components/transportistas/CarrierDriverFormDialog.vue'
import {
  carrierDriversService, carriersService, LICENSE_CATEGORIES,
} from '@/services/carriersService'

const router = useRouter()
const tab = ref('carriers')

// Alta rápida de vehículo / conductor desde la fila del transportista.
const carriersRef = ref(null)
const addVehicleFor = ref(null) // fila del transportista o null
const addDriverFor = ref(null)
const snackbar = ref({ show: false, text: '' })
const afterCarrierChild = msg => {
  carriersRef.value?.load?.()
  snackbar.value = { show: true, text: msg }
}

const carrierColumns = [
  { key: 'name', label: 'Nombre / Razón social' },
  { key: 'documentId', label: 'RUC / DNI', format: r => r.documentId || '—' },
  { key: 'phone', label: 'Teléfono', format: r => r.phone || '—' },
  { key: 'homeCity', label: 'Ubicación', format: r => r.homeCity || '—' },
  { key: 'vehicleCount', label: 'Vehículos', align: 'end', format: r => r.vehicleCount ?? 0 },
]
const carrierFields = [
  { key: 'name', label: 'Nombre o razón social', type: 'text', required: true, cols: 12 },
  { key: 'documentId', label: 'RUC / DNI', type: 'text', cols: 6 },
  { key: 'phone', label: 'Teléfono', type: 'text', cols: 6 },
  { key: 'email', label: 'Email', type: 'text', cols: 12 },
  { key: 'address', label: 'Dirección', type: 'text', cols: 6 },
  {
    key: 'homeCity', label: 'Ubicación frecuente (distrito o ciudad)', type: 'text', cols: 6,
    hint: 'Dónde opera habitualmente. Sirve para asignarle repartos en su zona (más adelante, la app del '
      + 'transportista la va a detectar sola).',
  },
  { key: 'isDriver', label: 'También es conductor de sus vehículos', type: 'switch', cols: 12 },
  { key: 'active', label: 'Activo', type: 'switch', cols: 6 },
  { key: 'notes', label: 'Notas', type: 'textarea', cols: 12 },
]

// --- pestaña Conductores ---
const carrierOptions = ref([])
const driverFields = ref([])
const buildDriverFields = () => {
  driverFields.value = [
    { key: 'carrierId', label: 'Transportista', type: 'select', options: carrierOptions.value, required: true, cols: 12 },
    { key: 'name', label: 'Nombre completo', type: 'text', required: true, cols: 12 },
    { key: 'documentId', label: 'DNI', type: 'text', required: true, cols: 6 },
    { key: 'phone', label: 'Teléfono', type: 'text', cols: 6 },
    { key: 'licenseNumber', label: 'N° de licencia', type: 'text', cols: 6 },
    { key: 'licenseCategory', label: 'Categoría', type: 'select', options: LICENSE_CATEGORIES, cols: 6 },
    { key: 'licenseExpiresOn', label: 'Vencimiento de licencia', type: 'date', cols: 6 },
    { key: 'isOwner', label: 'Es el propio transportista (titular)', type: 'switch', cols: 6 },
    { key: 'active', label: 'Activo', type: 'switch', cols: 6 },
  ]
}
const driverColumns = [
  { key: 'name', label: 'Nombre' },
  { key: 'carrierName', label: 'Transportista' },
  { key: 'documentId', label: 'DNI' },
  { key: 'phone', label: 'Teléfono', format: r => r.phone || '—' },
  {
    key: 'licenseNumber', label: 'Licencia',
    format: r => (r.licenseNumber ? `${r.licenseNumber}${r.licenseCategory ? ` · ${r.licenseCategory}` : ''}` : '—'),
  },
  { key: 'isOwner', label: 'Titular', format: r => (r.isOwner ? 'Sí' : '—') },
]

onMounted(async () => {
  try {
    const data = await carriersService.list({ pageSize: 500, status: 'active' })
    carrierOptions.value = data.results.map(c => ({ title: c.name, value: c.id }))
  } catch { /* el form igual carga */ }
  buildDriverFields()
})
</script>

<template>
  <section>
    <div class="d-flex flex-wrap align-center justify-space-between ga-4 mb-4">
      <div>
        <h1 class="text-h4 font-weight-bold mb-1">Afiliados</h1>
        <p class="text-body-1 text-medium-emphasis mb-0">
          Transportistas externos y sus conductores.
        </p>
      </div>
      <VBtn variant="tonal" prepend-icon="ri-truck-line" @click="router.push('/transportistas/vehiculos')">
        Vehículos AF
      </VBtn>
    </div>

    <VTabs v-model="tab" class="mb-6">
      <VTab value="carriers"><VIcon start icon="ri-team-line" /> Transportistas</VTab>
      <VTab value="drivers"><VIcon start icon="ri-steering-line" /> Conductores</VTab>
    </VTabs>

    <VWindow v-model="tab">
      <VWindowItem value="carriers">
        <CrudResourcePage
          ref="carriersRef"
          hide-header singular="transportista" :service="carriersService"
          :columns="carrierColumns" :fields="carrierFields"
          search-label="Buscar por nombre, documento, teléfono o email" label-field="name"
          :detail-field="['name', 'vehicleCount']"
        >
          <template #row-actions="{ row }">
            <VBtn variant="text" size="small" title="Agregar vehículo" @click="addVehicleFor = row">
              <VIcon icon="ri-truck-line" />
              <VIcon icon="ri-add-line" size="12" style="margin-inline-start: -4px; margin-block-start: -8px;" />
            </VBtn>
            <VBtn
              icon="ri-user-add-line" variant="text" size="small" title="Agregar conductor"
              @click="addDriverFor = row"
            />
          </template>
          <template #detail="{ row, close }">
            <CarrierDetailDialog v-if="row" :carrier="row" @close="close" />
          </template>
        </CrudResourcePage>
      </VWindowItem>
      <VWindowItem value="drivers">
        <CrudResourcePage
          v-if="driverFields.length"
          hide-header singular="conductor" :service="carrierDriversService"
          :columns="driverColumns" :fields="driverFields"
          search-label="Buscar por nombre, DNI, teléfono o transportista" label-field="name"
          detail-field="name"
        >
          <template #detail="{ row, close }">
            <CarrierDetailDialog v-if="row" :carrier-id="row.carrierId" @close="close" />
          </template>
        </CrudResourcePage>
      </VWindowItem>
    </VWindow>

    <CarrierVehicleFormDialog
      v-if="addVehicleFor"
      :carrier-id="addVehicleFor.id" :carrier-name="addVehicleFor.name"
      @close="addVehicleFor = null"
      @saved="afterCarrierChild('Vehículo registrado.')"
    />
    <CarrierDriverFormDialog
      v-if="addDriverFor"
      :carrier-id="addDriverFor.id" :carrier-name="addDriverFor.name"
      @close="addDriverFor = null"
      @saved="afterCarrierChild('Conductor registrado.')"
    />

    <VSnackbar v-model="snackbar.show" color="success" timeout="3000">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
