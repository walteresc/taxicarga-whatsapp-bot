<script setup>
// Modal "Elegir vehículo" (opcional) — por defecto dejamos que TaxiCarga
// elija el vehículo según la carga descrita; este picker es solo para el
// cliente que ya sabe qué necesita.
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  trucks: { type: Array, required: true },
})
const emit = defineEmits(['update:modelValue', 'select', 'clear'])

const close = () => emit('update:modelValue', false)
const pick = value => { emit('select', value); close() }
const clear = () => { emit('clear'); close() }
</script>

<template>
  <VDialog :model-value="modelValue" max-width="360" @update:model-value="v => emit('update:modelValue', v)">
    <VCard>
      <VCardTitle class="d-flex align-center justify-space-between">
        <span class="text-subtitle-1 font-weight-bold">Elegir vehículo</span>
        <VBtn icon variant="text" size="small" @click="close">
          <VIcon icon="ri-close-line" />
        </VBtn>
      </VCardTitle>
      <VList density="comfortable">
        <VListItem
          v-for="t in props.trucks" :key="t.value" link
          :prepend-icon="t.icon || 'ri-truck-line'"
          :title="t.title" @click="pick(t.value)"
        />
      </VList>
      <VCardText class="pt-0">
        <VBtn variant="tonal" block @click="clear">Dejar que TaxiCarga elija</VBtn>
      </VCardText>
    </VCard>
  </VDialog>
</template>
