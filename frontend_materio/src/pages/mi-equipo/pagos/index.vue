<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { ApiError } from '@/services/apiClient'
import WorkerPayrollDialog from '@/components/planilla/WorkerPayrollDialog.vue'
import {
  fetchPayCalc, fetchPayrollSummary, PAYMENT_TYPES, payrollConfigService, paymentsService,
} from '@/services/payrollService'

const TYPE = Object.fromEntries(PAYMENT_TYPES.map(t => [t.value, t.label]))
const soles = n => (n == null ? '—' : `S/ ${Number(n).toLocaleString('es-PE', { minimumFractionDigits: 2 })}`)

const tab = ref('resumen')
const workers = ref([])
const rows = ref([])
const loading = ref(true)
const error = ref('')

// ── Resumen ────────────────────────────────────────────────────────────
const summaryDate = ref(new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Lima' }).format(new Date()))
const summary = ref([])
const summaryLoading = ref(false)
const detailWorker = ref(null)
const loadSummary = async () => {
  summaryLoading.value = true
  try {
    const d = await fetchPayrollSummary(summaryDate.value)
    summary.value = d.rows
  } catch { summary.value = [] } finally { summaryLoading.value = false }
}

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    const data = await paymentsService.list({ pageSize: 100 })
    rows.value = data.results
  } catch (e) {
    error.value = e.message || 'No se pudieron cargar los pagos.'
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
  loadSummary()
})

// ── Nuevo pago ─────────────────────────────────────────────────────────
const dialog = ref(false)
const saving = ref(false)
const errs = ref({})
const calc = ref(null)
const calcLoading = ref(false)
const form = reactive({
  trabajadorId: null, type: 'fin_de_mes', periodFrom: '', periodTo: '',
  otherDeductions: '0', otherDeductionsReason: '', note: '',
})

const monthRange = (type) => {
  const now = new Date()
  const y = now.getFullYear()
  const m = now.getMonth()
  const first = new Date(y, m, 1)
  const last = new Date(y, m + 1, 0)
  const iso = d => new Intl.DateTimeFormat('en-CA').format(d)
  if (type === 'quincena') {
    const day = now.getDate()
    return day <= 15
      ? [iso(first), iso(new Date(y, m, 15))]
      : [iso(new Date(y, m, 16)), iso(last)]
  }
  return [iso(first), iso(last)]
}

const openNew = () => {
  errs.value = {}
  calc.value = null
  const [f, t] = monthRange('fin_de_mes')
  Object.assign(form, {
    trabajadorId: null, type: 'fin_de_mes', periodFrom: f, periodTo: t,
    otherDeductions: '0', otherDeductionsReason: '', note: '',
  })
  dialog.value = true
}

watch(() => form.type, t => {
  const [f, to] = monthRange(t)
  if (t !== 'adelanto') { form.periodFrom = f; form.periodTo = to }
})

let calcTimer
const runCalc = () => {
  clearTimeout(calcTimer)
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

const netAfterOther = computed(() => {
  if (!calc.value) return null
  return Math.max(0, calc.value.netAmount - (Number(form.otherDeductions) || 0))
})

const submit = async () => {
  if (!calc.value) { notify('Elegí trabajador y período.', 'warning'); return }
  saving.value = true
  errs.value = {}
  try {
    await paymentsService.create({
      trabajadorId: form.trabajadorId,
      type: form.type,
      periodFrom: form.periodFrom,
      periodTo: form.periodTo,
      daysWorked: calc.value.daysWorked,
      absencesDeducted: calc.value.absencesDeducted,
      grossAmount: calc.value.grossAmount,
      afpDeduction: calc.value.afpDeduction,
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
          Liquidación de quincenas y fin de mes. El sistema calcula bruto, AFP y neto.
        </p>
      </div>
      <VBtn prepend-icon="ri-add-line" @click="openNew">Nuevo pago</VBtn>
    </div>

    <VTabs v-model="tab" class="mb-4">
      <VTab value="resumen">Resumen</VTab>
      <VTab value="pagos">Pagos registrados</VTab>
    </VTabs>

    <VAlert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</VAlert>

    <!-- Resumen -->
    <template v-if="tab === 'resumen'">
      <VCard>
        <VCardText class="d-flex flex-wrap align-center ga-3">
          <span class="text-body-2 text-medium-emphasis">Estado al</span>
          <VTextField v-model="summaryDate" type="date" density="compact" hide-details style="max-width: 175px;" @update:model-value="loadSummary" />
        </VCardText>
        <VDivider />
        <VTable>
          <thead>
            <tr>
              <th>Trabajador</th><th>Contrato</th>
              <th class="text-right">Saldo horas</th><th class="text-right">Valor saldo</th>
              <th class="text-right">Faltas mes</th><th class="text-right">Sin resolver</th>
              <th class="text-right">Días trab.</th><th class="text-right">Vac. pend.</th>
              <th class="text-right">A pagar (est.)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="summaryLoading"><td colspan="9" class="text-center py-8"><VProgressCircular indeterminate color="primary" /></td></tr>
            <tr v-else-if="!summary.length"><td colspan="9" class="text-center text-medium-emphasis py-10">Sin trabajadores en planilla.</td></tr>
            <tr v-for="s in summary" v-else :key="s.trabajadorId">
              <td>
                <button type="button" class="pz-link" @click="detailWorker = s.trabajadorId">{{ s.workerName }}</button>
              </td>
              <td><VChip size="x-small" variant="tonal">{{ s.contractType === 'planilla' ? 'Planilla' : 'Honorarios' }}</VChip></td>
              <td class="text-right" :class="s.balanceHours > 0 ? 'text-success' : (s.balanceHours < 0 ? 'text-error' : '')">
                {{ (s.balanceHours > 0 ? '+' : '') + s.balanceHours.toFixed(2) }}
              </td>
              <td class="text-right text-medium-emphasis">{{ soles(s.balanceValue) }}</td>
              <td class="text-right">{{ s.absencesMonth }}</td>
              <td class="text-right" :class="s.absencesUnresolved ? 'text-error font-weight-medium' : ''">{{ s.absencesUnresolved }}</td>
              <td class="text-right">{{ s.daysWorkedMonth }}</td>
              <td class="text-right">{{ s.vacationDaysPending ?? '—' }}</td>
              <td class="text-right font-weight-bold">{{ soles(s.estimatedNet) }}</td>
            </tr>
          </tbody>
        </VTable>
      </VCard>
    </template>

    <VCard v-else>
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
          <tr v-else-if="!rows.length"><td colspan="9" class="text-center text-medium-emphasis py-10">Aún no hay pagos registrados.</td></tr>
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

    <!-- Nuevo pago -->
    <VDialog v-model="dialog" max-width="620" persistent>
      <VCard>
        <VCardTitle>Nuevo pago</VCardTitle>
        <VCardText>
          <VRow>
            <VCol cols="12" sm="6">
              <VSelect
                v-model="form.trabajadorId"
                :items="workers.map(w => ({ title: `${w.workerName} (${w.contractType})`, value: w.id }))"
                label="Trabajador" :error-messages="errs.trabajadorId"
              />
            </VCol>
            <VCol cols="12" sm="6">
              <VSelect v-model="form.type" :items="PAYMENT_TYPES" item-title="label" item-value="value" label="Tipo de pago" />
            </VCol>
            <VCol cols="12" sm="6"><VTextField v-model="form.periodFrom" type="date" label="Período desde" :error-messages="errs.periodFrom" /></VCol>
            <VCol cols="12" sm="6"><VTextField v-model="form.periodTo" type="date" label="Período hasta" :error-messages="errs.periodTo" /></VCol>
          </VRow>

          <VDivider class="my-3" />
          <div v-if="calcLoading" class="text-center py-4"><VProgressCircular indeterminate size="24" color="primary" /></div>
          <div v-else-if="calc" class="text-body-2">
            <div class="d-flex justify-space-between"><span class="text-medium-emphasis">Días trabajados</span><span>{{ calc.daysWorked }}</span></div>
            <div class="d-flex justify-space-between"><span class="text-medium-emphasis">Faltas descontadas</span><span>{{ calc.absencesDeducted }}</span></div>
            <div class="d-flex justify-space-between"><span class="text-medium-emphasis">Monto bruto</span><span>{{ soles(calc.grossAmount) }}</span></div>
            <div class="d-flex justify-space-between"><span class="text-medium-emphasis">Descuento AFP</span><span>− {{ soles(calc.afpDeduction) }}</span></div>
          </div>
          <p v-else class="text-body-2 text-medium-emphasis">Elegí trabajador y período para calcular.</p>

          <VRow class="mt-1">
            <VCol cols="12" sm="6"><VTextField v-model="form.otherDeductions" type="number" label="Otros descuentos (S/)" @update:model-value="() => {}" /></VCol>
            <VCol cols="12" sm="6"><VTextField v-model="form.otherDeductionsReason" label="Motivo otros descuentos" /></VCol>
            <VCol cols="12"><VTextField v-model="form.note" label="Nota" /></VCol>
          </VRow>

          <VDivider class="my-2" />
          <div class="d-flex justify-space-between text-h6">
            <span>Neto a depositar</span>
            <strong>{{ soles(netAfterOther) }}</strong>
          </div>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" :disabled="saving" @click="dialog = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="saving" :disabled="!calc" @click="submit">Registrar pago</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Marcar pagado -->
    <VDialog :model-value="!!payDialog" max-width="420" @update:model-value="payDialog = null">
      <VCard v-if="payDialog">
        <VCardTitle>Marcar como pagado</VCardTitle>
        <VCardText>
          <p class="text-body-2 mb-3">{{ payDialog.workerName }} · {{ soles(payDialog.netAmount) }}</p>
          <VTextField v-model="payOn" type="date" label="Fecha de pago" class="mb-2" />
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
