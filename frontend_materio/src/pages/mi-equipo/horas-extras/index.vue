<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { ApiError } from '@/services/apiClient'
import {
  DAY_TYPES, fetchPayrollDay, payrollConfigService, savePayrollDay,
} from '@/services/payrollService'

const CONTRACT = { planilla: 'Planilla', honorarios: 'Honorarios' }
const DAY_LABEL = Object.fromEntries(DAY_TYPES.map(d => [d.value, d.label]))
const limaToday = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Lima' }).format(new Date())

const date = ref(limaToday())
const rows = ref([])
const loading = ref(true)
const error = ref('')
const workers = ref([])

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

const prettyDate = computed(() =>
  new Date(`${date.value}T12:00:00`).toLocaleDateString('es-PE', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  }))

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    const data = await fetchPayrollDay(date.value)
    rows.value = data.rows
  } catch (e) {
    error.value = e.message || 'No se pudo cargar la asistencia.'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const w = await payrollConfigService.list({ pageSize: 500, status: 'active' })
    workers.value = w.results
  } catch { /* */ }
  load()
})

const shiftDay = n => {
  const d = new Date(`${date.value}T12:00:00`)
  d.setDate(d.getDate() + n)
  date.value = new Intl.DateTimeFormat('en-CA').format(d)
  load()
}
const today = () => { date.value = limaToday(); load() }

const num = n => (n == null ? '—' : Number(n).toFixed(2))
const deltaColor = d => (d == null || d === 0 ? '' : (d > 0 ? 'text-success' : 'text-error'))
const withSign = d => (d == null ? '—' : (d > 0 ? '+' : '') + num(d))

// ── Registrar / editar asistencia ─────────────────────────────────────
const dialog = ref(false)
const saving = ref(false)
const errs = ref({})
const editing = ref(false)
const form = reactive({
  trabajadorId: null, fecha: '', dayType: 'trabajado', clockIn: '', clockOut: '', note: '',
})

const selectedWorker = computed(() => workers.value.find(w => w.id === form.trabajadorId) || null)
const isWorked = computed(() => form.dayType === 'trabajado')

const preview = computed(() => {
  const w = selectedWorker.value
  if (!w || !isWorked.value || !form.clockIn || !form.clockOut) return null
  const [h1, m1] = form.clockIn.split(':').map(Number)
  const [h2, m2] = form.clockOut.split(':').map(Number)
  let mins = (h2 * 60 + m2) - (h1 * 60 + m1)
  if (mins <= 0) mins += 1440
  const worked = mins / 60 - Number(w.lunchHours || 0)
  const delta = worked - Number(w.workdayHours || 0)
  return { worked, delta }
})

const openCreate = () => {
  editing.value = false
  errs.value = {}
  Object.assign(form, {
    trabajadorId: null, fecha: date.value, dayType: 'trabajado', clockIn: '', clockOut: '', note: '',
  })
  dialog.value = true
}
const openEdit = row => {
  editing.value = true
  errs.value = {}
  Object.assign(form, {
    trabajadorId: row.trabajadorId, fecha: date.value, dayType: row.dayType,
    clockIn: row.clockIn || '', clockOut: row.clockOut || '', note: row.note || '',
  })
  dialog.value = true
}

const canSave = computed(() => {
  if (!form.trabajadorId || !form.fecha) return false
  if (isWorked.value) return !!form.clockIn && !!form.clockOut
  return true
})

const submit = async () => {
  saving.value = true
  errs.value = {}
  try {
    await savePayrollDay({
      trabajadorId: form.trabajadorId,
      fecha: form.fecha,
      dayType: form.dayType,
      clockIn: isWorked.value ? form.clockIn : null,
      clockOut: isWorked.value ? form.clockOut : null,
      note: form.note,
    })
    dialog.value = false
    notify(editing.value ? 'Asistencia actualizada.' : 'Asistencia registrada.')
    if (form.fecha === date.value) load()
    else notify(`Registrada para ${form.fecha}.`)
  } catch (e) {
    if (e instanceof ApiError && Object.keys(e.fields).length) errs.value = e.fields
    else notify(e.message || 'No se pudo guardar.', 'error')
  } finally {
    saving.value = false
  }
}

const removeRow = async row => {
  if (!confirm(`¿Borrar la asistencia de ${row.workerName} del ${date.value}?`)) return
  try {
    await savePayrollDay({ trabajadorId: row.trabajadorId, fecha: date.value, clear: true })
    notify('Registro eliminado.')
    load()
  } catch (e) { notify(e.message || 'No se pudo eliminar.', 'error') }
}
</script>

<template>
  <section>
    <div class="mb-4">
      <h1 class="text-h4 font-weight-bold mb-1">Asistencia</h1>
      <p class="text-body-1 text-medium-emphasis mb-0">
        Asistencia registrada por día. Las horas trabajadas, las horas extra del día y el saldo acumulado se calculan solos.
      </p>
    </div>

    <VAlert v-if="error" type="error" variant="tonal" class="mb-4">
      {{ error }}
      <template #append><VBtn size="small" variant="text" @click="load">Reintentar</VBtn></template>
    </VAlert>

    <VCard>
      <VCardText class="d-flex flex-wrap align-center justify-space-between ga-3">
        <div class="d-flex flex-wrap align-center ga-2">
          <VBtn icon="ri-arrow-left-s-line" variant="tonal" size="small" @click="shiftDay(-1)" />
          <AppDateField v-model="date" hide-details style="flex: 0 0 190px; width: 190px;" @update:model-value="load" />
          <VBtn icon="ri-arrow-right-s-line" variant="tonal" size="small" @click="shiftDay(1)" />
          <VBtn variant="text" size="small" @click="today">Hoy</VBtn>
          <span class="text-body-2 text-medium-emphasis text-capitalize ms-2">{{ prettyDate }}</span>
        </div>
        <VBtn prepend-icon="ri-add-line" @click="openCreate">Registrar asistencia</VBtn>
      </VCardText>
      <VDivider />

      <div v-if="loading" class="text-center py-12"><VProgressCircular indeterminate color="primary" /></div>

      <div v-else-if="!rows.length" class="text-center py-12 px-4">
        <VIcon icon="ri-time-line" size="48" class="text-disabled mb-2" />
        <p class="text-body-1 text-medium-emphasis mb-1">Nadie tiene asistencia registrada para este día.</p>
        <p class="text-body-2 text-disabled mb-3">Usá "Registrar asistencia" para empezar.</p>
        <VBtn variant="tonal" prepend-icon="ri-add-line" @click="openCreate">Registrar asistencia</VBtn>
      </div>

      <VTable v-else>
        <thead>
          <tr>
            <th>Trabajador</th><th>Tipo de día</th>
            <th>Ingreso</th><th>Salida</th>
            <th class="text-right">Horas trab.</th>
            <th class="text-right">H. Extras Día</th>
            <th class="text-right">Saldo H. Extras</th>
            <th class="text-right">Acciones</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.trabajadorId">
            <td>
              <div class="font-weight-medium">{{ row.workerName }}</div>
              <VChip size="x-small" variant="tonal">{{ CONTRACT[row.contractType] }} · {{ num(row.workdayHours) }}h</VChip>
            </td>
            <td>
              <VChip size="small" variant="tonal" :color="row.dayType === 'falta' ? 'error' : (row.dayType === 'trabajado' ? undefined : 'secondary')">
                {{ DAY_LABEL[row.dayType] || row.dayType }}
              </VChip>
            </td>
            <td>{{ row.clockIn || '—' }}</td>
            <td>{{ row.clockOut || '—' }}</td>
            <td class="text-right">{{ num(row.workedHours) }}</td>
            <td class="text-right" :class="deltaColor(row.delta)">{{ withSign(row.delta) }}</td>
            <td class="text-right font-weight-medium" :class="deltaColor(row.balanceHours)">{{ withSign(row.balanceHours) }}</td>
            <td class="text-right text-no-wrap">
              <VBtn size="small" variant="text" icon="ri-edit-line" title="Editar" @click="openEdit(row)" />
              <VBtn size="small" variant="text" icon="ri-delete-bin-line" color="error" title="Borrar" @click="removeRow(row)" />
            </td>
          </tr>
        </tbody>
      </VTable>
    </VCard>

    <!-- Registrar / editar asistencia -->
    <VDialog v-model="dialog" max-width="520" persistent>
      <VCard>
        <VCardTitle class="pt-5">{{ editing ? 'Editar asistencia' : 'Registrar asistencia' }}</VCardTitle>
        <VCardText class="pt-2">
          <VAutocomplete
            v-model="form.trabajadorId"
            :items="workers.map(w => ({ title: `${w.workerName} — ${CONTRACT[w.contractType]}`, value: w.id }))"
            label="Trabajador" prepend-inner-icon="ri-user-line"
            :disabled="editing" :error-messages="errs.trabajadorId"
            autofocus
          />

          <VExpandTransition>
            <div v-if="form.trabajadorId">
              <AppDateField
                v-model="form.fecha" label="Fecha" density="comfortable"
                class="mt-4" :error-messages="errs.fecha"
              />
              <VSelect
                v-model="form.dayType" :items="DAY_TYPES" item-title="label" item-value="value"
                label="Tipo de registro" density="comfortable" class="mt-4"
              />
              <div class="d-flex ga-4 mt-4">
                <AppTimeField
                  v-model="form.clockIn" label="Hora de ingreso" density="comfortable"
                  :disabled="!isWorked" hide-details style="flex: 1 1 0;"
                />
                <AppTimeField
                  v-model="form.clockOut" label="Hora de salida" density="comfortable"
                  :disabled="!isWorked" hide-details style="flex: 1 1 0;"
                />
              </div>
              <VTextField v-model="form.note" label="Observación (opcional)" density="comfortable" class="mt-4" />

              <VAlert
                v-if="preview" type="info" variant="tonal" density="compact" class="mt-4"
              >
                Horas trabajadas: <strong>{{ preview.worked.toFixed(2) }}</strong> ·
                Δ del día:
                <strong :class="preview.delta > 0 ? 'text-success' : (preview.delta < 0 ? 'text-error' : '')">
                  {{ (preview.delta > 0 ? '+' : '') + preview.delta.toFixed(2) }}
                </strong>
              </VAlert>
            </div>
          </VExpandTransition>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" :disabled="saving" @click="dialog = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="saving" :disabled="!canSave" @click="submit">
            {{ editing ? 'Guardar' : 'Registrar' }}
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
