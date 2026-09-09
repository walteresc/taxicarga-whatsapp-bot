<script setup>
import { computed } from 'vue'

// Campo de hora unificado: VAutocomplete estilo Materio con opciones cada
// N minutos (5 por defecto). El v-model es un string 'HH:MM' de 24 horas
// (o ''). Se puede tipear para filtrar (ej. "08" o "8:3").
const props = defineProps({
  modelValue: { type: String, default: '' },
  label: { type: String, default: '' },
  density: { type: String, default: 'comfortable' },
  variant: { type: String, default: undefined },
  hideDetails: { type: [Boolean, String], default: 'auto' },
  clearable: { type: Boolean, default: true },
  disabled: { type: Boolean, default: false },
  step: { type: Number, default: 5 },
  errorMessages: { type: [String, Array], default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const pad = n => String(n).padStart(2, '0')

const items = computed(() => {
  const out = []
  for (let m = 0; m < 24 * 60; m += props.step)
    out.push(`${pad(Math.floor(m / 60))}:${pad(m % 60)}`)
  return out
})
</script>

<template>
  <VAutocomplete
    :model-value="modelValue || null"
    :items="items"
    :label="label"
    :density="density"
    :variant="variant"
    :hide-details="hideDetails"
    :error-messages="errorMessages"
    :disabled="disabled"
    :clearable="clearable"
    prepend-inner-icon="ri-time-line"
    placeholder="--:--"
    auto-select-first
    :menu-props="{ maxHeight: 260 }"
    @update:model-value="v => emit('update:modelValue', v || '')"
  />
</template>
