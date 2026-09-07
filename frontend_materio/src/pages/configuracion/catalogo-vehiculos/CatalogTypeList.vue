<script setup>
import { reactive, ref } from 'vue'

import { ApiError } from '@/services/apiClient'

const props = defineProps({
  service: { type: Object, required: true },
  singular: { type: String, required: true }, // "tipo de vehículo"
  createLabel: { type: String, required: true }, // "Nuevo Tipo"
})

const rows = ref([])
const loading = ref(true)
const loadError = ref('')

const load = async () => {
  loading.value = true
  loadError.value = ''
  try {
    rows.value = (await props.service.list({ pageSize: 200 })).results
  } catch (e) {
    loadError.value = e.message || 'No se pudo cargar.'
  } finally {
    loading.value = false
  }
}
load()

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

// --- alta / edición ---
const dialog = ref(false)
const editing = ref(null)
const saving = ref(false)
const errors = ref({})
const form = reactive({ name: '', code: '', icon: '', enabled: true, order: 0 })

const openCreate = () => {
  editing.value = null
  Object.assign(form, { name: '', code: '', icon: '', enabled: true, order: (rows.value.at(-1)?.order ?? 0) + 1 })
  errors.value = {}
  dialog.value = true
}
const openEdit = row => {
  editing.value = row
  Object.assign(form, { name: row.name, code: row.code, icon: row.icon || '', enabled: row.enabled, order: row.order })
  errors.value = {}
  dialog.value = true
}

const submit = async () => {
  saving.value = true
  errors.value = {}
  try {
    const payload = { ...form }
    if (editing.value) await props.service.update(editing.value.id, payload)
    else await props.service.create(payload)
    dialog.value = false
    notify(editing.value ? 'Cambios guardados.' : `${props.singular} creado.`)
    await load()
  } catch (e) {
    if (e instanceof ApiError && Object.keys(e.fields).length) errors.value = e.fields
    else notify(e.message || 'No se pudo guardar.', 'error')
  } finally {
    saving.value = false
  }
}

const toggle = async row => {
  try {
    await props.service.action(row.id, 'toggle-active')
    await load()
  } catch (e) {
    notify(e.message || 'No se pudo cambiar el estado.', 'error')
  }
}

const confirming = ref(null)
const doDelete = async () => {
  const row = confirming.value
  confirming.value = null
  try {
    await props.service.remove(row.id)
    notify(`${props.singular} eliminado.`)
    await load()
  } catch (e) {
    notify(e.message || 'No se pudo eliminar.', 'error')
  }
}
</script>

<template>
  <div>
    <div class="d-flex align-center justify-space-between mb-4">
      <span class="text-body-2 text-medium-emphasis">{{ rows.length }} {{ rows.length === 1 ? 'registro' : 'registros' }}</span>
      <VBtn prepend-icon="ri-add-line" @click="openCreate">{{ createLabel }}</VBtn>
    </div>

    <VAlert v-if="loadError" type="error" variant="tonal" class="mb-4">
      {{ loadError }}
      <template #append><VBtn size="small" variant="text" @click="load">Reintentar</VBtn></template>
    </VAlert>

    <VCard>
      <VList v-if="!loading && rows.length" lines="two" class="py-0">
        <template v-for="(row, i) in rows" :key="row.id">
          <VDivider v-if="i" />
          <VListItem>
            <template #prepend>
              <VAvatar rounded="lg" color="primary" variant="tonal" size="40" class="me-3">
                <VIcon :icon="row.icon || 'ri-shape-line'" />
              </VAvatar>
            </template>
            <VListItemTitle class="font-weight-medium">{{ row.name }}</VListItemTitle>
            <VListItemSubtitle class="d-flex align-center ga-2 mt-1">
              <VChip size="x-small" label>{{ row.code }}</VChip>
              <span :class="row.enabled ? 'text-success' : 'text-disabled'" class="text-caption">
                {{ row.enabled ? 'Habilitado' : 'Deshabilitado' }}
              </span>
            </VListItemSubtitle>
            <template #append>
              <div class="d-flex align-center">
                <VSwitch :model-value="row.enabled" color="success" hide-details density="compact" @update:model-value="toggle(row)" />
                <VBtn icon="ri-edit-line" variant="text" size="small" title="Editar" @click="openEdit(row)" />
                <VBtn icon="ri-delete-bin-line" variant="text" size="small" color="error" title="Eliminar" @click="confirming = row" />
              </div>
            </template>
          </VListItem>
        </template>
      </VList>
      <div v-else-if="loading" class="text-center py-10"><VProgressCircular indeterminate color="primary" /></div>
      <div v-else class="text-center text-medium-emphasis py-10">Sin registros.</div>
    </VCard>

    <!-- Alta / edición -->
    <VDialog v-model="dialog" max-width="480" persistent>
      <VCard>
        <VCardTitle>{{ editing ? 'Editar' : 'Nuevo' }} {{ singular }}</VCardTitle>
        <VCardText>
          <VRow>
            <VCol cols="12" sm="8">
              <VTextField v-model="form.name" label="Nombre" :error-messages="errors.name" />
            </VCol>
            <VCol cols="12" sm="4">
              <VTextField v-model.number="form.order" label="Orden" type="number" :error-messages="errors.order" />
            </VCol>
            <VCol cols="12" sm="6">
              <VTextField v-model="form.code" label="Código" hint="minúsculas, sin espacios" :error-messages="errors.code" />
            </VCol>
            <VCol cols="12" sm="6">
              <VTextField v-model="form.icon" label="Ícono" placeholder="ri-truck-line" :error-messages="errors.icon">
                <template #append-inner><VIcon :icon="form.icon || 'ri-shape-line'" /></template>
              </VTextField>
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
        <VCardTitle>Eliminar {{ singular }}</VCardTitle>
        <VCardText>Se eliminará <strong>{{ confirming.name }}</strong>.</VCardText>
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
