<script setup>
// Compatibilidad de carrocería por CATEGORÍA puntual (tonelaje) — no por
// tipo de vehículo genérico. Un "Camión 2 ton" y un "Camión 15 ton" no
// tienen por qué admitir las mismas carrocerías (antes sí, porque la
// compatibilidad colgaba de TipoVehiculo). Se agrupa visualmente por tipo
// de vehículo para no mostrar una lista plana de 20+ filas.
import { computed, reactive, ref } from 'vue'

import { bodyTypesService, vehicleCategoriesService } from '@/services/catalogService'

const categories = ref([])
const bodyTypes = ref([])
const loading = ref(true)
const loadError = ref('')

const load = async () => {
  loading.value = true
  loadError.value = ''
  try {
    const [c, b] = await Promise.all([
      vehicleCategoriesService.list({ pageSize: 300 }),
      bodyTypesService.list({ pageSize: 200 }),
    ])
    categories.value = c.results
    bodyTypes.value = b.results
  } catch (e) {
    loadError.value = e.message || 'No se pudo cargar.'
  } finally {
    loading.value = false
  }
}
load()

const groups = computed(() => {
  const byType = new Map()
  for (const cat of categories.value) {
    const key = cat.vehicleTypeName || '—'
    if (!byType.has(key)) byType.set(key, [])
    byType.get(key).push(cat)
  }
  return Array.from(byType.entries()).map(([vehicleTypeName, rows]) => ({ vehicleTypeName, rows }))
})

const bodyOptions = computed(() => bodyTypes.value.map(b => ({ title: b.name, value: b.id })))

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

const dialog = ref(false)
const editing = ref(null)
const selected = ref([])
const displayNames = reactive({})   // { [tipoCarroceriaId]: 'Nombre para el cliente' }
const saving = ref(false)

const openEdit = row => {
  editing.value = row
  selected.value = (row.compatibleBodyTypes || []).map(c => c.id)
  Object.keys(displayNames).forEach(k => delete displayNames[k])
  for (const c of row.compatibleBodyTypes || []) displayNames[c.id] = c.displayName || ''
  dialog.value = true
}

const bodyTypeName = id => bodyTypes.value.find(b => b.id === id)?.name || ''

const submit = async () => {
  saving.value = true
  try {
    await vehicleCategoriesService.update(editing.value.id, {
      compatibleBodyTypeIds: selected.value,
      bodyTypeDisplayNames: Object.fromEntries(selected.value.map(id => [id, displayNames[id] || ''])),
    })
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
      Define qué carrocerías admite cada categoría de vehículo (por tonelaje puntual). Al registrar
      un vehículo solo se mostrarán las carrocerías compatibles con su categoría.
    </p>

    <VAlert v-if="loadError" type="error" variant="tonal" class="mb-4">
      {{ loadError }}
      <template #append><VBtn size="small" variant="text" @click="load">Reintentar</VBtn></template>
    </VAlert>

    <div v-if="loading" class="text-center py-10"><VProgressCircular indeterminate color="primary" /></div>

    <VCard v-for="group in groups" v-else :key="group.vehicleTypeName" class="mb-4">
      <VCardTitle class="text-subtitle-1 font-weight-bold py-3">{{ group.vehicleTypeName }}</VCardTitle>
      <VDivider />
      <VList lines="two" class="py-0">
        <template v-for="(row, i) in group.rows" :key="row.id">
          <VDivider v-if="i" />
          <VListItem>
            <VListItemTitle class="font-weight-medium">{{ row.name }}</VListItemTitle>
            <VListItemSubtitle class="mt-1">
              <template v-if="row.compatibleBodyTypes?.length">
                <VChip
                  v-for="c in row.compatibleBodyTypes" :key="c.id"
                  size="x-small" :color="c.displayName ? 'secondary' : 'primary'" variant="tonal" class="me-1 mb-1"
                  :prepend-icon="c.displayName ? 'ri-star-smile-line' : undefined"
                >
                  {{ c.displayName ? `${c.displayName} (${c.name})` : c.name }}
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
    </VCard>

    <VDialog v-model="dialog" max-width="560" persistent>
      <VCard v-if="editing">
        <VCardTitle>Carrocerías de {{ editing.name }}</VCardTitle>
        <VCardText>
          <VSelect
            v-model="selected"
            :items="bodyOptions"
            label="Carrocerías compatibles"
            multiple chips closable-chips
          />
          <p class="text-caption text-medium-emphasis mt-2 mb-3">
            Sin selección = el vehículo no lleva carrocería (moto, auto…) o no hay restricción.
          </p>

          <template v-if="selected.length">
            <VDivider class="mb-3" />
            <p class="text-caption text-medium-emphasis mb-2">
              <strong>Nombre propio para el cliente (opcional):</strong> si lo completás para una
              carrocería, esa combinación deja de listarse como una carrocería más de
              "{{ editing.name }}" y aparece en el cotizador como su propia opción con ese nombre
              (p. ej. "Cigüeña" en vez de "{{ editing.name }} · Furgón Cerrado"). El transportista
              sigue dando de alta su vehículo real + esa carrocería real, sin nada especial.
            </p>
            <VTextField
              v-for="id in selected" :key="id"
              v-model="displayNames[id]"
              :label="bodyTypeName(id)" placeholder="Nombre para el cliente (opcional)"
              density="compact" clearable class="mb-2" hide-details
            />
          </template>
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
