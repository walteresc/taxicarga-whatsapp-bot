<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { ApiError } from '@/services/apiClient'
import { CONTRACT_TYPES, payrollConfigService } from '@/services/payrollService'

const props = defineProps({
  // fila del directorio de personal: { type, sourceId, name }
  worker: { type: Object, required: true },
})
const emit = defineEmits(['close', 'saved'])

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const errs = ref({})
const existing = ref(null)

const form = reactive({
  contractType: 'planilla',
  amountPerMonth: '',
  amountPerDay: '',
  workdayHours: '8',
  lunchHours: '1',
  afpPct: '10',
  hiredOn: '',
  active: true,
  notes: '',
})

const soles = n => (n == null || n === '' ? '—' : `S/ ${Number(n).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`)

const valorDia = computed(() => {
  if (form.contractType === 'honorarios') return Number(form.amountPerDay) || 0
  return (Number(form.amountPerMonth) || 0) / 30
})
const valorHora = computed(() => {
  const j = Number(form.workdayHours) || 0
  return j ? valorDia.value / j : 0
})

onMounted(async () => {
  try {
    const data = await payrollConfigService.list({
      workerType: props.worker.type, workerId: props.worker.sourceId, pageSize: 1,
    })
    if (data.results.length) {
      const c = data.results[0]
      existing.value = c
      Object.assign(form, {
        contractType: c.contractType,
        amountPerMonth: c.amountPerMonth ?? '',
        amountPerDay: c.amountPerDay ?? '',
        workdayHours: c.workdayHours,
        lunchHours: c.lunchHours,
        afpPct: c.afpPct,
        hiredOn: c.hiredOn || '',
        active: c.active,
        notes: c.notes || '',
      })
    }
  } catch (e) {
    error.value = e.message || 'No se pudo cargar la configuración.'
  } finally {
    loading.value = false
  }
})

const submit = async () => {
  saving.value = true
  errs.value = {}
  const payload = {
    contractType: form.contractType,
    workdayHours: form.workdayHours,
    lunchHours: form.lunchHours,
    afpPct: form.afpPct || 0,
    hiredOn: form.hiredOn,
    active: form.active,
    notes: form.notes,
    amountPerMonth: form.contractType === 'planilla' ? form.amountPerMonth : null,
    amountPerDay: form.contractType === 'honorarios' ? form.amountPerDay : null,
  }
  try {
    if (existing.value) {
      await payrollConfigService.update(existing.value.id, payload)
    } else {
      await payrollConfigService.create({
        ...payload, workerType: props.worker.type, workerId: props.worker.sourceId,
      })
    }
    emit('saved')
    emit('close')
  } catch (e) {
    if (e instanceof ApiError && Object.keys(e.fields).length) errs.value = e.fields
    else error.value = e.message || 'No se pudo guardar.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <VDialog :model-value="true" max-width="560" persistent @update:model-value="$emit('close')">
    <VCard>
      <VCardTitle class="d-flex align-center justify-space-between">
        <span>Planilla · {{ worker.name }}</span>
        <VBtn icon="ri-close-line" variant="text" size="small" @click="$emit('close')" />
      </VCardTitle>
      <VDivider />

      <VCardText>
        <div v-if="loading" class="text-center py-8"><VProgressCircular indeterminate color="primary" /></div>
        <template v-else>
          <VAlert v-if="error" type="error" variant="tonal" density="compact" class="mb-4">{{ error }}</VAlert>

          <VRow>
            <VCol cols="12">
              <VSelect
                v-model="form.contractType"
                :items="CONTRACT_TYPES" item-title="label" item-value="value"
                label="Tipo de contrato" :error-messages="errs.contractType"
              />
            </VCol>
            <VCol v-if="form.contractType === 'planilla'" cols="12" sm="6">
              <VTextField
                v-model="form.amountPerMonth" type="number" label="Sueldo mensual (S/)"
                :error-messages="errs.amountPerMonth"
              />
            </VCol>
            <VCol v-else cols="12" sm="6">
              <VTextField
                v-model="form.amountPerDay" type="number" label="Monto por día (S/)"
                :error-messages="errs.amountPerDay"
              />
            </VCol>
            <VCol cols="12" sm="6">
              <VTextField
                v-model="form.hiredOn" type="date" label="Fecha de ingreso"
                :error-messages="errs.hiredOn"
              />
            </VCol>
            <VCol cols="12" sm="4">
              <VTextField
                v-model="form.workdayHours" type="number" step="0.25" label="Horas de jornada / día"
                :error-messages="errs.workdayHours"
              />
            </VCol>
            <VCol cols="12" sm="4">
              <VTextField
                v-model="form.lunchHours" type="number" step="0.25" label="Horas de refrigerio"
                :error-messages="errs.lunchHours"
              />
            </VCol>
            <VCol cols="12" sm="4">
              <VTextField
                v-model="form.afpPct" type="number" step="0.01" label="% AFP"
                :disabled="form.contractType === 'honorarios'"
                :hint="form.contractType === 'honorarios' ? 'No aplica a honorarios' : ''"
                persistent-hint :error-messages="errs.afpPct"
              />
            </VCol>
            <VCol cols="12">
              <VTextarea v-model="form.notes" label="Observaciones" rows="2" auto-grow :error-messages="errs.notes" />
            </VCol>
            <VCol cols="12"><VSwitch v-model="form.active" label="Activo en planilla" color="primary" /></VCol>
          </VRow>

          <VDivider class="my-2" />
          <div class="d-flex flex-wrap ga-4 text-body-2">
            <span>Valor día: <strong>{{ soles(valorDia) }}</strong></span>
            <span>Valor hora: <strong>{{ soles(valorHora) }}</strong></span>
          </div>
        </template>
      </VCardText>

      <VCardActions>
        <VSpacer />
        <VBtn variant="text" :disabled="saving" @click="$emit('close')">Cancelar</VBtn>
        <VBtn color="primary" :loading="saving" :disabled="loading" @click="submit">Guardar</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
