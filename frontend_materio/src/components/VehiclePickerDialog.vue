<script setup>
// Modal "Elegir vehículo" (opcional) — con datos reales del catálogo
// (apps/catalogo). Por defecto dejamos que TaxiCarga elija el vehículo
// según la carga descrita; este picker es solo para el cliente que ya
// sabe qué necesita.
//
// Filtro principal: categoría de PESO (Menores/Livianos/Medianos/Pesados/
// Especiales) — es la decisión de menor fricción para un cliente que no
// conoce términos técnicos. La carrocería queda solo como dato informativo
// en cada unidad, no como filtro: si el vehículo asignado no tiene la
// carrocería que la carga necesita, es el transportista quien lo evalúa y
// puede rechazar el servicio al verlo (ve foto/descripción/peso) — no hace
// falta que el cliente acierte esa decisión de antemano.
import { computed, ref, watch } from 'vue'

import { vehiclePickerCatalog } from '@/services/catalogService'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'select', 'clear'])

const loading = ref(false)
const bodyTypes = ref([])
const weightCategories = ref([])
const units = ref([])
const selectedWeight = ref('')   // '' = Todas

const load = async () => {
  if (units.value.length) return   // ya cargado, no repetir
  loading.value = true
  try {
    const data = await vehiclePickerCatalog()
    bodyTypes.value = data.bodyTypes || []
    weightCategories.value = data.weightCategories || []
    units.value = data.units || []
  } catch (e) { /* si falla, queda el picker vacío — "TaxiCarga elige" sigue disponible */ }
  finally { loading.value = false }
}
watch(() => props.modelValue, v => { if (v) load() })

const filteredUnits = computed(() => selectedWeight.value
  ? units.value.filter(u => u.weightCategory === selectedWeight.value)
  : units.value)

const capacityLabel = u => {
  if (u.minTon == null && u.maxTon == null) return ''
  if (u.maxTon == null) return `Desde ${u.minTon} ton`
  if (u.minTon === 0) return `Hasta ${u.maxTon} ton`

  return `${u.minTon} – ${u.maxTon} ton`
}
const bodyTypesLabel = u => u.bodyTypes
  .map(code => bodyTypes.value.find(bt => bt.code === code)?.name)
  .filter(Boolean)
  .join(', ')
const unitSubtitle = u => [capacityLabel(u), bodyTypesLabel(u)].filter(Boolean).join(' · ')

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
          <span class="text-caption text-medium-emphasis">Elegí por capacidad — la carrocería es solo referencial.</span>
        </div>
        <VBtn icon variant="text" size="small" @click="close">
          <VIcon icon="ri-close-line" />
        </VBtn>
      </VCardTitle>

      <VCardText class="pt-0">
        <VProgressLinear v-if="loading" indeterminate class="mb-3" />

        <div v-if="weightCategories.length" class="d-flex ga-2 overflow-x-auto pb-2 mb-2" style="scrollbar-width: thin;">
          <VChip
            :color="!selectedWeight ? 'primary' : undefined" :variant="!selectedWeight ? 'flat' : 'outlined'"
            size="small" @click="selectedWeight = ''"
          >
            Todas
          </VChip>
          <VChip
            v-for="wc in weightCategories" :key="wc.code"
            :color="selectedWeight === wc.code ? 'primary' : undefined" :variant="selectedWeight === wc.code ? 'flat' : 'outlined'"
            size="small" @click="selectedWeight = wc.code"
          >
            {{ wc.name }}
          </VChip>
        </div>

        <VList density="comfortable" style="max-height: 320px; overflow-y: auto;">
          <VListItem
            v-for="u in filteredUnits" :key="u.code" link
            prepend-icon="ri-truck-line" :title="u.name" :subtitle="unitSubtitle(u)"
            @click="pick(u)"
          />
          <VListItem v-if="!loading && !filteredUnits.length" title="No hay unidades para esa categoría." class="text-medium-emphasis" />
        </VList>
      </VCardText>

      <VCardText class="pt-0">
        <VBtn variant="tonal" block @click="clear">Dejar que TaxiCarga elija</VBtn>
      </VCardText>
    </VCard>
  </VDialog>
</template>
