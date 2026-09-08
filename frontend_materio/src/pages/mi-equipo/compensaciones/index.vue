<script setup>
import { computed, onMounted, ref } from 'vue'

import CrudResourcePage from '@/components/crud/CrudResourcePage.vue'
import {
  COMPENSATION_KINDS, compensationsService, fetchPendingAbsences, payrollConfigService,
} from '@/services/payrollService'

const KIND = Object.fromEntries(COMPENSATION_KINDS.map(k => [k.value, k.label]))
const num = n => (n == null ? '—' : Number(n).toFixed(2))

// ── Faltas por resolver ────────────────────────────────────────────────
const pending = ref([])
const loadingPending = ref(true)
const busyId = ref(null)
const crudRef = ref(null)

const loadPending = async () => {
  loadingPending.value = true
  try {
    pending.value = await fetchPendingAbsences({})
  } catch { pending.value = [] } finally { loadingPending.value = false }
}
onMounted(loadPending)

const compensate = async row => {
  busyId.value = row.attendanceId
  try {
    await compensationsService.create({
      trabajadorId: row.trabajadorId, kind: 'falta_compensada', attendanceId: row.attendanceId,
    })
    await loadPending()
    crudRef.value?.load?.()
  } catch (e) {
    // el CrudResourcePage tiene su propio snackbar; acá uno simple
    alert(e.message || 'No se pudo compensar.')
  } finally {
    busyId.value = null
  }
}

// ── CRUD de movimientos ────────────────────────────────────────────────
const workerOptions = ref([])
onMounted(async () => {
  try {
    const data = await payrollConfigService.list({ pageSize: 500, status: 'active' })
    workerOptions.value = data.results.map(c => ({ title: `${c.workerName}`, value: c.id }))
  } catch { /* */ }
})

const columns = [
  { key: 'date', label: 'Fecha' },
  { key: 'workerName', label: 'Trabajador' },
  { key: 'kind', label: 'Tipo', format: r => KIND[r.kind] || r.kind },
  { key: 'hours', label: 'Horas', align: 'end', format: r => `${r.hours > 0 ? '+' : ''}${num(r.hours)}` },
  { key: 'reason', label: 'Motivo', format: r => r.reason || '—' },
]
const fields = computed(() => [
  { key: 'trabajadorId', label: 'Trabajador', type: 'select', options: workerOptions.value, required: true, cols: 12 },
  { key: 'date', label: 'Fecha', type: 'date', required: true, cols: 6 },
  { key: 'kind', label: 'Tipo', type: 'select', options: COMPENSATION_KINDS.filter(k => k.value !== 'falta_compensada').map(k => ({ title: k.label, value: k.value })), required: true, cols: 6 },
  { key: 'hours', label: 'Horas (+ suma al saldo, − consume)', type: 'text', required: true, cols: 6 },
  { key: 'reason', label: 'Motivo', type: 'text', cols: 12 },
])
</script>

<template>
  <section>
    <div class="mb-6">
      <h1 class="text-h4 font-weight-bold mb-1">Compensaciones</h1>
      <p class="text-body-1 text-medium-emphasis mb-0">
        Ajustes al saldo de horas: compensar faltas, días libres, pago o reposición de horas.
      </p>
    </div>

    <VCard class="mb-6">
      <VCardItem>
        <VCardTitle>Faltas por resolver</VCardTitle>
        <template #append>
          <VBtn size="small" variant="text" icon="ri-refresh-line" @click="loadPending" />
        </template>
      </VCardItem>
      <VDivider />
      <div v-if="loadingPending" class="text-center py-6"><VProgressCircular indeterminate color="primary" size="28" /></div>
      <VTable v-else-if="pending.length">
        <thead>
          <tr><th>Fecha</th><th>Trabajador</th><th class="text-right">Jornada</th><th class="text-right">Saldo a la fecha</th><th class="text-right">Acción</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in pending" :key="row.attendanceId">
            <td>{{ row.date }}</td>
            <td class="font-weight-medium">{{ row.workerName }}</td>
            <td class="text-right">{{ num(row.workdayHours) }} h</td>
            <td class="text-right" :class="row.compensable ? 'text-success' : 'text-error'">
              {{ (row.balanceAtDate > 0 ? '+' : '') + num(row.balanceAtDate) }} h
            </td>
            <td class="text-right">
              <VBtn
                size="small" color="primary" variant="tonal"
                :disabled="!row.compensable" :loading="busyId === row.attendanceId"
                @click="compensate(row)"
              >
                Compensar con horas
              </VBtn>
              <div v-if="!row.compensable" class="text-caption text-medium-emphasis">
                Sin saldo → se descuenta 1 día
              </div>
            </td>
          </tr>
        </tbody>
      </VTable>
      <p v-else class="text-body-2 text-medium-emphasis pa-4 mb-0">No hay faltas pendientes de resolver.</p>
    </VCard>

    <CrudResourcePage
      ref="crudRef"
      hide-header singular="movimiento" :service="compensationsService"
      :columns="columns" :fields="fields"
      search-label="Buscar por trabajador o motivo" label-field="workerName"
      toggle-field="" :deletable="true"
      @changed="loadPending"
    />
  </section>
</template>
