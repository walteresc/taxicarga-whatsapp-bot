<script setup>
import { computed, ref, useAttrs } from 'vue'

// Campo de fecha unificado para todo el CRM: VTextField estilo Materio +
// calendario Vuetify en un menú. El v-model sigue siendo un string
// 'YYYY-MM-DD' (o '') como el resto del código espera.
defineOptions({ inheritAttrs: false })

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

const attrs = useAttrs()
// El wrapper aplica class/style del padre al VTextField interno (el activador
// del menú), no al VMenu; y no reenvía el listener de v-model.
const fieldAttrs = computed(() => {
  const { 'onUpdate:modelValue': _omit, ...rest } = attrs
  return rest
})

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
        v-bind="{ ...activator, ...fieldAttrs }"
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
      hide-header
      color="primary"
      class="app-date-field__picker"
      @update:model-value="pick"
    />
  </VMenu>
</template>

<style scoped>
.app-date-field__picker {
  width: 280px;
}
.app-date-field__picker :deep(.v-date-picker-month) {
  min-width: auto;
  padding-inline: 8px;
}
.app-date-field__picker :deep(.v-date-picker-month__day) {
  width: 32px;
  height: 32px;
}
.app-date-field__picker :deep(.v-date-picker-month__day .v-btn) {
  width: 30px;
  height: 30px;
}
.app-date-field__picker :deep(.v-date-picker-controls) {
  padding-inline: 8px;
  min-height: 40px;
}
</style>
