<script setup>
import { computed, reactive, ref } from 'vue'

import { bodyTypesService, vehicleTypesService } from '@/services/catalogService'

const types = ref([])
const bodyTypes = ref([])
const loading = ref(true)
const loadError = ref('')

const load = async () => {
  loading.value = true
  loadError.value = ''
  try {
    const [t, b] = await Promise.all([
      vehicleTypesService.list({ pageSize: 200 }),
      bodyTypesService.list({ pageSize: 200 }),
    ])
    types.value = t.results
    bodyTypes.value = b.results
  } catch (e) {
    loadError.value = e.message || 'No se pudo cargar.'
  } finally {
    loading.value = false
  }
}
load()

const bodyOptions = computed(() => bodyTypes.value.map(b => ({ title: b.name, value: b.id })))

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

const dialog = ref(false)
const editing = ref(null)
const selected = ref([])
const saving = ref(false)

const openEdit = row => {
  editing.value = row
  selected.value = (row.compatibleBodyTypes || []).map(c => c.id)
  dialog.value = true
}

const submit = async () => {
  saving.value = true
  try {
    await vehicleTypesService.update(editing.value.id, { compatibleBodyTypeIds: selected.value })
    dialog.value = false
    notify('Compatibilidades actualizadas.')
    await load()
  } catch (e) {
    notify(e.message || 'No se pudo guardar.', 'error')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div>
    <p class="text-body-2 text-medium-emphasis mb-4">
      Define qué tipos de carrocería puede tener cada tipo de vehículo. Al registrar un vehículo
      solo se mostrarán las carrocerías compatibles.
    </p>

    <VAlert v-if="loadError" type="error" variant="tonal" class="mb-4">
      {{ loadError }}
      <template #append><VBtn size="small" variant="text" @click="load">Reintentar</VBtn></template>
    </VAlert>

    <VCard>
      <VList v-if="!loading" lines="two" class="py-0">
        <template v-for="(row, i) in types" :key="row.id">
          <VDivider v-if="i" />
          <VListItem>
            <template #prepend>
              <VAvatar rounded="lg" color="primary" variant="tonal" size="40" class="me-3">
                <VIcon :icon="row.icon || 'ri-shape-line'" />
              </VAvatar>
            </template>
            <VListItemTitle class="font-weight-medium">{{ row.name }}</VListItemTitle>
            <VListItemSubtitle class="mt-1">
              <template v-if="row.compatibleBodyTypes?.length">
                <VChip
                  v-for="c in row.compatibleBodyTypes" :key="c.id"
                  size="x-small" color="primary" variant="tonal" class="me-1 mb-1"
                >
                  {{ c.name }}
                </VChip>
              </template>
              <span v-else class="text-caption text-medium-emphasis">Sin carrocería — no aplica o sin restricción</span>
            </VListItemSubtitle>
            <template #append>
              <VBtn variant="tonal" color="primary" size="small" prepend-icon="ri-edit-line" @click="openEdit(row)">Editar</VBtn>
            </template>
          </VListItem>
        </template>
      </VList>
      <div v-else class="text-center py-10"><VProgressCircular indeterminate color="primary" /></div>
    </VCard>

    <VDialog v-model="dialog" max-width="520" persistent>
      <VCard v-if="editing">
        <VCardTitle>Carrocerías de {{ editing.name }}</VCardTitle>
        <VCardText>
          <VSelect
            v-model="selected"
            :items="bodyOptions"
            label="Carrocerías compatibles"
            multiple chips closable-chips
          />
          <p class="text-caption text-medium-emphasis mt-2">
            Sin selección = el vehículo no lleva carrocería (moto, auto…) o no hay restricción.
          </p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" :disabled="saving" @click="dialog = false">Cancelar</VBtn>
          <VBtn :loading="saving" @click="submit">Guardar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </div>
</template>
