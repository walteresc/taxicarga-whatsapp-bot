<script setup>
import { computed } from 'vue'

// Campo de hora unificado: dos selects (hora y minutos) estilo Materio.
// El v-model es un string 'HH:MM' de 24 horas (o '').
const props = defineProps({
  modelValue: { type: String, default: '' },
  label: { type: String, default: '' },
  density: { type: String, default: 'comfortable' },
  variant: { type: String, default: undefined },
  hideDetails: { type: [Boolean, String], default: 'auto' },
  disabled: { type: Boolean, default: false },
  step: { type: Number, default: 5 },
  errorMessages: { type: [String, Array], default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const pad = n => String(n).padStart(2, '0')

const hours = Array.from({ length: 24 }, (_, i) => pad(i))
const minutes = computed(() => {
  const out = []
  for (let m = 0; m < 60; m += props.step) out.push(pad(m))
  return out
})

const parts = computed(() => {
  const [h = '', m = ''] = (props.modelValue || '').split(':')
  return { h, m }
})

const setHour = h => emit('update:modelValue', h ? `${h}:${parts.value.m || '00'}` : '')
const setMinute = m => emit('update:modelValue', `${parts.value.h || '00'}:${m || '00'}`)

const errorText = computed(() => {
  const e = props.errorMessages
  return Array.isArray(e) ? e[0] : e
})
</script>

<template>
  <div>
    <div v-if="label" class="text-body-2 text-medium-emphasis mb-1">{{ label }}</div>
    <div class="d-flex ga-2">
      <VSelect
        :model-value="parts.h"
        :items="hours"
        label="Hora"
        :density="density"
        :variant="variant"
        hide-details
        :disabled="disabled"
        :menu-props="{ maxHeight: 260 }"
        style="max-width: 130px;"
        @update:model-value="setHour"
      />
      <VSelect
        :model-value="parts.m"
        :items="minutes"
        label="Minutos"
        :density="density"
        :variant="variant"
        hide-details
        :disabled="disabled"
        :menu-props="{ maxHeight: 260 }"
        style="max-width: 130px;"
        @update:model-value="setMinute"
      />
    </div>
    <div v-if="errorText" class="text-caption text-error mt-1">{{ errorText }}</div>
  </div>
</template>
