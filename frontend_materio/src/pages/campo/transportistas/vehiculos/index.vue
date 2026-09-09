<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { ApiError } from '@/services/apiClient'
import { carriersService, carrierVehiclesService, fetchVehicleCatalog } from '@/services/carriersService'

const rows = ref([])
const carriers = ref([])
const vehicleTypes = ref([])
const bodyTypes = ref([])
const loading = ref(true)
const loadError = ref('')
const search = ref('')
const onlyActive = ref(false)
const weightFilter = ref(null) // 'livianos' | 'medianos' | 'pesados'
const bodyTypeFilter = ref(null)
const categoryFilter = ref(null) // CategoriaVehiculo id ("Camión 2ton")
const vehicleCategories = ref([])
let searchTimer

const WEIGHT_OPTIONS = [
  { title: 'Livianos', value: 'livianos' },
  { title: 'Medianos', value: 'medianos' },
  { title: 'Pesados', value: 'pesados' },
]
const hasFilters = computed(() =>
  !!search.value || onlyActive.value || weightFilter.value || bodyTypeFilter.value || categoryFilter.value)
const clearFilters = () => {
  search.value = ''
  onlyActive.value = false
  weightFilter.value = null
  bodyTypeFilter.value = null
  categoryFilter.value = null
  load()
}

const load = async () => {
  loading.value = true
  loadError.value = ''
  try {
    rows.value = (await carrierVehiclesService.list({
      search: search.value || undefined,
      status: onlyActive.value ? 'active' : undefined,
      category: weightFilter.value || undefined,
      bodyTypeId: bodyTypeFilter.value || undefined,
      categoryId: categoryFilter.value || undefined,
      pageSize: 200,
    })).results
  } catch (e) {
    loadError.value = e.message || 'No se pudo cargar.'
  } finally {
    loading.value = false
  }
}
const onSearch = () => { clearTimeout(searchTimer); searchTimer = setTimeout(load, 350) }
const bodyTypeOptions = computed(() => bodyTypes.value.map(b => ({ title: b.name, value: b.id })))
const categoryOptions = computed(() => vehicleCategories.value.map(c => ({
  title: c.vehicleTypeName ? `${c.name} (${c.vehicleTypeName})` : c.name,
  value: c.id,
})))

onMounted(async () => {
  try {
    const [cat, c] = await Promise.all([fetchVehicleCatalog(), carriersService.list({ pageSize: 500, status: 'active' })])
    vehicleTypes.value = cat.vehicleTypes
    bodyTypes.value = cat.bodyTypes
    vehicleCategories.value = cat.categories || []
    carriers.value = c.results
  } catch { /* la lista igual carga */ }
  await load()
})

const carrierOptions = computed(() => carriers.value.map(c => ({ title: c.name, value: c.id })))
const typeOptions = computed(() => vehicleTypes.value.map(t => ({ title: t.name, value: t.id })))
const selectedType = computed(() => vehicleTypes.value.find(t => t.id === form.vehicleTypeId))
const bodyOptions = computed(() => {
  const compat = selectedType.value?.compatibleBodyTypes || []
  if (!compat.length) return []
  const ids = new Set(compat.map(c => c.id))
  return bodyTypes.value.filter(b => ids.has(b.id)).map(b => ({ title: b.name, value: b.id }))
})
const bodyNotApplicable = computed(() => selectedType.value && !(selectedType.value.compatibleBodyTypes || []).length)

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

// --- alta / edición ---
const dialog = ref(false)
const editing = ref(null)
const saving = ref(false)
const errors = ref({})
const blank = () => ({
  carrierId: null, plate: '', vehicleTypeId: null, bodyTypeId: null,
  brand: '', model: '', year: '', capacityUsefulTons: '',
  lengthUsefulM: '', widthUsefulM: '', heightUsefulM: '', active: true, notes: '',
})
const form = reactive(blank())

const openCreate = () => {
  editing.value = null
  Object.assign(form, blank())
  errors.value = {}
  dialog.value = true
}
const openEdit = row => {
  editing.value = row
  Object.assign(form, blank(), {
    carrierId: row.carrierId, plate: row.plate, vehicleTypeId: row.vehicleTypeId, bodyTypeId: row.bodyTypeId,
    brand: row.brand || '', model: row.model || '', year: row.year ?? '',
    capacityUsefulTons: row.capacityUsefulTons ?? '', lengthUsefulM: row.lengthUsefulM ?? '',
    widthUsefulM: row.widthUsefulM ?? '', heightUsefulM: row.heightUsefulM ?? '',
    active: row.active, notes: row.notes || '',
  })
  errors.value = {}
  dialog.value = true
}

const numOrNull = v => (v === '' || v === null ? null : Number(v))

const submit = async () => {
  saving.value = true
  errors.value = {}
  try {
    const payload = {
      carrierId: form.carrierId,
      plate: form.plate,
      vehicleTypeId: form.vehicleTypeId,
      bodyTypeId: bodyNotApplicable.value ? null : form.bodyTypeId,
      brand: form.brand,
      model: form.model,
      year: numOrNull(form.year),
      capacityUsefulTons: numOrNull(form.capacityUsefulTons),
      lengthUsefulM: numOrNull(form.lengthUsefulM),
      widthUsefulM: numOrNull(form.widthUsefulM),
      heightUsefulM: numOrNull(form.heightUsefulM),
      active: form.active,
      notes: form.notes,
    }
    if (editing.value) await carrierVehiclesService.update(editing.value.id, payload)
    else await carrierVehiclesService.create(payload)
    dialog.value = false
    notify(editing.value ? 'Vehículo actualizado.' : 'Vehículo registrado.')
    await load()
  } catch (e) {
    if (e instanceof ApiError && Object.keys(e.fields).length) errors.value = e.fields
    else notify(e.message || 'No se pudo guardar.', 'error')
  } finally {
    saving.value = false
  }
}

const toggle = async row => {
  try { await carrierVehiclesService.action(row.id, 'toggle-active'); await load() }
  catch (e) { notify(e.message || 'No se pudo cambiar el estado.', 'error') }
}
const confirming = ref(null)
const doDelete = async () => {
  const row = confirming.value
  confirming.value = null
  try { await carrierVehiclesService.remove(row.id); notify('Vehículo eliminado.'); await load() }
  catch (e) { notify(e.message || 'No se pudo eliminar.', 'error') }
}

const dims = r => [r.lengthUsefulM, r.widthUsefulM, r.heightUsefulM].every(x => x == null)
  ? '—'
  : `${r.lengthUsefulM ?? '?'} × ${r.widthUsefulM ?? '?'} × ${r.heightUsefulM ?? '?'} m`
</script>

<template>
  <section>
    <div class="d-flex flex-wrap align-center justify-space-between ga-4 mb-6">
      <div>
        <h1 class="text-h4 font-weight-bold mb-1">Vehículos de transportistas</h1>
        <p class="text-body-1 text-medium-emphasis mb-0">
          Flota externa. La categoría se asigna sola según la capacidad útil.
        </p>
      </div>
      <VBtn prepend-icon="ri-add-line" @click="openCreate">Nuevo vehículo</VBtn>
    </div>

    <VCard>
      <VCardText class="d-flex flex-wrap align-center ga-3">
        <VTextField
          v-model="search" prepend-inner-icon="ri-search-line"
          label="Buscar por placa, marca, modelo o transportista"
          density="compact" hide-details clearable style="max-width: 300px;"
          @update:model-value="onSearch"
        />
        <VSwitch
          v-model="onlyActive" label="Solo activos" color="primary"
          density="compact" hide-details @update:model-value="load"
        />
        <VSelect
          v-model="weightFilter" :items="WEIGHT_OPTIONS" label="Categoría"
          density="compact" hide-details clearable style="max-width: 160px;"
          @update:model-value="load"
        />
        <VSelect
          v-model="categoryFilter" :items="categoryOptions" label="Clasificación"
          density="compact" hide-details clearable style="max-width: 220px;"
          @update:model-value="load"
        />
        <VSelect
          v-model="bodyTypeFilter" :items="bodyTypeOptions" label="Carrocería"
          density="compact" hide-details clearable style="max-width: 180px;"
          @update:model-value="load"
        />
        <VChip
          v-if="hasFilters" variant="tonal" prepend-icon="ri-close-line"
          @click="clearFilters"
        >
          Todos
        </VChip>
      </VCardText>

      <VAlert v-if="loadError" type="error" variant="tonal" class="ma-4">
        {{ loadError }}
        <template #append><VBtn size="small" variant="text" @click="load">Reintentar</VBtn></template>
      </VAlert>

      <VDivider />

      <VTable class="text-no-wrap">
        <thead>
          <tr>
            <th>Placa</th><th>Transportista</th><th>Tipo</th><th>Carrocería</th>
            <th>Marca / Modelo</th><th class="text-right">Cap. útil</th><th>Clasificación</th>
            <th>L×A×A</th><th>Estado</th><th class="text-right">Acciones</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="10" class="text-center py-8"><VProgressCircular indeterminate color="primary" /></td></tr>
          <tr v-else-if="!rows.length"><td colspan="10" class="text-center text-medium-emphasis py-10">Aún no hay vehículos registrados.</td></tr>
          <tr v-for="row in rows" v-else :key="row.id">
            <td class="font-weight-medium">{{ row.plate }}</td>
            <td>{{ row.carrierName }}</td>
            <td>{{ row.vehicleTypeName }}</td>
            <td>{{ row.bodyTypeName || '—' }}</td>
            <td class="text-medium-emphasis">{{ [row.brand, row.model].filter(Boolean).join(' ') || '—' }}</td>
            <td class="text-right">{{ row.capacityUsefulTons != null ? `${row.capacityUsefulTons} t` : '—' }}</td>
            <td><VChip v-if="row.categoryName" size="x-small" color="primary" variant="tonal">{{ row.categoryName }}</VChip><span v-else>—</span></td>
            <td class="text-medium-emphasis">{{ dims(row) }}</td>
            <td><VSwitch :model-value="row.active" color="success" hide-details density="compact" @update:model-value="toggle(row)" /></td>
            <td class="text-right text-no-wrap">
              <VBtn icon="ri-edit-line" variant="text" size="small" title="Editar" @click="openEdit(row)" />
              <VBtn icon="ri-delete-bin-line" variant="text" size="small" color="error" title="Eliminar" @click="confirming = row" />
            </td>
          </tr>
        </tbody>
      </VTable>
    </VCard>

    <!-- Alta / edición de vehículo -->
    <VDialog v-model="dialog" max-width="640" persistent>
      <VCard>
        <VCardTitle>{{ editing ? 'Editar vehículo' : 'Nuevo vehículo' }}</VCardTitle>
        <VCardText>
          <VRow>
            <VCol cols="12" sm="7">
              <VSelect v-model="form.carrierId" :items="carrierOptions" label="Transportista" :error-messages="errors.carrierId" />
            </VCol>
            <VCol cols="12" sm="5">
              <VTextField v-model="form.plate" label="Placa" :error-messages="errors.plate" />
            </VCol>
            <VCol cols="12" sm="6">
              <VSelect v-model="form.vehicleTypeId" :items="typeOptions" label="Tipo de vehículo" :error-messages="errors.vehicleTypeId" />
            </VCol>
            <VCol cols="12" sm="6">
              <VSelect
                v-model="form.bodyTypeId" :items="bodyOptions" label="Tipo de carrocería"
                :disabled="!form.vehicleTypeId || bodyNotApplicable" clearable
                :hint="bodyNotApplicable ? 'Este tipo de vehículo no lleva carrocería' : ''"
                persistent-hint :error-messages="errors.bodyTypeId"
              />
            </VCol>
            <VCol cols="12" sm="4"><VTextField v-model="form.brand" label="Marca" :error-messages="errors.brand" /></VCol>
            <VCol cols="12" sm="4"><VTextField v-model="form.model" label="Modelo" :error-messages="errors.model" /></VCol>
            <VCol cols="12" sm="4"><VTextField v-model="form.year" label="Año" type="number" :error-messages="errors.year" /></VCol>
            <VCol cols="12" sm="6"><VTextField v-model="form.capacityUsefulTons" label="Capacidad útil (ton)" type="number" :error-messages="errors.capacityUsefulTons" /></VCol>
            <VCol cols="12" sm="6" class="d-flex align-center">
              <VChip v-if="selectedType && form.capacityUsefulTons" color="primary" variant="tonal" size="small">
                <VIcon start icon="ri-price-tag-3-line" size="14" /> categoría automática al guardar
              </VChip>
            </VCol>
            <VCol cols="4"><VTextField v-model="form.lengthUsefulM" label="Largo útil (m)" type="number" :error-messages="errors.lengthUsefulM" /></VCol>
            <VCol cols="4"><VTextField v-model="form.widthUsefulM" label="Ancho útil (m)" type="number" :error-messages="errors.widthUsefulM" /></VCol>
            <VCol cols="4"><VTextField v-model="form.heightUsefulM" label="Alto útil (m)" type="number" :error-messages="errors.heightUsefulM" /></VCol>
            <VCol cols="12"><VSwitch v-model="form.active" label="Activo" color="primary" /></VCol>
            <VCol cols="12"><VTextarea v-model="form.notes" label="Notas" rows="2" auto-grow :error-messages="errors.notes" /></VCol>
          </VRow>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" :disabled="saving" @click="dialog = false">Cancelar</VBtn>
          <VBtn :loading="saving" @click="submit">Guardar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog :model-value="!!confirming" max-width="420" @update:model-value="confirming = null">
      <VCard v-if="confirming">
        <VCardTitle>Eliminar vehículo</VCardTitle>
        <VCardText>Se eliminará <strong>{{ confirming.plate }}</strong> ({{ confirming.carrierName }}).</VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="confirming = null">Cancelar</VBtn>
          <VBtn color="error" @click="doDelete">Eliminar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
