<script setup>
import { computed, onMounted, ref } from 'vue'

import { assistantsService, driversService } from '@/services/personnelService'
import {
  COMPENSATION_KINDS, CONTRACT_TYPES, DAY_TYPES, fetchWorkerPayroll, payrollConfigService,
} from '@/services/payrollService'

const props = defineProps({
  // fila del directorio de personal: { type, sourceId, name, documentId, phone, detail, active }
  worker: { type: Object, required: true },
})
const emit = defineEmits(['close', 'edit', 'edit-payroll'])

const TYPE = {
  conductor: { label: 'Conductor', color: 'primary', icon: 'ri-steering-line' },
  ayudante: { label: 'Ayudante', color: 'info', icon: 'ri-user-2-line' },
  asesor: { label: 'Asesor', color: 'success', icon: 'ri-briefcase-line' },
}
const CONTRACT = Object.fromEntries(CONTRACT_TYPES.map(c => [c.value, c.label]))
const DAY = Object.fromEntries(DAY_TYPES.map(d => [d.value, d.label]))
const KIND = Object.fromEntries(COMPENSATION_KINDS.map(k => [k.value, k.label]))
const soles = n => (n == null ? '—' : `S/ ${Number(n).toLocaleString('es-PE', { minimumFractionDigits: 2 })}`)
const hLabel = n => (n == null ? '—' : `${n > 0 ? '+' : ''}${Number(n).toFixed(2)} h`)

const loading = ref(true)
const record = ref(null)
const config = ref(null)
const payroll = ref(null)

const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Lima' }).format(new Date())

const balanceClass = computed(() => {
  const b = payroll.value?.balanceHours
  return b > 0 ? 'text-success' : (b < 0 ? 'text-error' : '')
})

onMounted(async () => {
  const jobs = []
  if (props.worker.type !== 'asesor') {
    const svc = props.worker.type === 'conductor' ? driversService : assistantsService
    jobs.push(svc.get(props.worker.sourceId).then(r => { record.value = r }).catch(() => {}))
  }
  jobs.push(
    payrollConfigService.list({
      workerType: props.worker.type, workerId: props.worker.sourceId, pageSize: 1,
    }).then(async d => {
      if (d.results.length) {
        config.value = d.results[0]
        payroll.value = await fetchWorkerPayroll(config.value.id, today).catch(() => null)
      }
    }).catch(() => {}),
  )
  await Promise.all(jobs)
  loading.value = false
})
</script>

<template>
  <VDialog :model-value="true" max-width="780" scrollable @update:model-value="$emit('close')">
    <VCard>
      <VCardTitle class="d-flex align-center justify-space-between pt-4">
        <div class="d-flex align-center ga-2">
          <VIcon :icon="TYPE[worker.type]?.icon" :color="TYPE[worker.type]?.color" />
          <span>{{ worker.name }}</span>
          <VChip size="x-small" :color="worker.active ? 'success' : 'secondary'">
            {{ worker.active ? 'Activo' : 'Inactivo' }}
          </VChip>
        </div>
        <VBtn icon="ri-close-line" variant="text" size="small" @click="$emit('close')" />
      </VCardTitle>
      <VDivider />

      <VCardText>
        <div v-if="loading" class="text-center py-8"><VProgressCircular indeterminate color="primary" /></div>

        <template v-else>
          <!-- Datos personales -->
          <div class="text-overline text-medium-emphasis mb-2">Datos</div>
          <VRow dense class="mb-2">
            <VCol cols="12" sm="6" md="4">
              <div class="text-caption text-medium-emphasis">Tipo</div>
              <div>{{ TYPE[worker.type]?.label || worker.type }}</div>
            </VCol>
            <VCol cols="12" sm="6" md="4">
              <div class="text-caption text-medium-emphasis">Documento</div>
              <div>{{ worker.documentId || '—' }}</div>
            </VCol>
            <VCol cols="12" sm="6" md="4">
              <div class="text-caption text-medium-emphasis">Teléfono</div>
              <div>{{ worker.phone || '—' }}</div>
            </VCol>
            <VCol v-if="worker.detail" cols="12" sm="6" md="4">
              <div class="text-caption text-medium-emphasis">Detalle</div>
              <div>{{ worker.detail }}</div>
            </VCol>
            <template v-if="record && worker.type === 'conductor'">
              <VCol cols="12" sm="6" md="4">
                <div class="text-caption text-medium-emphasis">N° de licencia</div>
                <div>{{ record.licenseNumber || '—' }}</div>
              </VCol>
              <VCol cols="12" sm="6" md="4">
                <div class="text-caption text-medium-emphasis">Categoría</div>
                <div>{{ record.licenseCategory || '—' }}</div>
              </VCol>
              <VCol cols="12" sm="6" md="4">
                <div class="text-caption text-medium-emphasis">Vencimiento de licencia</div>
                <div>{{ record.licenseExpiresOn || '—' }}</div>
              </VCol>
            </template>
          </VRow>

          <div v-if="worker.type !== 'asesor'" class="mb-4">
            <VBtn size="small" variant="text" prepend-icon="ri-edit-line" @click="$emit('edit', worker)">
              Editar datos
            </VBtn>
          </div>

          <VDivider class="mb-4" />

          <!-- Planilla -->
          <div class="d-flex align-center justify-space-between mb-2">
            <span class="text-overline text-medium-emphasis">Planilla</span>
            <VBtn size="small" variant="text" prepend-icon="ri-money-dollar-circle-line" @click="$emit('edit-payroll', worker)">
              {{ config ? 'Editar planilla' : 'Configurar planilla' }}
            </VBtn>
          </div>

          <p v-if="!config" class="text-body-2 text-medium-emphasis">
            Este trabajador no tiene configuración de planilla.
          </p>

          <template v-else>
            <div class="d-flex flex-wrap ga-2 mb-3">
              <VChip size="small" variant="tonal">{{ CONTRACT[config.contractType] || config.contractType }}</VChip>
              <VChip v-if="config.contractType === 'planilla'" size="small" variant="tonal">
                Sueldo {{ soles(config.amountPerMonth) }}
              </VChip>
              <VChip v-else size="small" variant="tonal">Día {{ soles(config.amountPerDay) }}</VChip>
              <VChip size="small" variant="tonal">Jornada {{ config.workdayHours }} h</VChip>
              <VChip size="small" variant="tonal">Refrigerio {{ config.lunchHours }} h</VChip>
              <VChip v-if="config.contractType === 'planilla'" size="small" variant="tonal">AFP {{ config.afpPct }}%</VChip>
              <VChip size="small" variant="tonal">Ingreso {{ config.hiredOn }}</VChip>
              <VChip v-if="config.endedOn" size="small" variant="tonal" color="warning">Cese {{ config.endedOn }}</VChip>
              <VChip size="small" variant="tonal">Valor día {{ soles(config.valorDia) }}</VChip>
              <VChip size="small" variant="tonal">Valor hora {{ soles(config.valorHora) }}</VChip>
            </div>

            <VRow v-if="payroll" class="mb-1">
              <VCol cols="12" sm="6">
                <div class="text-caption text-medium-emphasis">Saldo de horas extra (al {{ today }})</div>
                <div class="text-h5 font-weight-bold" :class="balanceClass">{{ hLabel(payroll.balanceHours) }}</div>
              </VCol>
              <VCol v-if="payroll.vacations?.aplica" cols="12" sm="6">
                <div class="text-caption text-medium-emphasis">Vacaciones</div>
                <div class="text-body-2">
                  Ganadas {{ payroll.vacations.daysEarned }} · Tomadas {{ payroll.vacations.daysTaken }} ·
                  <strong>Pendientes {{ payroll.vacations.daysPending }}</strong>
                </div>
                <div class="text-body-2 text-medium-emphasis">
                  Liquidación estimada: <strong>{{ soles(payroll.vacations.liquidationAmount) }}</strong>
                </div>
              </VCol>
            </VRow>

            <VExpansionPanels v-if="payroll" variant="accordion" class="mt-2">
              <VExpansionPanel :title="`Asistencia reciente (${payroll.recentAttendance.length})`">
                <template #text>
                  <VTable v-if="payroll.recentAttendance.length" density="compact">
                    <thead><tr><th>Fecha</th><th>Tipo</th><th>Ingreso</th><th>Salida</th><th class="text-right">Δ</th></tr></thead>
                    <tbody>
                      <tr v-for="a in payroll.recentAttendance" :key="a.date">
                        <td>{{ a.date }}</td><td>{{ DAY[a.dayType] || a.dayType }}</td>
                        <td>{{ a.clockIn || '—' }}</td><td>{{ a.clockOut || '—' }}</td>
                        <td class="text-right" :class="a.delta > 0 ? 'text-success' : (a.delta < 0 ? 'text-error' : '')">{{ hLabel(a.delta) }}</td>
                      </tr>
                    </tbody>
                  </VTable>
                  <p v-else class="text-body-2 text-medium-emphasis mb-0">Sin registros.</p>
                </template>
              </VExpansionPanel>
              <VExpansionPanel :title="`Compensaciones (${payroll.compensations.length})`">
                <template #text>
                  <VTable v-if="payroll.compensations.length" density="compact">
                    <thead><tr><th>Fecha</th><th>Tipo</th><th class="text-right">Horas</th><th>Motivo</th></tr></thead>
                    <tbody>
                      <tr v-for="(c, i) in payroll.compensations" :key="i">
                        <td>{{ c.date }}</td><td>{{ KIND[c.kind] || c.kind }}</td>
                        <td class="text-right">{{ hLabel(c.hours) }}</td><td>{{ c.reason || '—' }}</td>
                      </tr>
                    </tbody>
                  </VTable>
                  <p v-else class="text-body-2 text-medium-emphasis mb-0">Sin movimientos.</p>
                </template>
              </VExpansionPanel>
              <VExpansionPanel :title="`Pagos (${payroll.payments.length})`">
                <template #text>
                  <VTable v-if="payroll.payments.length" density="compact">
                    <thead><tr><th>Período</th><th>Tipo</th><th class="text-right">Neto</th><th>Estado</th></tr></thead>
                    <tbody>
                      <tr v-for="(p, i) in payroll.payments" :key="i">
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
        </template>
      </VCardText>
    </VCard>
  </VDialog>
</template>
