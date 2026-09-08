<script setup>
import { onMounted, reactive, ref } from 'vue'

import {
  COMPENSATION_KINDS, DAY_TYPES, fetchWorkerPayroll, openingBalanceService,
} from '@/services/payrollService'

const props = defineProps({
  trabajadorId: { type: [Number, String], required: true },
  date: { type: String, default: '' },
})
defineEmits(['close'])

const DAY = Object.fromEntries(DAY_TYPES.map(d => [d.value, d.label]))
const KIND = Object.fromEntries(COMPENSATION_KINDS.map(k => [k.value, k.label]))
const soles = n => (n == null ? '—' : `S/ ${Number(n).toLocaleString('es-PE', { minimumFractionDigits: 2 })}`)
const h = n => (n == null ? '—' : `${n > 0 ? '+' : ''}${Number(n).toFixed(2)} h`)

const data = ref(null)
const loading = ref(true)
const error = ref('')

const refDate = props.date || new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Lima' }).format(new Date())

const load = async () => {
  loading.value = true
  try {
    data.value = await fetchWorkerPayroll(props.trabajadorId, refDate)
  } catch (e) {
    error.value = e.message || 'No se pudo cargar el detalle.'
  } finally {
    loading.value = false
  }
}
onMounted(load)

// ── Editar apertura del saldo del mes ──────────────────────────────────
const ob = reactive({ open: false, year: new Date(refDate).getFullYear(), month: new Date(refDate).getMonth() + 1, hours: '0', saving: false })
const saveOpening = async () => {
  ob.saving = true
  try {
    await openingBalanceService.create({
      trabajadorId: props.trabajadorId, year: ob.year, month: ob.month, openingHours: ob.hours,
    })
    ob.open = false
    await load()
  } catch (e) {
    error.value = e.message || 'No se pudo guardar la apertura.'
  } finally {
    ob.saving = false
  }
}
</script>

<template>
  <VDialog :model-value="true" max-width="760" scrollable @update:model-value="$emit('close')">
    <VCard>
      <VCardTitle class="d-flex align-center justify-space-between">
        <span>{{ data?.worker?.name || 'Trabajador' }}</span>
        <VBtn icon="ri-close-line" variant="text" size="small" @click="$emit('close')" />
      </VCardTitle>
      <VDivider />

      <VCardText>
        <VAlert v-if="error" type="error" variant="tonal" density="compact" class="mb-3">{{ error }}</VAlert>
        <div v-if="loading" class="text-center py-8"><VProgressCircular indeterminate color="primary" /></div>

        <template v-else-if="data">
          <div class="d-flex flex-wrap ga-2 mb-4">
            <VChip size="small" variant="tonal">{{ data.worker.contractType === 'planilla' ? 'Planilla' : 'Honorarios' }}</VChip>
            <VChip size="small" variant="tonal">Jornada {{ data.worker.workdayHours }} h</VChip>
            <VChip size="small" variant="tonal">Ingreso {{ data.worker.hiredOn }}</VChip>
            <VChip size="small" variant="tonal">Valor día {{ soles(data.worker.valorDia) }}</VChip>
            <VChip size="small" variant="tonal">Valor hora {{ soles(data.worker.valorHora) }}</VChip>
          </div>

          <VRow class="mb-2">
            <VCol cols="12" sm="6">
              <div class="text-overline text-medium-emphasis">Saldo de horas (al {{ refDate }})</div>
              <div class="text-h5 font-weight-bold" :class="data.balanceHours > 0 ? 'text-success' : (data.balanceHours < 0 ? 'text-error' : '')">
                {{ h(data.balanceHours) }}
              </div>
              <VBtn size="x-small" variant="text" prepend-icon="ri-edit-line" @click="ob.open = !ob.open">
                Editar apertura del mes
              </VBtn>
              <div v-if="ob.open" class="d-flex flex-wrap align-center ga-2 mt-1">
                <VTextField v-model.number="ob.year" type="number" label="Año" density="compact" hide-details style="max-width: 90px;" />
                <VTextField v-model.number="ob.month" type="number" label="Mes" density="compact" hide-details style="max-width: 80px;" />
                <VTextField v-model="ob.hours" type="number" label="Horas apertura" density="compact" hide-details style="max-width: 140px;" />
                <VBtn size="small" :loading="ob.saving" @click="saveOpening">Guardar</VBtn>
              </div>
            </VCol>
            <VCol v-if="data.vacations.aplica" cols="12" sm="6">
              <div class="text-overline text-medium-emphasis">Vacaciones</div>
              <div class="text-body-2">
                Ganadas {{ data.vacations.daysEarned }} · Tomadas {{ data.vacations.daysTaken }} ·
                <strong>Pendientes {{ data.vacations.daysPending }}</strong>
              </div>
              <div class="text-body-2 text-medium-emphasis">
                Truncas año en curso: {{ data.vacations.daysAccruedCurrentYear.toFixed(2) }} d ·
                Liquidación: <strong>{{ soles(data.vacations.liquidationAmount) }}</strong>
              </div>
            </VCol>
          </VRow>

          <VExpansionPanels variant="accordion" class="mt-2">
            <VExpansionPanel title="Asistencia reciente">
              <template #text>
                <VTable density="compact">
                  <thead><tr><th>Fecha</th><th>Tipo</th><th>Ingreso</th><th>Salida</th><th class="text-right">Δ</th></tr></thead>
                  <tbody>
                    <tr v-for="a in data.recentAttendance" :key="a.date">
                      <td>{{ a.date }}</td><td>{{ DAY[a.dayType] || a.dayType }}</td>
                      <td>{{ a.clockIn || '—' }}</td><td>{{ a.clockOut || '—' }}</td>
                      <td class="text-right" :class="a.delta > 0 ? 'text-success' : (a.delta < 0 ? 'text-error' : '')">{{ h(a.delta) }}</td>
                    </tr>
                  </tbody>
                </VTable>
              </template>
            </VExpansionPanel>
            <VExpansionPanel :title="`Compensaciones (${data.compensations.length})`">
              <template #text>
                <VTable v-if="data.compensations.length" density="compact">
                  <thead><tr><th>Fecha</th><th>Tipo</th><th class="text-right">Horas</th><th>Motivo</th></tr></thead>
                  <tbody>
                    <tr v-for="(c, i) in data.compensations" :key="i">
                      <td>{{ c.date }}</td><td>{{ KIND[c.kind] || c.kind }}</td>
                      <td class="text-right">{{ h(c.hours) }}</td><td>{{ c.reason || '—' }}</td>
                    </tr>
                  </tbody>
                </VTable>
                <p v-else class="text-body-2 text-medium-emphasis mb-0">Sin movimientos.</p>
              </template>
            </VExpansionPanel>
            <VExpansionPanel :title="`Pagos (${data.payments.length})`">
              <template #text>
                <VTable v-if="data.payments.length" density="compact">
                  <thead><tr><th>Período</th><th>Tipo</th><th class="text-right">Neto</th><th>Estado</th></tr></thead>
                  <tbody>
                    <tr v-for="(p, i) in data.payments" :key="i">
                      <td>{{ p.periodFrom }} → {{ p.periodTo }}</td><td>{{ p.type }}</td>
                      <td class="text-right">{{ soles(p.netAmount) }}</td>
                      <td>{{ p.paid ? `Pagado ${p.paidOn || ''}` : 'Pendiente' }}</td>
                    </tr>
                  </tbody>
                </VTable>
                <p v-else class="text-body-2 text-medium-emphasis mb-0">Sin pagos.</p>
              </template>
            </VExpansionPanel>
          </VExpansionPanels>
        </template>
      </VCardText>
    </VCard>
  </VDialog>
</template>
