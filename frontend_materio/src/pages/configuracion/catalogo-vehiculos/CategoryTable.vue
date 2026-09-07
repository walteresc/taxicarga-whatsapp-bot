<script setup>
import { computed, reactive, ref } from 'vue'

import { ApiError } from '@/services/apiClient'
import { vehicleCategoriesService, vehicleTypesService } from '@/services/catalogService'

const CATS = [
  { title: 'Livianos', value: 'livianos' },
  { title: 'Medianos', value: 'medianos' },
  { title: 'Pesados', value: 'pesados' },
]
const CAT_COLOR = { livianos: 'success', medianos: 'warning', pesados: 'error' }

const rows = ref([])
const types = ref([])
const loading = ref(true)
const loadError = ref('')

const load = async () => {
  loading.value = true
  loadError.value = ''
  try {
    const [c, t] = await Promise.all([
      vehicleCategoriesService.list({ pageSize: 500, ordering: 'order' }),
      vehicleTypesService.list({ pageSize: 200 }),
    ])
    rows.value = c.results
    types.value = t.results
  } catch (e) {
    loadError.value = e.message || 'No se pudo cargar.'
  } finally {
    loading.value = false
  }
}
load()

const typeOptions = computed(() => types.value.map(t => ({ title: t.name, value: t.id })))

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

const dialog = ref(false)
const editing = ref(null)
const saving = ref(false)
const errors = ref({})
const form = reactive({ vehicleTypeId: null, name: '', category: 'livianos', minTons: '', maxTons: '', order: 0, enabled: true })

const openCreate = () => {
  editing.value = null
  Object.assign(form, { vehicleTypeId: null, name: '', category: 'livianos', minTons: '', maxTons: '', order: (rows.value.at(-1)?.order ?? 0) + 1, enabled: true })
  errors.value = {}
  dialog.value = true
}
const openEdit = row => {
  editing.value = row
  Object.assign(form, {
    vehicleTypeId: row.vehicleTypeId, name: row.name, category: row.category,
    minTons: row.minTons ?? '', maxTons: row.maxTons ?? '', order: row.order, enabled: row.enabled,
  })
  errors.value = {}
  dialog.value = true
}

const submit = async () => {
  saving.value = true
  errors.value = {}
  try {
    const payload = {
      ...form,
      minTons: form.minTons === '' ? null : Number(form.minTons),
      maxTons: form.maxTons === '' ? null : Number(form.maxTons),
    }
    if (editing.value) await vehicleCategoriesService.update(editing.value.id, payload)
    else await vehicleCategoriesService.create(payload)
    dialog.value = false
    notify(editing.value ? 'Cambios guardados.' : 'Fila creada.')
    await load()
  } catch (e) {
    if (e instanceof ApiError && Object.keys(e.fields).length) errors.value = e.fields
    else notify(e.message || 'No se pudo guardar.', 'error')
  } finally {
    saving.value = false
  }
}

const toggle = async row => {
  try { await vehicleCategoriesService.action(row.id, 'toggle-active'); await load() }
  catch (e) { notify(e.message || 'No se pudo cambiar el estado.', 'error') }
}

const confirming = ref(null)
const doDelete = async () => {
  const row = confirming.value
  confirming.value = null
  try { await vehicleCategoriesService.remove(row.id); notify('Fila eliminada.'); await load() }
  catch (e) { notify(e.message || 'No se pudo eliminar.', 'error') }
}
</script>

<template>
  <div>
    <div class="d-flex align-center justify-space-between mb-4">
      <p class="text-body-2 text-medium-emphasis mb-0">
        Tabla de categorías de peso/capacidad por tipo de vehículo. El sistema asigna la categoría
        automáticamente al registrar un vehículo según su capacidad de carga.
      </p>
      <VBtn prepend-icon="ri-add-line" class="ms-4 flex-shrink-0" @click="openCreate">Nueva Fila</VBtn>
    </div>

    <VAlert v-if="loadError" type="error" variant="tonal" class="mb-4">
      {{ loadError }}
      <template #append><VBtn size="small" variant="text" @click="load">Reintentar</VBtn></template>
    </VAlert>

    <VCard>
      <VDivider />
      <VTable>
        <thead>
          <tr>
            <th>Tipo vehículo</th><th>Nombre</th><th>Categoría</th>
            <th class="text-right">Min ton</th><th class="text-right">Max ton</th><th class="text-right">Orden</th>
            <th>Estado</th><th class="text-right">Acciones</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="8" class="text-center py-8"><VProgressCircular indeterminate color="primary" /></td></tr>
          <tr v-else-if="!rows.length"><td colspan="8" class="text-center text-medium-emphasis py-10">Sin filas.</td></tr>
          <tr v-for="row in rows" v-else :key="row.id">
            <td class="text-medium-emphasis">{{ row.vehicleTypeName }}</td>
            <td class="font-weight-medium">{{ row.name }}</td>
            <td><VChip size="small" :color="CAT_COLOR[row.category]" variant="tonal" class="text-capitalize">{{ row.category }}</VChip></td>
            <td class="text-right">{{ row.minTons ?? '—' }}</td>
            <td class="text-right">{{ row.maxTons ?? '—' }}</td>
            <td class="text-right">{{ row.order }}</td>
            <td><VSwitch :model-value="row.enabled" color="success" hide-details density="compact" @update:model-value="toggle(row)" /></td>
            <td class="text-right text-no-wrap">
              <VBtn icon="ri-edit-line" variant="text" size="small" title="Editar" @click="openEdit(row)" />
              <VBtn icon="ri-delete-bin-line" variant="text" size="small" color="error" title="Eliminar" @click="confirming = row" />
            </td>
          </tr>
        </tbody>
      </VTable>
    </VCard>

    <VDialog v-model="dialog" max-width="520" persistent>
      <VCard>
        <VCardTitle>{{ editing ? 'Editar fila' : 'Nueva fila' }}</VCardTitle>
        <VCardText>
          <VRow>
            <VCol cols="12" sm="7">
              <VSelect v-model="form.vehicleTypeId" :items="typeOptions" label="Tipo de vehículo" :error-messages="errors.vehicleTypeId" />
            </VCol>
            <VCol cols="12" sm="5">
              <VTextField v-model.number="form.order" label="Orden" type="number" :error-messages="errors.order" />
            </VCol>
            <VCol cols="12" sm="7">
              <VTextField v-model="form.name" label="Nombre" placeholder="Camión 6 ton" :error-messages="errors.name" />
            </VCol>
            <VCol cols="12" sm="5">
              <VSelect v-model="form.category" :items="CATS" label="Categoría" :error-messages="errors.category" />
            </VCol>
            <VCol cols="6">
              <VTextField v-model="form.minTons" label="Min ton" type="number" :error-messages="errors.minTons" />
            </VCol>
            <VCol cols="6">
              <VTextField v-model="form.maxTons" label="Max ton" type="number" :error-messages="errors.maxTons" />
            </VCol>
            <VCol cols="12">
              <VSwitch v-model="form.enabled" label="Habilitado" color="primary" />
            </VCol>
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
        <VCardTitle>Eliminar fila</VCardTitle>
        <VCardText>Se eliminará <strong>{{ confirming.name }}</strong> ({{ confirming.vehicleTypeName }}).</VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="confirming = null">Cancelar</VBtn>
          <VBtn color="error" @click="doDelete">Eliminar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </div>
</template>
