<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { apiClient, ApiError } from '@/services/apiClient'
import WorkerPayrollDialog from '@/components/planilla/WorkerPayrollDialog.vue'
import {
  fetchPayCalc, PAYMENT_TYPES, payrollConfigService, paymentsService,
} from '@/services/payrollService'

const TYPE = Object.fromEntries(PAYMENT_TYPES.map(t => [t.value, t.label]))
const soles = n => (n == null ? '—' : `S/ ${Number(n).toLocaleString('es-PE', { minimumFractionDigits: 2 })}`)
const iso = d => new Intl.DateTimeFormat('en-CA').format(d)
const limaToday = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Lima' }).format(new Date())
const limaMonth = () => limaToday().slice(0, 7)

const tab = ref('resumen')
const workers = ref([])
const rows = ref([])
const loading = ref(true)
const error = ref('')

// ── Resumen ────────────────────────────────────────────────────────────
const SUM_PRESETS = [
  { value: 'mtd', label: 'Al día de hoy', type: 'por_dias' },
  { value: 'month', label: 'Mes completo', type: 'fin_de_mes' },
  { value: 'q1', label: 'Quincena 1', type: 'quincena' },
  { value: 'q2', label: 'Quincena 2', type: 'quincena' },
  { value: 'custom', label: 'Entre fechas', type: 'por_dias' },
]
const monthFirstIso = () => `${limaMonth()}-01`
const summaryPreset = ref('mtd')
const summaryFrom = ref(monthFirstIso())
const summaryTo = ref(limaToday())
const summaryType = ref('por_dias')
const summary = ref([])
const summaryLoading = ref(false)
const detailWorker = ref(null)

// Los chips solo pre-llenan Desde/Hasta (relativo al mes de "Desde"). Las
// fechas siempre quedan editables a mano; editarlas pasa a "Entre fechas".
const applySumPreset = (val) => {
  summaryPreset.value = val
  const p = SUM_PRESETS.find(x => x.value === val)
  if (val === 'custom') { summaryType.value = 'por_dias'; return }
  const base = (summaryFrom.value || limaToday()).split('-').map(Number)
  const [y, m] = base
  const first = new Date(y, m - 1, 1)
  const last = new Date(y, m, 0)
  let from = iso(first)
  let to = iso(last)
  if (val === 'mtd') {
    const t = new Date(limaToday())
    to = iso(t >= first && t <= last ? t : last)
  } else if (val === 'q1') {
    to = iso(new Date(y, m - 1, 15))
  } else if (val === 'q2') {
    from = iso(new Date(y, m - 1, 16))
  }
  summaryFrom.value = from
  summaryTo.value = to
  summaryType.value = p.type
}
const onSumDateEdit = () => { summaryPreset.value = 'custom'; summaryType.value = 'por_dias' }

const loadSummary = async () => {
  const from = summaryFrom.value
  const to = summaryTo.value
  if (!from || !to || from > to) { summary.value = []; return }
  summaryLoading.value = true
  try {
    const d = await apiClient.get('/api/v2/payroll/summary', { from, to, type: summaryType.value })
    summary.value = d.rows
  } catch { summary.value = [] } finally { summaryLoading.value = false }
}
watch([summaryFrom, summaryTo, summaryType], loadSummary)

const summaryTotal = computed(() => summary.value.reduce((t, s) => t + (s.estimatedNet || 0), 0))

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

const statusFilter = ref('')
const load = async () => {
  loading.value = true
  error.value = ''
  try {
    const data = await paymentsService.list({
      pageSize: 200,
      paid: statusFilter.value === 'paid' ? 'true' : (statusFilter.value === 'pending' ? 'false' : undefined),
    })
    rows.value = data.results
  } catch (e) {
    error.value = e.message || 'No se pudieron cargar los pagos.'
  } finally {
    loading.value = false
  }
}
const setStatus = v => { statusFilter.value = v; load() }

onMounted(async () => {
  try {
    const w = await payrollConfigService.list({ pageSize: 500, status: 'active' })
    workers.value = w.results
  } catch { /* */ }
  load()
  loadSummary()
})

// ── Nuevo pago / calcular ──────────────────────────────────────────────
const dialog = ref(false)
const saving = ref(false)
const errs = ref({})
const calc = ref(null)
const calcLoading = ref(false)

// Método de cálculo del pago
const PAY_METHODS = [
  { value: 'por_dias', label: 'Proporcional por días trabajados' },
  { value: 'fin_de_mes', label: 'Sueldo del mes completo' },
  { value: 'quincena', label: 'Media quincena' },
  { value: 'adelanto', label: 'Adelanto (monto libre)' },
]

const form = reactive({
  trabajadorId: null, type: 'por_dias', freeAmount: '',
  periodFrom: '', periodTo: '', otherDeductions: '0', otherDeductionsReason: '', note: '',
})
const isAdelanto = computed(() => form.type === 'adelanto')

// Atajos: llenan Desde/Hasta y el método a partir del mes actual (Lima).
const applyQuick = (kind) => {
  const [y, m] = limaMonth().split('-').map(Number)
  const first = new Date(y, m - 1, 1)
  const last = new Date(y, m, 0)
  if (kind === 'month') { form.periodFrom = iso(first); form.periodTo = iso(last); form.type = 'fin_de_mes' }
  else if (kind === 'q1') { form.periodFrom = iso(first); form.periodTo = iso(new Date(y, m - 1, 15)); form.type = 'quincena' }
  else if (kind === 'q2') { form.periodFrom = iso(new Date(y, m - 1, 16)); form.periodTo = iso(last); form.type = 'quincena' }
  else if (kind === 'mtd') { form.periodFrom = iso(first); form.periodTo = iso(new Date(limaToday())); form.type = 'por_dias' }
}

const openNew = ({ trabajadorId = null, from = '', to = '', type = 'por_dias' } = {}) => {
  errs.value = {}
  calc.value = null
  Object.assign(form, {
    trabajadorId, type,
    periodFrom: from, periodTo: to, otherDeductions: '0', otherDeductionsReason: '', note: '',
  })
  if (!from || !to) applyQuick('month')
  dialog.value = true
}
const registerFor = s => {
  openNew({ trabajadorId: s.trabajadorId, from: s.periodFrom, to: s.periodTo, type: summaryType.value })
}

let calcTimer
const runCalc = () => {
  clearTimeout(calcTimer)
  if (isAdelanto.value) { calc.value = null; return }
  calcTimer = setTimeout(async () => {
    if (!form.trabajadorId || !form.periodFrom || !form.periodTo) { calc.value = null; return }
    calcLoading.value = true
    try {
      calc.value = await fetchPayCalc({
        trabajadorId: form.trabajadorId, from: form.periodFrom, to: form.periodTo, type: form.type,
      })
    } catch { calc.value = null } finally { calcLoading.value = false }
  }, 300)
}
watch(() => [form.trabajadorId, form.type, form.periodFrom, form.periodTo], runCalc)

const grossAmount = computed(() => (isAdelanto.value ? (Number(form.freeAmount) || 0) : (calc.value?.grossAmount ?? 0)))
const afpAmount = computed(() => (isAdelanto.value ? 0 : (calc.value?.afpDeduction ?? 0)))
const netAfterOther = computed(() => {
  if (!isAdelanto.value && !calc.value) return null
  return Math.max(0, grossAmount.value - afpAmount.value - (Number(form.otherDeductions) || 0))
})
const canSubmit = computed(() => (isAdelanto.value ? Number(form.freeAmount) > 0 : !!calc.value)
  && !!form.periodFrom && !!form.periodTo)

const submit = async () => {
  if (!canSubmit.value) { notify('Completá trabajador, período y monto.', 'warning'); return }
  saving.value = true
  errs.value = {}
  try {
    await paymentsService.create({
      trabajadorId: form.trabajadorId,
      type: form.type,
      periodFrom: form.periodFrom,
      periodTo: form.periodTo,
      daysWorked: calc.value ? (calc.value.payableDays ?? calc.value.daysWorked) : 0,
      absencesDeducted: calc.value?.absencesDeducted ?? 0,
      grossAmount: grossAmount.value,
      afpDeduction: afpAmount.value,
      otherDeductions: form.otherDeductions || 0,
      otherDeductionsReason: form.otherDeductionsReason,
      netAmount: netAfterOther.value,
      note: form.note,
    })
    dialog.value = false
    notify('Pago registrado.')
    load(); loadSummary()
  } catch (e) {
    if (e instanceof ApiError && Object.keys(e.fields).length) errs.value = e.fields
    else notify(e.message || 'No se pudo registrar.', 'error')
  } finally {
    saving.value = false
  }
}

// ── Marcar pagado ──────────────────────────────────────────────────────
const payDialog = ref(null)
const payOn = ref('')
const payMethod = ref('')
const openPay = row => {
  payDialog.value = row
  payOn.value = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Lima' }).format(new Date())
  payMethod.value = row.method || 'transferencia'
}
const confirmPay = async () => {
  try {
    await paymentsService.update(payDialog.value.id, {
      paid: true, paidOn: payOn.value, method: payMethod.value,
    })
    payDialog.value = null
    notify('Pago marcado como pagado.')
    load()
  } catch (e) { notify(e.message || 'No se pudo actualizar.', 'error') }
}

const removePayment = async row => {
  if (!confirm(`¿Borrar el pago de ${row.workerName}?`)) return
  try {
    await paymentsService.remove(row.id)
    notify('Pago eliminado.')
    load()
  } catch (e) { notify(e.message || 'No se pudo eliminar.', 'error') }
}
</script>

<template>
  <section>
    <div class="d-flex flex-wrap align-center justify-space-between ga-4 mb-4">
      <div>
        <h1 class="text-h4 font-weight-bold mb-1">Pagos</h1>
        <p class="text-body-1 text-medium-emphasis mb-0">
          Liquidación por quincena, fin de mes o rango de fechas (para altas/bajas a mitad de mes). El sistema calcula bruto, AFP y neto.
        </p>
      </div>
      <VBtn prepend-icon="ri-add-line" @click="openNew()">Nuevo pago</VBtn>
    </div>

    <VTabs v-model="tab" class="mb-4">
      <VTab value="resumen">Resumen</VTab>
      <VTab value="pagos">Pagos registrados</VTab>
    </VTabs>

    <VAlert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</VAlert>

    <!-- Resumen -->
    <template v-if="tab === 'resumen'">
      <VCard>
        <VCardText>
          <div class="text-caption text-medium-emphasis mb-1">Período a calcular</div>
          <div class="d-flex flex-wrap ga-2 mb-3">
            <VChip
              v-for="p in SUM_PRESETS" :key="p.value"
              :color="summaryPreset === p.value ? 'primary' : undefined"
              :variant="summaryPreset === p.value ? 'flat' : 'tonal'"
              @click="applySumPreset(p.value)"
            >
              {{ p.label }}
            </VChip>
          </div>
          <div class="d-flex flex-wrap ga-3 mb-1">
            <AppDateField
              v-model="summaryFrom" label="Desde" hide-details
              class="flex-grow-0" style="max-width: 160px;" @update:model-value="onSumDateEdit"
            />
            <AppDateField
              v-model="summaryTo" label="Hasta" hide-details
              class="flex-grow-0" style="max-width: 160px;" @update:model-value="onSumDateEdit"
            />
          </div>
          <div v-if="summaryFrom > summaryTo" class="text-caption text-error">
            La fecha "Desde" no puede ser mayor que "Hasta".
          </div>
        </VCardText>
        <VDivider />
        <VTable>
          <thead>
            <tr>
              <th>Trabajador</th><th>Contrato</th>
              <th class="text-right">Saldo H. Extras</th><th class="text-right">Valor saldo</th>
              <th class="text-right">Faltas</th><th class="text-right">Sin resolver</th>
              <th class="text-right">Días trab.</th><th class="text-right">Vac. pend.</th>
              <th class="text-right">A pagar (est.)</th>
              <th class="text-right">Acciones</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="summaryLoading"><td colspan="10" class="text-center py-8"><VProgressCircular indeterminate color="primary" /></td></tr>
            <tr v-else-if="!summary.length"><td colspan="10" class="text-center text-medium-emphasis py-10">Sin trabajadores en planilla.</td></tr>
            <tr v-for="s in summary" v-else :key="s.trabajadorId">
              <td class="font-weight-medium">{{ s.workerName }}</td>
              <td><VChip size="x-small" variant="tonal">{{ s.contractType === 'planilla' ? 'Planilla' : 'Honorarios' }}</VChip></td>
              <td class="text-right" :class="s.balanceHours > 0 ? 'text-success' : (s.balanceHours < 0 ? 'text-error' : '')">
                {{ (s.balanceHours > 0 ? '+' : '') + s.balanceHours.toFixed(2) }}
              </td>
              <td class="text-right text-medium-emphasis">{{ soles(s.balanceValue) }}</td>
              <td class="text-right">{{ s.absencesRange }}</td>
              <td class="text-right" :class="s.absencesUnresolved ? 'text-error font-weight-medium' : ''">{{ s.absencesUnresolved }}</td>
              <td class="text-right">{{ s.daysWorkedRange }}</td>
              <td class="text-right">{{ s.vacationDaysPending ?? '—' }}</td>
              <td class="text-right font-weight-bold">{{ soles(s.estimatedNet) }}</td>
              <td class="text-right text-no-wrap">
                <VBtn size="small" variant="text" icon="ri-eye-line" title="Ver detalle" @click="detailWorker = s.trabajadorId" />
                <VBtn size="small" variant="text" icon="ri-bank-card-line" color="primary" title="Registrar pago" @click="registerFor(s)" />
              </td>
            </tr>
          </tbody>
          <tfoot v-if="summary.length && !summaryLoading">
            <tr class="font-weight-bold">
              <td colspan="8" class="text-right">Total a pagar en el período</td>
              <td class="text-right text-h6">{{ soles(summaryTotal) }}</td>
              <td></td>
            </tr>
          </tfoot>
        </VTable>
      </VCard>
    </template>

    <VCard v-else>
      <VCardText class="d-flex flex-wrap ga-2">
        <VChip
          v-for="f in [{ v: '', l: 'Todos' }, { v: 'pending', l: 'Pendientes' }, { v: 'paid', l: 'Pagados' }]"
          :key="f.v" :color="statusFilter === f.v ? 'primary' : undefined"
          :variant="statusFilter === f.v ? 'flat' : 'tonal'" @click="setStatus(f.v)"
        >
          {{ f.l }}
        </VChip>
      </VCardText>
      <VDivider />
      <VTable>
        <thead>
          <tr>
            <th>Período</th><th>Trabajador</th><th>Tipo</th>
            <th class="text-right">Bruto</th><th class="text-right">AFP</th>
            <th class="text-right">Otros</th><th class="text-right">Neto</th>
            <th>Estado</th><th class="text-right">Acciones</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="9" class="text-center py-8"><VProgressCircular indeterminate color="primary" /></td></tr>
          <tr v-else-if="!rows.length"><td colspan="9" class="text-center text-medium-emphasis py-10">No hay pagos para el filtro.</td></tr>
          <tr v-for="row in rows" v-else :key="row.id">
            <td class="text-no-wrap">{{ row.periodFrom }} → {{ row.periodTo }}</td>
            <td class="font-weight-medium">{{ row.workerName }}</td>
            <td><VChip size="small" variant="tonal">{{ TYPE[row.type] }}</VChip></td>
            <td class="text-right">{{ soles(row.grossAmount) }}</td>
            <td class="text-right text-medium-emphasis">{{ soles(row.afpDeduction) }}</td>
            <td class="text-right text-medium-emphasis">{{ soles(row.otherDeductions) }}</td>
            <td class="text-right font-weight-bold">{{ soles(row.netAmount) }}</td>
            <td>
              <VChip size="small" :color="row.paid ? 'success' : 'warning'">
                {{ row.paid ? `Pagado ${row.paidOn || ''}` : 'Pendiente' }}
              </VChip>
            </td>
            <td class="text-right text-no-wrap">
              <VBtn v-if="!row.paid" size="small" variant="text" icon="ri-check-double-line" title="Marcar pagado" @click="openPay(row)" />
              <VBtn size="small" variant="text" icon="ri-delete-bin-line" color="error" title="Eliminar" @click="removePayment(row)" />
            </td>
          </tr>
        </tbody>
      </VTable>
    </VCard>

    <!-- Nuevo pago / calcular -->
    <VDialog v-model="dialog" max-width="640" persistent>
      <VCard>
        <VCardTitle>Calcular y registrar pago</VCardTitle>
        <VCardText>
          <VAutocomplete
            v-model="form.trabajadorId"
            :items="workers.map(w => ({ title: `${w.workerName} — ${w.contractType === 'planilla' ? 'Planilla' : 'Honorarios'}`, value: w.id }))"
            label="Trabajador" prepend-inner-icon="ri-user-line"
            :error-messages="errs.trabajadorId" autofocus
          />

          <VExpandTransition>
            <div v-if="form.trabajadorId">
              <div class="text-caption text-medium-emphasis mt-3 mb-1">Atajos del mes actual</div>
              <div class="d-flex flex-wrap ga-2 mb-3">
                <VChip size="small" variant="tonal" @click="applyQuick('month')">Mes completo</VChip>
                <VChip size="small" variant="tonal" @click="applyQuick('q1')">Quincena 1</VChip>
                <VChip size="small" variant="tonal" @click="applyQuick('q2')">Quincena 2</VChip>
                <VChip size="small" variant="tonal" @click="applyQuick('mtd')">Lo que va del mes</VChip>
              </div>

              <VRow>
                <VCol cols="12" sm="6">
                  <AppDateField v-model="form.periodFrom" label="Desde" density="comfortable" :error-messages="errs.periodFrom" />
                </VCol>
                <VCol cols="12" sm="6">
                  <AppDateField v-model="form.periodTo" label="Hasta" density="comfortable" :error-messages="errs.periodTo" />
                </VCol>
                <VCol cols="12">
                  <VSelect
                    v-model="form.type" :items="PAY_METHODS"
                    item-title="label" item-value="value" label="Método de cálculo"
                  />
                </VCol>
              </VRow>
              <p class="text-caption text-medium-emphasis mt-n2 mb-0">
                Para un trabajador que solo trabajó unos días: poné las dos fechas y dejá "Proporcional por días".
              </p>

              <VDivider class="my-3" />
              <VTextField
                v-if="isAdelanto" v-model="form.freeAmount" type="number"
                label="Monto del adelanto (S/)" class="mb-2"
              />
              <div v-else-if="calcLoading" class="text-center py-4"><VProgressCircular indeterminate size="24" color="primary" /></div>
              <div v-else-if="calc" class="text-body-2">
                <div v-if="calc.payableDays != null" class="d-flex justify-space-between"><span class="text-medium-emphasis">Días pagables</span><span>{{ calc.payableDays }}</span></div>
                <div v-else class="d-flex justify-space-between"><span class="text-medium-emphasis">Días trabajados</span><span>{{ calc.daysWorked }}</span></div>
                <div class="d-flex justify-space-between"><span class="text-medium-emphasis">Faltas descontadas</span><span>{{ calc.absencesDeducted }}</span></div>
                <div class="d-flex justify-space-between"><span class="text-medium-emphasis">Monto bruto</span><span>{{ soles(calc.grossAmount) }}</span></div>
                <div class="d-flex justify-space-between"><span class="text-medium-emphasis">Descuento AFP</span><span>− {{ soles(calc.afpDeduction) }}</span></div>
              </div>
              <p v-else class="text-body-2 text-medium-emphasis">Elegí el período para calcular.</p>

              <VRow class="mt-1">
                <VCol cols="12" sm="6"><VTextField v-model="form.otherDeductions" type="number" label="Otros descuentos (S/)" /></VCol>
                <VCol cols="12" sm="6"><VTextField v-model="form.otherDeductionsReason" label="Motivo otros descuentos" /></VCol>
                <VCol cols="12"><VTextField v-model="form.note" label="Nota" /></VCol>
              </VRow>

              <VDivider class="my-2" />
              <div class="d-flex justify-space-between text-h6">
                <span>Neto a depositar</span>
                <strong>{{ soles(netAfterOther) }}</strong>
              </div>
            </div>
          </VExpandTransition>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" :disabled="saving" @click="dialog = false">Cerrar</VBtn>
          <VBtn color="primary" :loading="saving" :disabled="!canSubmit" @click="submit">Registrar pago</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Marcar pagado -->
    <VDialog :model-value="!!payDialog" max-width="420" @update:model-value="payDialog = null">
      <VCard v-if="payDialog">
        <VCardTitle>Marcar como pagado</VCardTitle>
        <VCardText>
          <p class="text-body-2 mb-3">{{ payDialog.workerName }} · {{ soles(payDialog.netAmount) }}</p>
          <AppDateField v-model="payOn" label="Fecha de pago" density="comfortable" class="mb-2" />
          <VTextField v-model="payMethod" label="Método" placeholder="transferencia / efectivo" />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="payDialog = null">Cancelar</VBtn>
          <VBtn color="primary" @click="confirmPay">Confirmar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <WorkerPayrollDialog
      v-if="detailWorker"
      :trabajador-id="detailWorker" :date="summaryDate"
      @close="detailWorker = null"
    />

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>

<style scoped>
.pz-link {
  font: inherit;
  color: rgb(var(--v-theme-primary));
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}
</style>
