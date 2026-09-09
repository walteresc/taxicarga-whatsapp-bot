<script setup>
import { onMounted, reactive, ref, watch } from 'vue'

import { ApiError, apiClient } from '@/services/apiClient'
import PayrollConfigDialog from '@/components/planilla/PayrollConfigDialog.vue'
import { assistantsService, driversService, LICENSE_CATEGORIES } from '@/services/personnelService'
import { payrollConfigService } from '@/services/payrollService'

const TYPE = {
  conductor: { label: 'Conductor', color: 'primary', icon: 'ri-steering-line' },
  ayudante: { label: 'Ayudante', color: 'info', icon: 'ri-user-2-line' },
  asesor: { label: 'Asesor', color: 'success', icon: 'ri-briefcase-line' },
}
const FILTERS = [
  { value: '', label: 'Todos' },
  { value: 'conductor', label: 'Conductores' },
  { value: 'ayudante', label: 'Ayudantes' },
  { value: 'asesor', label: 'Asesores' },
]
const SVC = { conductor: driversService, ayudante: assistantsService }

const rows = ref([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const type = ref('')
const onlyActive = ref(true)
const page = ref(1)
const pages = ref(1)
const total = ref(0)
let searchTimer

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

// ── Configuración de planilla por trabajador ────────────────────────────
const PAYROLL_LABEL = { planilla: 'Planilla', honorarios: 'Honorarios' }
const payrollByWorker = ref({}) // `${type}:${workerId}` -> config
const balanceByWorker = ref({}) // `${type}:${workerId}` -> saldo de horas extra
const payrollKey = row => `${row.type}:${row.sourceId}`
const loadPayroll = async () => {
  try {
    const data = await payrollConfigService.list({ pageSize: 500 })
    const map = {}
    for (const c of data.results) map[`${c.workerType}:${c.workerId}`] = c
    payrollByWorker.value = map
  } catch { /* la columna simplemente queda vacía */ }
  try {
    const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Lima' }).format(new Date())
    const data = await apiClient.get('/api/v2/payroll/summary', { from: `${today.slice(0, 7)}-01`, to: today })
    const map = {}
    for (const r of data.rows) map[`${r.workerType}:${r.workerId}`] = r.balanceHours
    balanceByWorker.value = map
  } catch { /* la columna simplemente queda vacía */ }
}
const payrollDialog = ref(null) // fila del trabajador o null

const balanceLabel = h => (h == null ? '—' : `${h > 0 ? '+' : ''}${h.toFixed(2)}`)
const balanceClass = h => (h == null || h === 0 ? '' : (h > 0 ? 'text-success' : 'text-error'))

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    const data = await apiClient.get('/api/v2/personnel/', {
      search: search.value,
      type: type.value || undefined,
      status: onlyActive.value ? 'active' : undefined,
      page: page.value,
      pageSize: 25,
    })
    rows.value = data.results
    pages.value = data.pages
    total.value = data.total
  } catch (e) {
    error.value = e.message || 'No se pudo cargar el personal.'
  } finally {
    loading.value = false
  }
}

onMounted(() => { load(); loadPayroll() })
watch([type, onlyActive, page], load)
watch(search, () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { page.value = 1; load() }, 350) })

// ── Alta / edición inline ────────────────────────────────────────────────
const dialog = ref(false)
const formType = ref('conductor')
const editId = ref(null)
const saving = ref(false)
const errs = ref({})
const blank = () => ({
  name: '', documentId: '', phone: '', active: true,
  licenseNumber: '', licenseCategory: '', licenseExpiresOn: '',
})
const form = reactive(blank())

const openCreate = t => {
  formType.value = t
  editId.value = null
  Object.assign(form, blank())
  errs.value = {}
  dialog.value = true
}
const openEdit = async row => {
  if (row.type === 'asesor') return
  formType.value = row.type
  editId.value = row.sourceId
  errs.value = {}
  Object.assign(form, blank())
  dialog.value = true
  try {
    const full = await SVC[row.type].get(row.sourceId)
    Object.assign(form, {
      name: full.name || '', documentId: full.documentId || '', phone: full.phone || '',
      active: full.active ?? true,
      licenseNumber: full.licenseNumber || '', licenseCategory: full.licenseCategory || '',
      licenseExpiresOn: full.licenseExpiresOn || '',
    })
  } catch (e) {
    notify(e.message || 'No se pudo cargar el registro.', 'error')
  }
}

const submit = async () => {
  saving.value = true
  errs.value = {}
  const base = { name: form.name, documentId: form.documentId, phone: form.phone, active: form.active }
  const payload = formType.value === 'conductor'
    ? {
      ...base,
      licenseNumber: form.licenseNumber,
      licenseCategory: form.licenseCategory || '',
      licenseExpiresOn: form.licenseExpiresOn || null,
    }
    : base
  try {
    const svc = SVC[formType.value]
    if (editId.value) await svc.update(editId.value, payload)
    else await svc.create(payload)
    dialog.value = false
    notify(editId.value ? 'Cambios guardados.' : `${TYPE[formType.value].label} creado.`)
    await load()
  } catch (e) {
    if (e instanceof ApiError && Object.keys(e.fields).length) errs.value = e.fields
    else notify(e.message || 'No se pudo guardar.', 'error')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section>
    <div class="d-flex flex-wrap align-center justify-space-between ga-4 mb-6">
      <div>
        <h1 class="text-h4 font-weight-bold mb-1">Personal</h1>
        <p class="text-body-1 text-medium-emphasis mb-0">
          Directorio de nuestro equipo: conductores, ayudantes y asesores.
        </p>
      </div>
      <VBtn prepend-icon="ri-add-line" append-icon="ri-arrow-down-s-line">
        Nuevo personal
        <VMenu activator="parent">
          <VList>
            <VListItem prepend-icon="ri-steering-line" title="Conductor" @click="openCreate('conductor')" />
            <VListItem prepend-icon="ri-user-2-line" title="Ayudante" @click="openCreate('ayudante')" />
            <VListItem
              prepend-icon="ri-briefcase-line" title="Asesor"
              subtitle="Desde Usuarios y permisos" :disabled="true"
            />
          </VList>
        </VMenu>
      </VBtn>
    </div>

    <VCard>
      <VCardText class="d-flex flex-wrap align-center ga-4">
        <VTextField
          v-model="search" prepend-inner-icon="ri-search-line"
          label="Buscar por nombre, documento o teléfono"
          density="compact" hide-details clearable style="max-width: 340px;"
        />
        <div class="d-flex flex-wrap ga-2">
          <VChip
            v-for="f in FILTERS" :key="f.value"
            :color="type === f.value ? 'primary' : undefined"
            :variant="type === f.value ? 'flat' : 'tonal'"
            @click="type = f.value"
          >
            {{ f.label }}
          </VChip>
        </div>
        <VSwitch v-model="onlyActive" label="Solo activos" color="primary" hide-details density="compact" />
      </VCardText>

      <VAlert v-if="error" type="error" variant="tonal" class="ma-4">
        {{ error }}
        <template #append><VBtn size="small" variant="text" @click="load">Reintentar</VBtn></template>
      </VAlert>

      <VDivider />

      <VTable>
        <thead>
          <tr>
            <th>Nombre</th><th>Tipo</th><th>Documento</th><th>Teléfono</th><th>Detalle</th>
            <th>Planilla</th><th class="text-right">Saldo H. Extras</th><th>Estado</th><th class="text-right">Acciones</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="9" class="text-center py-8"><VProgressCircular indeterminate color="primary" /></td></tr>
          <tr v-else-if="!rows.length"><td colspan="9" class="text-center text-medium-emphasis py-10">Sin personal para el filtro.</td></tr>
          <tr v-for="row in rows" v-else :key="row.id">
            <td class="font-weight-medium">{{ row.name }}</td>
            <td>
              <VChip size="small" :color="TYPE[row.type]?.color" variant="tonal">
                <VIcon start :icon="TYPE[row.type]?.icon" size="14" /> {{ TYPE[row.type]?.label }}
              </VChip>
            </td>
            <td>{{ row.documentId || '—' }}</td>
            <td>{{ row.phone || '—' }}</td>
            <td class="text-medium-emphasis text-body-2">{{ row.detail || '—' }}</td>
            <td>
              <VChip
                v-if="payrollByWorker[payrollKey(row)]"
                size="small" color="primary" variant="tonal"
              >
                {{ PAYROLL_LABEL[payrollByWorker[payrollKey(row)].contractType] }}
              </VChip>
              <span v-else class="text-caption text-disabled">Sin configurar</span>
            </td>
            <td class="text-right font-weight-medium" :class="balanceClass(balanceByWorker[payrollKey(row)])">
              {{ balanceLabel(balanceByWorker[payrollKey(row)]) }}
            </td>
            <td><VChip size="small" :color="row.active ? 'success' : 'secondary'">{{ row.active ? 'Activo' : 'Inactivo' }}</VChip></td>
            <td class="text-right text-no-wrap">
              <VBtn
                size="small" variant="text" icon="ri-money-dollar-circle-line"
                title="Configuración de planilla" @click="payrollDialog = row"
              />
              <VBtn
                v-if="row.type !== 'asesor'" size="small" variant="text" icon="ri-edit-line"
                title="Editar" @click="openEdit(row)"
              />
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
    <VDialog v-model="dialog" max-width="520" persistent>
      <VCard>
        <VCardTitle>
          {{ editId ? 'Editar' : 'Nuevo' }} {{ TYPE[formType].label.toLowerCase() }}
        </VCardTitle>
        <VCardText>
          <VRow>
            <VCol cols="12"><VTextField v-model="form.name" label="Nombre completo" :error-messages="errs.name" /></VCol>
            <VCol cols="12" sm="6"><VTextField v-model="form.documentId" label="Documento (DNI)" :error-messages="errs.documentId" /></VCol>
            <VCol cols="12" sm="6"><VTextField v-model="form.phone" label="Teléfono" :error-messages="errs.phone" /></VCol>
            <template v-if="formType === 'conductor'">
              <VCol cols="12" sm="6"><VTextField v-model="form.licenseNumber" label="N° de licencia" :error-messages="errs.licenseNumber" /></VCol>
              <VCol cols="12" sm="6"><VSelect v-model="form.licenseCategory" :items="LICENSE_CATEGORIES" label="Categoría" clearable :error-messages="errs.licenseCategory" /></VCol>
              <VCol cols="12" sm="6"><AppDateField v-model="form.licenseExpiresOn" label="Vencimiento de licencia" density="comfortable" clearable :error-messages="errs.licenseExpiresOn" /></VCol>
            </template>
            <VCol cols="12"><VSwitch v-model="form.active" label="Activo" color="primary" /></VCol>
          </VRow>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" :disabled="saving" @click="dialog = false">Cancelar</VBtn>
          <VBtn :loading="saving" @click="submit">Guardar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <PayrollConfigDialog
      v-if="payrollDialog"
      :worker="payrollDialog"
      @close="payrollDialog = null"
      @saved="() => { notify('Configuración de planilla guardada.'); loadPayroll() }"
    />

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
