<script setup>
import { onMounted, reactive, ref } from 'vue'

import { DAY_TYPES, fetchPayrollDay, savePayrollDay } from '@/services/payrollService'

const CONTRACT = { planilla: 'Planilla', honorarios: 'Honorarios' }

const date = ref(new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Lima' }).format(new Date()))
const rows = ref([])
const loading = ref(true)
const error = ref('')

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

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

onMounted(load)

const shiftDay = n => {
  const d = new Date(`${date.value}T12:00:00`)
  d.setDate(d.getDate() + n)
  date.value = new Intl.DateTimeFormat('en-CA').format(d)
  load()
}
const today = () => {
  date.value = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Lima' }).format(new Date())
  load()
}

const num = n => (n == null ? '—' : Number(n).toFixed(2))
const deltaColor = d => (d == null ? '' : (d > 0 ? 'text-success' : (d < 0 ? 'text-error' : '')))

const saving = ref(null) // trabajadorId en curso

const save = async (row, { clear = false } = {}) => {
  saving.value = row.trabajadorId
  try {
    const body = clear
      ? { trabajadorId: row.trabajadorId, fecha: date.value, clear: true }
      : {
        trabajadorId: row.trabajadorId, fecha: date.value,
        dayType: row.dayType || 'trabajado',
        clockIn: row.clockIn || null,
        clockOut: row.clockOut || null,
        note: row.note || '',
      }
    await savePayrollDay(body)
    await load()
  } catch (e) {
    notify(e.message || 'No se pudo guardar.', 'error')
  } finally {
    saving.value = null
  }
}

// al elegir un tipo que no es "trabajado", limpiar horas
const onDayType = row => {
  if (row.dayType && row.dayType !== 'trabajado') {
    row.clockIn = null
    row.clockOut = null
  }
  save(row)
}
</script>

<template>
  <section>
    <div class="d-flex flex-wrap align-center justify-space-between ga-4 mb-4">
      <div>
        <h1 class="text-h4 font-weight-bold mb-1">Horas extras</h1>
        <p class="text-body-1 text-medium-emphasis mb-0">
          Ingreso y salida de cada trabajador por día. El Δ y el acumulado del mes se calculan solos.
        </p>
      </div>
      <div class="d-flex align-center ga-1">
        <VBtn icon="ri-arrow-left-s-line" variant="tonal" @click="shiftDay(-1)" />
        <VTextField v-model="date" type="date" density="compact" hide-details style="max-width: 175px;" @update:model-value="load" />
        <VBtn icon="ri-arrow-right-s-line" variant="tonal" @click="shiftDay(1)" />
        <VBtn variant="text" @click="today">Hoy</VBtn>
      </div>
    </div>

    <VAlert v-if="error" type="error" variant="tonal" class="mb-4">
      {{ error }}
      <template #append><VBtn size="small" variant="text" @click="load">Reintentar</VBtn></template>
    </VAlert>

    <VCard>
      <VTable>
        <thead>
          <tr>
            <th>Trabajador</th>
            <th style="min-width: 170px;">Tipo de día</th>
            <th style="width: 130px;">Ingreso</th>
            <th style="width: 130px;">Salida</th>
            <th class="text-right">Horas trab.</th>
            <th class="text-right">Δ del día</th>
            <th class="text-right">Saldo horas</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="8" class="text-center py-8"><VProgressCircular indeterminate color="primary" /></td></tr>
          <tr v-else-if="!rows.length"><td colspan="8" class="text-center text-medium-emphasis py-10">
            No hay trabajadores con configuración de planilla. Configuralos en Personal.
          </td></tr>
          <tr v-for="row in rows" v-else :key="row.trabajadorId">
            <td>
              <div class="font-weight-medium">{{ row.workerName }}</div>
              <VChip size="x-small" variant="tonal">{{ CONTRACT[row.contractType] }} · {{ num(row.workdayHours) }}h</VChip>
            </td>
            <td>
              <VSelect
                v-model="row.dayType" :items="DAY_TYPES" item-title="label" item-value="value"
                density="compact" hide-details placeholder="—" clearable
                :loading="saving === row.trabajadorId"
                @update:model-value="onDayType(row)"
              />
            </td>
            <td>
              <VTextField
                v-model="row.clockIn" type="time" density="compact" hide-details
                :disabled="!!row.dayType && row.dayType !== 'trabajado'"
                @change="save(row)"
              />
            </td>
            <td>
              <VTextField
                v-model="row.clockOut" type="time" density="compact" hide-details
                :disabled="!!row.dayType && row.dayType !== 'trabajado'"
                @change="save(row)"
              />
            </td>
            <td class="text-right">{{ num(row.workedHours) }}</td>
            <td class="text-right" :class="deltaColor(row.delta)">
              {{ row.delta == null ? '—' : (row.delta > 0 ? '+' : '') + num(row.delta) }}
            </td>
            <td class="text-right font-weight-medium" :class="deltaColor(row.balanceHours)">
              {{ (row.balanceHours > 0 ? '+' : '') + num(row.balanceHours) }}
            </td>
            <td class="text-right">
              <VBtn
                v-if="row.attendanceId" icon="ri-eraser-line" size="small" variant="text"
                title="Borrar el registro del día" @click="save(row, { clear: true })"
              />
            </td>
          </tr>
        </tbody>
      </VTable>
    </VCard>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
