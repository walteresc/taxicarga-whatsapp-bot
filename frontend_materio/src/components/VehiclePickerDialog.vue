<script setup>
// Modal "Elegir vehículo" (opcional) — carrocería + unidades disponibles,
// con datos reales del catálogo de vehículos (apps/catalogo). Por defecto
// dejamos que TaxiCarga elija el vehículo según la carga descrita; este
// picker es solo para el cliente que ya sabe qué necesita.
import { computed, ref, watch } from 'vue'

import { vehiclePickerCatalog } from '@/services/catalogService'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'select', 'clear'])

const loading = ref(false)
const bodyTypes = ref([])
const units = ref([])
const selectedBody = ref('')   // '' = Cualquiera

const load = async () => {
  if (units.value.length) return   // ya cargado, no repetir
  loading.value = true
  try {
    const data = await vehiclePickerCatalog()
    bodyTypes.value = data.bodyTypes || []
    units.value = data.units || []
  } catch (e) { /* si falla, queda el picker vacío — "TaxiCarga elige" sigue disponible */ }
  finally { loading.value = false }
}
watch(() => props.modelValue, v => { if (v) load() })

const filteredUnits = computed(() => selectedBody.value
  ? units.value.filter(u => u.bodyTypes.includes(selectedBody.value))
  : units.value)

const capacityLabel = u => {
  if (u.minTon == null && u.maxTon == null) return ''
  if (u.maxTon == null) return `Desde ${u.minTon} ton`
  if (u.minTon === 0) return `Hasta ${u.maxTon} ton`

  return `${u.minTon} – ${u.maxTon} ton`
}

const close = () => emit('update:modelValue', false)
const pick = unit => { emit('select', unit.name); close() }
const clear = () => { emit('clear'); close() }
</script>

<template>
  <VDialog :model-value="modelValue" max-width="420" @update:model-value="v => emit('update:modelValue', v)">
    <VCard>
      <VCardTitle class="d-flex align-center justify-space-between">
        <div>
          <span class="text-subtitle-1 font-weight-bold d-block">Elegir vehículo</span>
          <span class="text-caption text-medium-emphasis">La carrocería filtra las unidades disponibles.</span>
        </div>
        <VBtn icon variant="text" size="small" @click="close">
          <VIcon icon="ri-close-line" />
        </VBtn>
      </VCardTitle>

      <VCardText class="pt-0">
        <VProgressLinear v-if="loading" indeterminate class="mb-3" />

        <div v-if="bodyTypes.length" class="d-flex ga-2 overflow-x-auto pb-2 mb-2" style="scrollbar-width: thin;">
          <VChip
            :color="!selectedBody ? 'primary' : undefined" :variant="!selectedBody ? 'flat' : 'outlined'"
            size="small" @click="selectedBody = ''"
          >
            Cualquiera
          </VChip>
          <VChip
            v-for="bt in bodyTypes" :key="bt.code"
            :color="selectedBody === bt.code ? 'primary' : undefined" :variant="selectedBody === bt.code ? 'flat' : 'outlined'"
            size="small" :prepend-icon="bt.icon" @click="selectedBody = bt.code"
          >
            {{ bt.name }}
          </VChip>
        </div>

        <VList density="comfortable" style="max-height: 320px; overflow-y: auto;">
          <VListItem
            v-for="u in filteredUnits" :key="u.code" link
            prepend-icon="ri-truck-line" :title="u.name" :subtitle="capacityLabel(u)"
            @click="pick(u)"
          />
          <VListItem v-if="!loading && !filteredUnits.length" title="No hay unidades para esa carrocería." class="text-medium-emphasis" />
        </VList>
      </VCardText>

      <VCardText class="pt-0">
        <VBtn variant="tonal" block @click="clear">Dejar que TaxiCarga elija</VBtn>
      </VCardText>
    </VCard>
  </VDialog>
</template>
