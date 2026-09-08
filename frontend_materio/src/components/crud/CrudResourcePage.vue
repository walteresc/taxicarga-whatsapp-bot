<script setup>
/**
 * Página CRUD reutilizable sobre un recurso de la API v2.
 *
 * Config-driven: se le pasa el `service` (createResource), las `columns` de la
 * tabla y los `fields` del formulario. Maneja búsqueda, filtro de estado,
 * ordenación, paginación, alta/edición con errores por campo, borrado,
 * activar/desactivar, y los estados de carga / error / vacío.
 *
 * Todas las claves (columns[].key, fields[].key, payload) son inglés canónico:
 * lo que devuelve y espera la API. Este componente no traduce nada.
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { ApiError } from '@/services/apiClient'
import { useAuthStore } from '@/stores/authStore'

const props = defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  hideHeader: { type: Boolean, default: false }, // true = sin h1/subtítulo (uso dentro de pestañas)
  singular: { type: String, required: true }, // "conductor"
  service: { type: Object, required: true },
  columns: { type: Array, required: true }, // [{ key, label, format?, align? }]
  fields: { type: Array, required: true }, // [{ key, label, type, options?, required?, cols? }]
  searchLabel: { type: String, default: 'Buscar' },
  // Filtros de botones extra. [{ value, label }]. El primero (value falsy) = "Todos".
  // Se pasa como `segment` a service.list().
  segments: { type: Array, default: () => [] },
  toggleField: { type: String, default: 'active' }, // habilita estado + activar/desactivar
  deletable: { type: Boolean, default: true }, // false = sin borrado duro (solo desactivar)
  labelField: { type: String, default: 'name' }, // para los mensajes ("<X> guardado")
  // Columna cuyo valor abre el detalle (slot #detail) al hacer clic. '' = sin detalle.
  detailField: { type: String, default: '' },
  writeRoles: { type: Array, default: () => ['Administrador', 'Supervisor', 'Asesor de Ventas'] },
})

const emit = defineEmits(['changed'])

const auth = useAuthStore()
const canWrite = computed(() => auth.hasAnyRole(...props.writeRoles))

// --- estado de la lista ---
const rows = ref([])
const loading = ref(false)
const loadError = ref('')
const search = ref('')
const status = ref('all')
const segment = ref('')
const ordering = ref('')
const page = ref(1)
const pageSize = 20
const total = ref(0)
const pages = ref(1)
let searchTimer

const colspan = computed(() => props.columns.length + 1 + (props.toggleField ? 1 : 0))

const load = async () => {
  loading.value = true
  loadError.value = ''
  try {
    const data = await props.service.list({
      search: search.value,
      status: props.toggleField ? status.value : undefined,
      segment: segment.value || undefined,
      ordering: ordering.value || undefined,
      page: page.value,
      pageSize,
    })
    rows.value = data.results
    total.value = data.total
    pages.value = data.pages
  } catch (err) {
    loadError.value = err.message || 'No se pudo cargar la lista.'
    rows.value = []
  } finally {
    loading.value = false
  }
}

const sortBy = key => {
  ordering.value = ordering.value === key ? `-${key}` : (ordering.value === `-${key}` ? '' : key)
  page.value = 1
  load()
}
const sortIcon = key => {
  if (ordering.value === key) return 'ri-arrow-up-s-line'
  if (ordering.value === `-${key}`) return 'ri-arrow-down-s-line'
  return 'ri-arrow-up-down-line'
}

watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; load() }, 350)
})
watch(status, () => { page.value = 1; load() })
watch(segment, () => { page.value = 1; load() })
watch(page, load)

load()

// --- alta / edición ---
const dialog = ref(false)
const saving = ref(false)
const editing = ref(null)
const form = reactive({})
const fieldErrors = ref({})

const blankForm = () => {
  const f = {}
  props.fields.forEach(fld => {
    f[fld.key] = fld.type === 'switch' ? true : ''
  })
  return f
}

const openCreate = () => {
  editing.value = null
  Object.assign(form, blankForm())
  fieldErrors.value = {}
  dialog.value = true
}

// Deep-link `?new=1` → abre el alta al entrar (viene de un menú "Nuevo …").
const route = useRoute()
onMounted(() => { if (route.query.new && canWrite.value) openCreate() })
const openEdit = row => {
  editing.value = row
  Object.assign(form, blankForm())
  props.fields.forEach(fld => { form[fld.key] = row[fld.key] ?? form[fld.key] })
  fieldErrors.value = {}
  dialog.value = true
}

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

const submit = async () => {
  saving.value = true
  fieldErrors.value = {}
  const payload = {}
  props.fields.forEach(fld => {
    let v = form[fld.key]
    if (fld.type === 'date' && !v) v = null
    payload[fld.key] = v
  })
  try {
    if (editing.value) await props.service.update(editing.value.id, payload)
    else await props.service.create(payload)
    dialog.value = false
    notify(`${props.singular[0].toUpperCase()}${props.singular.slice(1)} ${editing.value ? 'actualizado' : 'creado'}.`)
    await load()
    emit('changed')
  } catch (err) {
    if (err instanceof ApiError && Object.keys(err.fields).length) fieldErrors.value = err.fields
    else notify(err.message || 'No se pudo guardar.', 'error')
  } finally {
    saving.value = false
  }
}

// --- borrar / activar-desactivar ---
const confirming = ref(null)
const doDelete = async () => {
  const row = confirming.value
  confirming.value = null
  try {
    await props.service.remove(row.id)
    notify(`${props.singular[0].toUpperCase()}${props.singular.slice(1)} eliminado.`)
    if (rows.value.length === 1 && page.value > 1) page.value -= 1
    else await load()
    emit('changed')
  } catch (err) {
    notify(err.message || 'No se pudo eliminar.', 'error')
  }
}
const toggleActive = async row => {
  try {
    await props.service.action(row.id, 'toggle-active')
    await load()
    emit('changed')
  } catch (err) {
    notify(err.message || 'No se pudo cambiar el estado.', 'error')
  }
}

const cellValue = (row, col) => (col.format ? col.format(row) : (row[col.key] ?? '—'))
const fieldError = key => fieldErrors.value[key]?.[0]

const detailRow = ref(null)
const closeDetail = () => { detailRow.value = null }

defineExpose({ load })
</script>

<template>
  <section>
    <div class="d-flex flex-wrap align-center justify-space-between ga-4 mb-6">
      <div v-if="!hideHeader">
        <h1 class="text-h4 font-weight-bold mb-1">
          {{ title }}
        </h1>
        <p v-if="subtitle" class="text-body-1 text-medium-emphasis mb-0">
          {{ subtitle }}
        </p>
      </div>
      <VSpacer v-else />
      <VBtn v-if="canWrite" prepend-icon="ri-add-line" @click="openCreate">
        Nuevo {{ singular }}
      </VBtn>
    </div>

    <slot name="before-table" />

    <VCard>
      <VCardText class="d-flex flex-wrap align-center ga-4">
        <VTextField
          v-model="search"
          prepend-inner-icon="ri-search-line"
          :label="searchLabel"
          hide-details
          clearable
          density="compact"
          style="max-width: 340px;"
        />
        <div v-if="segments.length" class="d-flex flex-wrap ga-2">
          <VChip
            v-for="s in segments"
            :key="s.value"
            :color="segment === s.value ? 'primary' : undefined"
            :variant="segment === s.value ? 'flat' : 'tonal'"
            @click="segment = s.value"
          >
            {{ s.label }}
          </VChip>
        </div>
        <VSelect
          v-if="toggleField"
          v-model="status"
          :items="[
            { title: 'Todos', value: 'all' },
            { title: 'Activos', value: 'active' },
            { title: 'Inactivos', value: 'inactive' },
          ]"
          label="Estado"
          hide-details
          density="compact"
          style="max-width: 180px;"
        />
      </VCardText>

      <VAlert v-if="loadError" type="error" variant="tonal" class="ma-4">
        {{ loadError }}
        <template #append>
          <VBtn size="small" variant="text" @click="load">
            Reintentar
          </VBtn>
        </template>
      </VAlert>

      <VTable>
        <thead>
          <tr>
            <th v-for="col in columns" :key="col.key" :class="col.align === 'end' ? 'text-right' : ''">
              <button type="button" class="crud-sort" @click="sortBy(col.key)">
                {{ col.label }}
                <VIcon :icon="sortIcon(col.key)" size="16" />
              </button>
            </th>
            <th v-if="toggleField">
              Estado
            </th>
            <th class="text-right">
              Acciones
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td :colspan="colspan" class="text-center py-8">
              <VProgressCircular indeterminate color="primary" />
            </td>
          </tr>
          <tr v-else-if="!rows.length">
            <td :colspan="colspan" class="text-center text-medium-emphasis py-10">
              {{ search || status !== 'all' ? 'Sin resultados para el filtro.' : `Aún no hay ${singular}s registrados.` }}
            </td>
          </tr>
          <tr v-for="row in rows" v-else :key="row.id">
            <td v-for="col in columns" :key="col.key" :class="col.align === 'end' ? 'text-right' : ''">
              <VChip
                v-if="col.chip"
                size="small"
                :color="col.chip(row)?.color || 'default'"
                variant="tonal"
              >
                {{ col.chip(row)?.text ?? cellValue(row, col) }}
              </VChip>
              <button
                v-else-if="detailField && col.key === detailField"
                type="button" class="crud-link" @click="detailRow = row"
              >
                {{ cellValue(row, col) }}
              </button>
              <template v-else>{{ cellValue(row, col) }}</template>
            </td>
            <td v-if="toggleField">
              <VChip size="small" :color="row[toggleField] ? 'success' : 'secondary'">
                {{ row[toggleField] ? 'Activo' : 'Inactivo' }}
              </VChip>
            </td>
            <td class="text-right text-no-wrap">
              <template v-if="canWrite">
                <VBtn icon="ri-edit-line" variant="text" size="small" title="Editar" @click="openEdit(row)" />
                <VBtn
                  v-if="toggleField"
                  :icon="row[toggleField] ? 'ri-pause-circle-line' : 'ri-play-circle-line'"
                  variant="text" size="small"
                  :title="row[toggleField] ? 'Desactivar' : 'Activar'"
                  @click="toggleActive(row)"
                />
                <VBtn v-if="deletable" icon="ri-delete-bin-line" variant="text" size="small" color="error" title="Eliminar" @click="confirming = row" />
              </template>
              <span v-else class="text-disabled text-caption">Solo lectura</span>
            </td>
          </tr>
        </tbody>
      </VTable>

      <div v-if="pages > 1" class="d-flex justify-space-between align-center pa-4">
        <span class="text-caption text-medium-emphasis">{{ total }} en total</span>
        <VPagination v-model="page" :length="pages" :total-visible="5" density="comfortable" />
      </div>
    </VCard>

    <!-- Alta / edición -->
    <VDialog v-model="dialog" max-width="560" persistent>
      <VCard>
        <VCardTitle>{{ editing ? 'Editar' : 'Nuevo' }} {{ singular }}</VCardTitle>
        <VCardText>
          <VRow>
            <VCol v-for="fld in fields" :key="fld.key" :cols="12" :md="fld.cols || 12">
              <VTextField
                v-if="fld.type === 'text' || !fld.type"
                v-model="form[fld.key]"
                :label="fld.label"
                :error-messages="fieldError(fld.key)"
                :required="fld.required"
              />
              <VTextarea
                v-else-if="fld.type === 'textarea'"
                v-model="form[fld.key]"
                :label="fld.label"
                :error-messages="fieldError(fld.key)"
                rows="2" auto-grow
              />
              <VSelect
                v-else-if="fld.type === 'select'"
                v-model="form[fld.key]"
                :label="fld.label"
                :items="fld.options"
                :error-messages="fieldError(fld.key)"
                clearable
              />
              <VTextField
                v-else-if="fld.type === 'date'"
                v-model="form[fld.key]"
                :label="fld.label"
                type="date"
                :error-messages="fieldError(fld.key)"
              />
              <VSwitch
                v-else-if="fld.type === 'switch'"
                v-model="form[fld.key]"
                :label="fld.label"
                color="primary"
                :error-messages="fieldError(fld.key)"
              />
            </VCol>
          </VRow>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" :disabled="saving" @click="dialog = false">
            Cancelar
          </VBtn>
          <VBtn :loading="saving" @click="submit">
            Guardar
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Confirmar borrado -->
    <VDialog :model-value="!!confirming" max-width="420" @update:model-value="confirming = null">
      <VCard v-if="confirming">
        <VCardTitle>Eliminar {{ singular }}</VCardTitle>
        <VCardText>
          Se eliminará <strong>{{ confirming[labelField] }}</strong>. Esta acción no se puede deshacer.
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="confirming = null">
            Cancelar
          </VBtn>
          <VBtn color="error" @click="doDelete">
            Eliminar
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <slot name="detail" :row="detailRow" :close="closeDetail" />

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">
      {{ snackbar.text }}
    </VSnackbar>
  </section>
</template>

<style scoped>
.crud-sort {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font: inherit;
  color: inherit;
  background: none;
  border: 0;
  cursor: pointer;
  padding: 0;
}
.crud-sort:hover { color: rgb(var(--v-theme-primary)); }
.crud-link {
  font: inherit;
  color: rgb(var(--v-theme-primary));
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
  text-align: start;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.crud-link:hover { text-decoration-thickness: 2px; }
</style>
