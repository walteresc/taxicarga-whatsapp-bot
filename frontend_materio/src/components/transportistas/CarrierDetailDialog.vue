<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { ApiError } from '@/services/apiClient'
import {
  carrierDriversService, carriersService, carrierVehiclesService,
  fetchVehicleCatalog, LICENSE_CATEGORIES,
} from '@/services/carriersService'

const props = defineProps({
  carrier: { type: Object, default: null },
  carrierId: { type: [Number, String], default: null },
})
const emit = defineEmits(['close', 'changed'])

const info = ref(props.carrier)
const vehicles = ref([])
const drivers = ref([])
const loading = ref(true)
const error = ref('')
const vehicleTypes = ref([])
const bodyTypes = ref([])

const cid = computed(() => props.carrier?.id ?? props.carrierId)

const loadLists = async () => {
  const [v, d] = await Promise.all([
    carrierVehiclesService.list({ carrierId: cid.value, pageSize: 200 }),
    carrierDriversService.list({ carrierId: cid.value, pageSize: 200 }),
  ])
  vehicles.value = v.results
  drivers.value = d.results
}

onMounted(async () => {
  try {
    const [c] = await Promise.all([
      info.value ? Promise.resolve(info.value) : carriersService.get(cid.value),
      loadLists(),
      fetchVehicleCatalog().then(cat => {
        vehicleTypes.value = cat.vehicleTypes
        bodyTypes.value = cat.bodyTypes
      }).catch(() => {}),
    ])
    info.value = c
  } catch (e) {
    error.value = e.message || 'No se pudo cargar el detalle.'
  } finally {
    loading.value = false
  }
})

const dash = v => v || '—'
const snack = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snack, { show: true, text, color })

// ── Alta de vehículo ──────────────────────────────────────────────────
const vehDialog = ref(false)
const vehSaving = ref(false)
const vehErr = ref({})
const vehForm = reactive({
  plate: '', vehicleTypeId: null, bodyTypeId: null,
  brand: '', model: '', year: '', capacityUsefulTons: '', active: true,
})
const typeOptions = computed(() => vehicleTypes.value.map(t => ({ title: t.name, value: t.id })))
const selType = computed(() => vehicleTypes.value.find(t => t.id === vehForm.vehicleTypeId))
const bodyOptions = computed(() => {
  const compat = selType.value?.compatibleBodyTypes || []
  const ids = new Set(compat.map(c => c.id))
  return bodyTypes.value.filter(b => ids.has(b.id)).map(b => ({ title: b.name, value: b.id }))
})
const bodyNA = computed(() => selType.value && !(selType.value.compatibleBodyTypes || []).length)
const numOrNull = v => (v === '' || v == null ? null : Number(v))

const openVehicle = () => {
  Object.assign(vehForm, {
    plate: '', vehicleTypeId: null, bodyTypeId: null,
    brand: '', model: '', year: '', capacityUsefulTons: '', active: true,
  })
  vehErr.value = {}
  vehDialog.value = true
}
const submitVehicle = async () => {
  vehSaving.value = true
  vehErr.value = {}
  try {
    await carrierVehiclesService.create({
      carrierId: cid.value,
      plate: vehForm.plate,
      vehicleTypeId: vehForm.vehicleTypeId,
      bodyTypeId: bodyNA.value ? null : vehForm.bodyTypeId,
      brand: vehForm.brand,
      model: vehForm.model,
      year: numOrNull(vehForm.year),
      capacityUsefulTons: numOrNull(vehForm.capacityUsefulTons),
      active: vehForm.active,
    })
    vehDialog.value = false
    notify('Vehículo registrado.')
    await loadLists()
    emit('changed')
  } catch (e) {
    if (e instanceof ApiError && Object.keys(e.fields).length) vehErr.value = e.fields
    else notify(e.message || 'No se pudo guardar.', 'error')
  } finally {
    vehSaving.value = false
  }
}

// ── Alta de conductor ─────────────────────────────────────────────────
const drvDialog = ref(false)
const drvSaving = ref(false)
const drvErr = ref({})
const drvForm = reactive({
  name: '', documentId: '', phone: '', licenseNumber: '', licenseCategory: null,
  licenseExpiresOn: '', isOwner: false, active: true,
})
const openDriver = () => {
  Object.assign(drvForm, {
    name: '', documentId: '', phone: '', licenseNumber: '', licenseCategory: null,
    licenseExpiresOn: '', isOwner: false, active: true,
  })
  drvErr.value = {}
  drvDialog.value = true
}
const submitDriver = async () => {
  drvSaving.value = true
  drvErr.value = {}
  try {
    await carrierDriversService.create({
      carrierId: cid.value,
      name: drvForm.name,
      documentId: drvForm.documentId,
      phone: drvForm.phone,
      licenseNumber: drvForm.licenseNumber,
      licenseCategory: drvForm.licenseCategory || '',
      licenseExpiresOn: drvForm.licenseExpiresOn || null,
      isOwner: drvForm.isOwner,
      active: drvForm.active,
    })
    drvDialog.value = false
    notify('Conductor registrado.')
    await loadLists()
    emit('changed')
  } catch (e) {
    if (e instanceof ApiError && Object.keys(e.fields).length) drvErr.value = e.fields
    else notify(e.message || 'No se pudo guardar.', 'error')
  } finally {
    drvSaving.value = false
  }
}
</script>

<template>
  <VDialog :model-value="true" max-width="760" scrollable @update:model-value="$emit('close')">
    <VCard>
      <VCardTitle class="d-flex align-center justify-space-between">
        <div>
          <span class="text-h6">{{ info?.name || 'Transportista' }}</span>
          <span v-if="info?.documentId" class="text-body-2 text-medium-emphasis ms-2">{{ info.documentId }}</span>
        </div>
        <VBtn icon="ri-close-line" variant="text" size="small" @click="$emit('close')" />
      </VCardTitle>

      <VDivider />
      <VCardText>
        <div v-if="info" class="d-flex flex-wrap ga-2 mb-4">
          <VChip size="small" :color="info.active ? 'success' : 'secondary'">
            {{ info.active ? 'Activo' : 'Inactivo' }}
          </VChip>
          <VChip v-if="info.phone" size="small" variant="tonal" prepend-icon="ri-phone-line">{{ info.phone }}</VChip>
          <VChip v-if="info.email" size="small" variant="tonal" prepend-icon="ri-mail-line">{{ info.email }}</VChip>
          <VChip v-if="info.isDriver" size="small" variant="tonal" prepend-icon="ri-steering-line">Titular conduce</VChip>
        </div>
        <p v-if="info?.notes" class="text-body-2 text-medium-emphasis mb-4">{{ info.notes }}</p>

        <VAlert v-if="error" type="error" variant="tonal" density="compact" class="mb-3">{{ error }}</VAlert>
        <div v-if="loading" class="text-center py-6"><VProgressCircular indeterminate color="primary" size="28" /></div>

        <template v-else>
          <div class="d-flex align-center justify-space-between mb-2">
            <span class="text-overline text-medium-emphasis">Vehículos ({{ vehicles.length }})</span>
            <VBtn size="small" variant="tonal" prepend-icon="ri-add-line" @click="openVehicle">Agregar vehículo</VBtn>
          </div>
          <VTable v-if="vehicles.length" density="compact" class="mb-4">
            <thead><tr><th>Placa</th><th>Tipo / carrocería</th><th>Marca modelo</th><th>Cap. útil (t)</th><th>Estado</th></tr></thead>
            <tbody>
              <tr v-for="v in vehicles" :key="v.id">
                <td class="font-weight-medium">{{ v.plate }}</td>
                <td>{{ dash(v.vehicleTypeName) }}<span v-if="v.bodyTypeName"> · {{ v.bodyTypeName }}</span></td>
                <td>{{ dash([v.brand, v.model].filter(Boolean).join(' ')) }}</td>
                <td>{{ dash(v.capacityUsefulTons) }}</td>
                <td><VChip size="x-small" :color="v.active ? 'success' : 'secondary'">{{ v.active ? 'Activo' : 'Inactivo' }}</VChip></td>
              </tr>
            </tbody>
          </VTable>
          <p v-else class="text-body-2 text-medium-emphasis mb-4">Sin vehículos afiliados.</p>

          <div class="d-flex align-center justify-space-between mb-2">
            <span class="text-overline text-medium-emphasis">Conductores ({{ drivers.length }})</span>
            <VBtn size="small" variant="tonal" prepend-icon="ri-add-line" @click="openDriver">Agregar conductor</VBtn>
          </div>
          <VTable v-if="drivers.length" density="compact">
            <thead><tr><th>Nombre</th><th>DNI</th><th>Teléfono</th><th>Licencia</th><th>Titular</th></tr></thead>
            <tbody>
              <tr v-for="d in drivers" :key="d.id">
                <td class="font-weight-medium">{{ d.name }}</td>
                <td>{{ dash(d.documentId) }}</td>
                <td>{{ dash(d.phone) }}</td>
                <td>{{ d.licenseNumber ? `${d.licenseNumber}${d.licenseCategory ? ` · ${d.licenseCategory}` : ''}` : '—' }}</td>
                <td>{{ d.isOwner ? 'Sí' : '—' }}</td>
              </tr>
            </tbody>
          </VTable>
          <p v-else class="text-body-2 text-medium-emphasis">Sin conductores registrados.</p>
        </template>
      </VCardText>
    </VCard>

    <!-- Alta de vehículo -->
    <VDialog v-model="vehDialog" max-width="560" persistent>
      <VCard>
        <VCardTitle>Nuevo vehículo · {{ info?.name }}</VCardTitle>
        <VCardText>
          <VRow>
            <VCol cols="12" sm="6"><VTextField v-model="vehForm.plate" label="Placa" :error-messages="vehErr.plate" /></VCol>
            <VCol cols="12" sm="6">
              <VSelect v-model="vehForm.vehicleTypeId" :items="typeOptions" label="Tipo de vehículo" :error-messages="vehErr.vehicleTypeId" />
            </VCol>
            <VCol cols="12" sm="6">
              <VSelect
                v-model="vehForm.bodyTypeId" :items="bodyOptions" label="Carrocería"
                :disabled="!vehForm.vehicleTypeId || bodyNA" clearable
                :hint="bodyNA ? 'Este tipo no lleva carrocería' : ''" persistent-hint
                :error-messages="vehErr.bodyTypeId"
              />
            </VCol>
            <VCol cols="6" sm="3"><VTextField v-model="vehForm.brand" label="Marca" :error-messages="vehErr.brand" /></VCol>
            <VCol cols="6" sm="3"><VTextField v-model="vehForm.model" label="Modelo" :error-messages="vehErr.model" /></VCol>
            <VCol cols="6" sm="3"><VTextField v-model="vehForm.year" label="Año" type="number" :error-messages="vehErr.year" /></VCol>
            <VCol cols="6" sm="3"><VTextField v-model="vehForm.capacityUsefulTons" label="Cap. útil (t)" type="number" :error-messages="vehErr.capacityUsefulTons" /></VCol>
            <VCol cols="12"><VSwitch v-model="vehForm.active" label="Activo" color="primary" /></VCol>
          </VRow>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" :disabled="vehSaving" @click="vehDialog = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="vehSaving" :disabled="!vehForm.plate || !vehForm.vehicleTypeId" @click="submitVehicle">Guardar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Alta de conductor -->
    <VDialog v-model="drvDialog" max-width="560" persistent>
      <VCard>
        <VCardTitle>Nuevo conductor · {{ info?.name }}</VCardTitle>
        <VCardText>
          <VRow>
            <VCol cols="12"><VTextField v-model="drvForm.name" label="Nombre completo" :error-messages="drvErr.name" /></VCol>
            <VCol cols="12" sm="6"><VTextField v-model="drvForm.documentId" label="DNI" :error-messages="drvErr.documentId" /></VCol>
            <VCol cols="12" sm="6"><VTextField v-model="drvForm.phone" label="Teléfono" :error-messages="drvErr.phone" /></VCol>
            <VCol cols="12" sm="6"><VTextField v-model="drvForm.licenseNumber" label="N° de licencia" :error-messages="drvErr.licenseNumber" /></VCol>
            <VCol cols="12" sm="6">
              <VSelect v-model="drvForm.licenseCategory" :items="LICENSE_CATEGORIES" label="Categoría" clearable :error-messages="drvErr.licenseCategory" />
            </VCol>
            <VCol cols="12" sm="6">
              <AppDateField v-model="drvForm.licenseExpiresOn" label="Vencimiento de licencia" density="comfortable" clearable :error-messages="drvErr.licenseExpiresOn" />
            </VCol>
            <VCol cols="12" sm="6" class="d-flex align-center"><VSwitch v-model="drvForm.isOwner" label="Es el titular" color="primary" hide-details /></VCol>
            <VCol cols="12"><VSwitch v-model="drvForm.active" label="Activo" color="primary" /></VCol>
          </VRow>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" :disabled="drvSaving" @click="drvDialog = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="drvSaving" :disabled="!drvForm.name || !drvForm.documentId" @click="submitDriver">Guardar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snack.show" :color="snack.color" timeout="3000">{{ snack.text }}</VSnackbar>
  </VDialog>
</template>
