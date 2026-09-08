<script setup>
import { computed, ref } from 'vue'

// Campo de fecha unificado para todo el CRM: VTextField estilo Materio +
// calendario Vuetify en un menú. El v-model sigue siendo un string
// 'YYYY-MM-DD' (o '') como el resto del código espera.
const props = defineProps({
  modelValue: { type: String, default: '' },
  label: { type: String, default: '' },
  density: { type: String, default: 'compact' },
  variant: { type: String, default: undefined },
  hideDetails: { type: [Boolean, String], default: 'auto' },
  clearable: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  hint: { type: String, default: undefined },
  persistentHint: { type: Boolean, default: false },
  errorMessages: { type: [String, Array], default: () => [] },
  min: { type: String, default: undefined },
  max: { type: String, default: undefined },
})
const emit = defineEmits(['update:modelValue'])

const menu = ref(false)

const asDate = computed(() => {
  const v = props.modelValue
  if (!v) return null
  const [y, m, d] = v.split('-').map(Number)
  if (!y || !m || !d) return null
  return new Date(y, m - 1, d)
})

const pad = n => String(n).padStart(2, '0')
const toIso = dt => {
  const d = Array.isArray(dt) ? dt[0] : dt
  if (!d) return ''
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const display = computed(() =>
  asDate.value ? new Intl.DateTimeFormat('es-PE').format(asDate.value) : '')

const pick = val => {
  emit('update:modelValue', toIso(val))
  menu.value = false
}
</script>

<template>
  <VMenu v-model="menu" :close-on-content-click="false" location="bottom start" min-width="0">
    <template #activator="{ props: activator }">
      <VTextField
        v-bind="activator"
        :model-value="display"
        :label="label"
        :density="density"
        :variant="variant"
        :hide-details="hideDetails"
        :error-messages="errorMessages"
        :disabled="disabled"
        :clearable="clearable"
        :hint="hint"
        :persistent-hint="persistentHint"
        readonly
        prepend-inner-icon="ri-calendar-line"
        placeholder="dd/mm/aaaa"
        @click:clear="emit('update:modelValue', '')"
      />
    </template>
    <VDatePicker
      :model-value="asDate"
      :min="min"
      :max="max"
      show-adjacent-months
      color="primary"
      @update:model-value="pick"
    />
  </VMenu>
</template>
