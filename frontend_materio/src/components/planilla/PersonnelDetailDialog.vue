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
const dash = v => (v === '' || v == null ? '—' : v)

const loading = ref(true)
const record = ref(null)
const config = ref(null)
const payroll = ref(null)

const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Lima' }).format(new Date())

const balanceClass = computed(() => {
  const b = payroll.value?.balanceHours
  return b > 0 ? 'text-success' : (b < 0 ? 'text-error' : '')
})

const personalFields = computed(() => {
  const f = [
    { label: 'Tipo', value: TYPE[props.worker.type]?.label || props.worker.type },
    { label: 'Documento', value: dash(props.worker.documentId) },
    { label: 'Teléfono', value: dash(props.worker.phone) },
  ]
  if (props.worker.detail) f.push({ label: 'Detalle', value: props.worker.detail })
  if (record.value && props.worker.type === 'conductor') {
    f.push(
      { label: 'N° de licencia', value: dash(record.value.licenseNumber) },
      { label: 'Categoría', value: dash(record.value.licenseCategory) },
      { label: 'Vencimiento de licencia', value: dash(record.value.licenseExpiresOn) },
    )
  }
  return f
})

const payrollFields = computed(() => {
  const c = config.value
  if (!c) return []
  const f = [{ label: 'Contrato', value: CONTRACT[c.contractType] || c.contractType }]
  if (c.contractType === 'planilla') {
    f.push({ label: 'Sueldo mensual', value: soles(c.amountPerMonth) })
    f.push({ label: 'AFP', value: `${c.afpPct} %` })
  } else {
    f.push({ label: 'Monto por día', value: soles(c.amountPerDay) })
  }
  f.push(
    { label: 'Jornada', value: `${c.workdayHours} h` },
    { label: 'Refrigerio', value: `${c.lunchHours} h` },
    { label: 'Ingreso', value: c.hiredOn },
  )
  if (c.endedOn) f.push({ label: 'Cese', value: c.endedOn })
  return f
})
</script>

<template>
  <VDialog :model-value="true" max-width="820" scrollable @update:model-value="$emit('close')">
    <VCard>
      <div class="pdd-head d-flex align-center ga-3 pa-5">
        <VAvatar :color="TYPE[worker.type]?.color" variant="tonal" size="48">
          <VIcon :icon="TYPE[worker.type]?.icon" size="24" />
        </VAvatar>
        <div class="flex-grow-1">
          <div class="d-flex align-center flex-wrap ga-2">
            <span class="text-h6">{{ worker.name }}</span>
            <VChip size="x-small" :color="worker.active ? 'success' : 'secondary'" label>
              {{ worker.active ? 'Activo' : 'Inactivo' }}
            </VChip>
          </div>
          <div class="text-body-2 text-medium-emphasis">
            {{ TYPE[worker.type]?.label }}<template v-if="worker.documentId"> · DNI {{ worker.documentId }}</template>
          </div>
        </div>
        <VBtn icon="ri-close-line" variant="text" size="small" @click="$emit('close')" />
      </div>
      <VDivider />

      <VCardText class="pa-5">
        <div v-if="loading" class="text-center py-10"><VProgressCircular indeterminate color="primary" /></div>

        <template v-else>
          <!-- Datos personales -->
          <section class="mb-6">
            <div class="d-flex align-center justify-space-between mb-3">
              <h3 class="text-subtitle-1 font-weight-bold">Datos personales</h3>
              <VBtn
                v-if="worker.type !== 'asesor'" size="small" variant="tonal"
                prepend-icon="ri-edit-line" @click="$emit('edit', worker)"
              >
                Editar
              </VBtn>
            </div>
            <div class="pdd-grid">
              <div v-for="f in personalFields" :key="f.label" class="pdd-cell">
                <div class="pdd-cell__label">{{ f.label }}</div>
                <div class="pdd-cell__value">{{ f.value }}</div>
              </div>
            </div>
          </section>

          <!-- Planilla -->
          <section>
            <div class="d-flex align-center justify-space-between mb-3">
              <h3 class="text-subtitle-1 font-weight-bold">Planilla</h3>
              <VBtn
                size="small" variant="tonal" prepend-icon="ri-money-dollar-circle-line"
                @click="$emit('edit-payroll', worker)"
              >
                {{ config ? 'Editar' : 'Configurar' }}
              </VBtn>
            </div>

            <VAlert v-if="!config" type="info" variant="tonal" density="compact">
              Este trabajador no tiene configuración de planilla.
            </VAlert>

            <template v-else>
              <!-- métricas destacadas -->
              <div class="pdd-stats mb-4">
                <div class="pdd-stat">
                  <div class="pdd-stat__label">Saldo de horas extra</div>
                  <div class="pdd-stat__value" :class="balanceClass">
                    {{ payroll ? hLabel(payroll.balanceHours) : '—' }}
                  </div>
                  <div class="pdd-stat__hint">al {{ today }}</div>
                </div>
                <div class="pdd-stat">
                  <div class="pdd-stat__label">Valor día</div>
                  <div class="pdd-stat__value">{{ soles(config.valorDia) }}</div>
                </div>
                <div class="pdd-stat">
                  <div class="pdd-stat__label">Valor hora</div>
                  <div class="pdd-stat__value">{{ soles(config.valorHora) }}</div>
                </div>
                <div v-if="payroll && payroll.vacations?.aplica" class="pdd-stat">
                  <div class="pdd-stat__label">Vacaciones pendientes</div>
                  <div class="pdd-stat__value">{{ payroll.vacations.daysPending }} d</div>
                  <div class="pdd-stat__hint">liquidación {{ soles(payroll.vacations.liquidationAmount) }}</div>
                </div>
              </div>

              <div class="pdd-grid mb-2">
                <div v-for="f in payrollFields" :key="f.label" class="pdd-cell">
                  <div class="pdd-cell__label">{{ f.label }}</div>
                  <div class="pdd-cell__value">{{ f.value }}</div>
                </div>
              </div>

              <VExpansionPanels v-if="payroll" variant="accordion" class="mt-4">
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
          </section>
        </template>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<style scoped>
.pdd-head {
  background: rgba(var(--v-theme-on-surface), 0.02);
}

.pdd-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 16px 24px;
}
.pdd-cell__label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(var(--v-theme-on-surface), 0.6);
  margin-bottom: 2px;
}
.pdd-cell__value {
  font-size: 0.95rem;
}

.pdd-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}
.pdd-stat {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  padding: 12px 14px;
}
.pdd-stat__label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.pdd-stat__value {
  font-size: 1.35rem;
  font-weight: 700;
  line-height: 1.4;
}
.pdd-stat__hint {
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), 0.55);
}
</style>
