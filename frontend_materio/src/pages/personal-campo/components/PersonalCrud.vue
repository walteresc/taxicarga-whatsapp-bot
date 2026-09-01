<script setup>
/* eslint-disable camelcase */
import { computed, onMounted, reactive, ref, watch } from 'vue'

const props = defineProps({
  type: { type: String, required: true },
  title: { type: String, required: true },
  service: { type: Object, required: true },
})

const items = ref([])
const loading = ref(false)
const saving = ref(false)
const dialog = ref(false)
const search = ref('')
const status = ref('all')
const page = ref(1)
const total = ref(0)
const pages = ref(1)
const alert = reactive({ show: false, type: 'success', text: '' })
const errors = ref({})
let searchTimer

const emptyForm = () => ({
  id: null,
  nombre: '',
  dni: '',
  telefono: '',
  numero_licencia: '',
  categoria_licencia: '',
  fecha_vencimiento_licencia: null,
  activo: true,
  observaciones: '',
})

const form = reactive(emptyForm())
const isConductor = computed(() => props.type === 'conductores')
const dialogTitle = computed(() => `${form.id ? 'Editar' : 'Nuevo'} ${isConductor.value ? 'conductor' : 'ayudante'}`)
const licenciaCategorias = ['A-I', 'A-II-a', 'A-II-b', 'A-III-a', 'A-III-b', 'A-III-c', 'B-I', 'B-II-a', 'B-II-b', 'B-II-c']

const notify = (text, type = 'success') => {
  Object.assign(alert, { show: true, text, type })
}

const load = async () => {
  loading.value = true
  try {
    const data = await props.service.list({
      search: search.value,
      status: status.value,
      page: page.value,
      page_size: 20,
    })

    items.value = data.results
    total.value = data.total
    pages.value = data.pages
  } catch (error) {
    notify(error.message, 'error')
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  Object.assign(form, emptyForm())
  errors.value = {}
  dialog.value = true
}

const openEdit = item => {
  Object.assign(form, emptyForm(), item)
  errors.value = {}
  dialog.value = true
}

const fieldError = name => errors.value[name]?.[0]

const save = async () => {
  saving.value = true
  errors.value = {}

  const payload = { ...form }

  delete payload.id
  if (!isConductor.value) {
    delete payload.numero_licencia
    delete payload.categoria_licencia
    delete payload.fecha_vencimiento_licencia
  }
  try {
    if (form.id) await props.service.update(form.id, payload)
    else await props.service.create(payload)
    dialog.value = false
    notify(`${isConductor.value ? 'Conductor' : 'Ayudante'} guardado.`)
    await load()
  } catch (error) {
    errors.value = error.errors || {}
    if (!Object.keys(errors.value).length) notify(error.message, 'error')
  } finally {
    saving.value = false
  }
}

const toggle = async item => {
  try {
    await props.service.update(item.id, { activo: !item.activo })
    notify(`${item.nombre} ${item.activo ? 'desactivado' : 'activado'}.`)
    await load()
  } catch (error) {
    notify(error.message, 'error')
  }
}

watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    load()
  }, 350)
})
watch(status, () => {
  page.value = 1
  load()
})
watch(page, load)
onMounted(load)
</script>

<template>
  <section>
    <div class="d-flex flex-wrap align-center justify-space-between ga-4 mb-6">
      <div>
        <h1 class="text-h4 font-weight-bold">
          {{ title }}
        </h1>
        <p class="text-body-1 text-medium-emphasis mb-0">
          Gestión de personal de campo
        </p>
      </div>
      <VBtn
        prepend-icon="ri-add-line"
        @click="openCreate"
      >
        Nuevo {{ isConductor ? 'conductor' : 'ayudante' }}
      </VBtn>
    </div>

    <VAlert
      v-if="alert.show"
      v-model="alert.show"
      closable
      :type="alert.type"
      class="mb-4"
    >
      {{ alert.text }}
    </VAlert>

    <VCard>
      <VCardText class="d-flex flex-wrap ga-4">
        <VTextField
          v-model="search"
          prepend-inner-icon="ri-search-line"
          label="Buscar por nombre, DNI o teléfono"
          hide-details
          clearable
          class="personal-search"
        />
        <VSelect
          v-model="status"
          :items="[{ title: 'Todos', value: 'all' }, { title: 'Activos', value: 'active' }, { title: 'Inactivos', value: 'inactive' }]"
          label="Estado"
          hide-details
          class="personal-status"
        />
      </VCardText>

      <VTable>
        <thead>
          <tr>
            <th>Nombre</th><th>DNI</th><th>Teléfono</th><th v-if="isConductor">
              Licencia
            </th><th>Estado</th><th class="text-right">
              Acciones
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td
              :colspan="isConductor ? 6 : 5"
              class="text-center py-8"
            >
              <VProgressCircular
                indeterminate
                color="primary"
              />
            </td>
          </tr>
          <tr v-else-if="!items.length">
            <td
              :colspan="isConductor ? 6 : 5"
              class="text-center text-medium-emphasis py-8"
            >
              No hay registros.
            </td>
          </tr>
          <tr
            v-for="item in items"
            v-else
            :key="item.id"
          >
            <td class="font-weight-medium">
              {{ item.nombre }}
            </td><td>{{ item.dni }}</td><td>{{ item.telefono }}</td>
            <td v-if="isConductor">
              {{ item.numero_licencia || '—' }}<span
                v-if="item.categoria_licencia"
                class="text-medium-emphasis"
              > · {{ item.categoria_licencia }}</span>
            </td>
            <td>
              <VChip
                size="small"
                :color="item.activo ? 'success' : 'secondary'"
              >
                {{ item.activo ? 'Activo' : 'Inactivo' }}
              </VChip>
            </td>
            <td class="text-right">
              <VBtn
                icon="ri-edit-line"
                variant="text"
                size="small"
                title="Editar"
                @click="openEdit(item)"
              /><VBtn
                :icon="item.activo ? 'ri-user-unfollow-line' : 'ri-user-follow-line'"
                variant="text"
                size="small"
                :color="item.activo ? 'error' : 'success'"
                :title="item.activo ? 'Desactivar' : 'Activar'"
                @click="toggle(item)"
              />
            </td>
          </tr>
        </tbody>
      </VTable>

      <VDivider />
      <VCardText class="d-flex align-center justify-space-between">
        <span class="text-body-2 text-medium-emphasis">{{ total }} registros</span><VPagination
          v-if="pages > 1"
          v-model="page"
          :length="pages"
          density="compact"
        />
      </VCardText>
    </VCard>

    <VDialog
      v-model="dialog"
      max-width="680"
    >
      <VCard :title="dialogTitle">
        <VCardText>
          <VAlert
            v-if="fieldError('general')"
            type="error"
            class="mb-4"
          >
            {{ fieldError('general') }}
          </VAlert>
          <VRow>
            <VCol
              cols="12"
              md="6"
            >
              <VTextField
                v-model="form.nombre"
                label="Nombre completo"
                :error-messages="fieldError('nombre')"
              />
            </VCol>
            <VCol
              cols="12"
              md="6"
            >
              <VTextField
                v-model="form.dni"
                label="DNI"
                maxlength="20"
                :error-messages="fieldError('dni')"
              />
            </VCol>
            <VCol
              cols="12"
              md="6"
            >
              <VTextField
                v-model="form.telefono"
                label="Teléfono"
                :error-messages="fieldError('telefono')"
              />
            </VCol>
            <template v-if="isConductor">
              <VCol
                cols="12"
                md="6"
              >
                <VTextField
                  v-model="form.numero_licencia"
                  label="Número de licencia"
                  :error-messages="fieldError('numero_licencia')"
                />
              </VCol>
              <VCol
                cols="12"
                md="6"
              >
                <VSelect
                  v-model="form.categoria_licencia"
                  :items="licenciaCategorias"
                  label="Categoría"
                  clearable
                  :error-messages="fieldError('categoria_licencia')"
                />
              </VCol>
              <VCol
                cols="12"
                md="6"
              >
                <VTextField
                  v-model="form.fecha_vencimiento_licencia"
                  type="date"
                  label="Vencimiento de licencia"
                  :error-messages="fieldError('fecha_vencimiento_licencia')"
                />
              </VCol>
            </template>
            <VCol cols="12">
              <VTextarea
                v-model="form.observaciones"
                label="Observaciones"
                rows="3"
                :error-messages="fieldError('observaciones')"
              />
            </VCol>
            <VCol cols="12">
              <VSwitch
                v-model="form.activo"
                label="Personal activo"
                color="success"
                hide-details
              />
            </VCol>
          </VRow>
        </VCardText>
        <VCardActions class="px-6 pb-6">
          <VSpacer /><VBtn
            variant="text"
            @click="dialog = false"
          >
            Cancelar
          </VBtn><VBtn
            :loading="saving"
            @click="save"
          >
            Guardar
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </section>
</template>

<style scoped>
.personal-search { min-inline-size: 280px; flex: 1; }
.personal-status { max-inline-size: 190px; }
</style>
