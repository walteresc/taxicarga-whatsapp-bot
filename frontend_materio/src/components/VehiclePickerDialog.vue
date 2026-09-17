<script setup>
// Modal "Elegir vehículo" (opcional) — con datos reales del catálogo
// (apps/catalogo). Por defecto dejamos que TaxiCarga elija el vehículo
// según la carga descrita; este picker es solo para el cliente que ya
// sabe qué necesita.
//
// Flujo en 2 pasos:
//  1) Categoría de PESO (Menores/Livianos/Medianos/Pesados/Especiales) +
//     unidad — es la decisión de menor fricción para un cliente que no
//     conoce términos técnicos, y la que más acota la lista.
//  2) Carrocería PARA esa unidad, con "Cualquiera" (compatible con mi
//     carga) como opción por defecto — no es obligatorio acertarla: si no
//     calza, el transportista lo evalúa al aceptar (ve foto/descripción/
//     peso) y puede rechazar.
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

const step = ref(1)
const chosenUnit = ref(null)
const chosenBody = ref('')   // '' = Cualquiera

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
watch(() => props.modelValue, v => {
  if (v) {
    load()
  } else {
    step.value = 1
    chosenUnit.value = null
    chosenBody.value = ''
  }
})

const filteredUnits = computed(() => selectedWeight.value
  ? units.value.filter(u => u.weightCategory === selectedWeight.value)
  : units.value)

const capacityLabel = u => {
  if (!u) return ''
  if (u.minTon == null && u.maxTon == null) return ''
  if (u.maxTon == null) return `Desde ${u.minTon} ton`
  if (u.minTon === 0) return `Hasta ${u.maxTon} ton`

  return `${u.minTon} – ${u.maxTon} ton`
}
const bodyName = code => bodyTypes.value.find(bt => bt.code === code)?.name || code
const unitBodyOptions = computed(() => (chosenUnit.value?.bodyTypes || []).map(code => ({ code, name: bodyName(code) })))

const close = () => emit('update:modelValue', false)
const chooseUnit = unit => { chosenUnit.value = unit; chosenBody.value = ''; step.value = 2 }
const back = () => { step.value = 1 }
const confirm = () => {
  const label = chosenBody.value ? `${chosenUnit.value.name} (${bodyName(chosenBody.value)})` : chosenUnit.value.name
  emit('select', label)
  close()
}
const clear = () => { emit('clear'); close() }
</script>

<template>
  <VDialog :model-value="modelValue" max-width="460" @update:model-value="v => emit('update:modelValue', v)">
    <VCard>
      <VCardTitle class="d-flex align-center justify-space-between">
        <div>
          <span class="text-subtitle-1 font-weight-bold d-block">Elegir vehículo</span>
          <span v-if="step === 1" class="text-caption text-medium-emphasis">Elegí por capacidad — la carrocería va después.</span>
          <span v-else class="text-caption text-medium-emphasis">¿Necesitás una carrocería en particular?</span>
        </div>
        <VBtn icon variant="text" size="small" @click="close">
          <VIcon icon="ri-close-line" />
        </VBtn>
      </VCardTitle>

      <VCardText v-if="step === 1" class="pt-0">
        <VProgressLinear v-if="loading" indeterminate class="mb-3" />

        <div v-if="weightCategories.length" class="d-flex flex-wrap ga-2 mb-3">
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
            prepend-icon="ri-truck-line" :title="u.name" :subtitle="capacityLabel(u)"
            @click="chooseUnit(u)"
          />
          <VListItem v-if="!loading && !filteredUnits.length" title="No hay unidades para esa categoría." class="text-medium-emphasis" />
        </VList>
      </VCardText>

      <VCardText v-else class="pt-0">
        <div class="d-flex align-center ga-2 mb-4">
          <VIcon icon="ri-truck-line" />
          <div>
            <div class="text-body-2 font-weight-bold">{{ chosenUnit.name }}</div>
            <div class="text-caption text-medium-emphasis">{{ capacityLabel(chosenUnit) }}</div>
          </div>
        </div>

        <div class="d-flex flex-wrap ga-2">
          <VChip
            :color="!chosenBody ? 'primary' : undefined" :variant="!chosenBody ? 'flat' : 'outlined'"
            @click="chosenBody = ''"
          >
            Cualquiera (compatible con mi carga)
          </VChip>
          <VChip
            v-for="bt in unitBodyOptions" :key="bt.code"
            :color="chosenBody === bt.code ? 'primary' : undefined" :variant="chosenBody === bt.code ? 'flat' : 'outlined'"
            @click="chosenBody = bt.code"
          >
            {{ bt.name }}
          </VChip>
        </div>
        <p v-if="!unitBodyOptions.length" class="text-caption text-medium-emphasis mt-2 mb-0">
          Esta unidad no tiene carrocerías específicas cargadas — queda en "Cualquiera".
        </p>
      </VCardText>

      <VCardActions class="px-4 pb-4">
        <VBtn v-if="step === 2" variant="text" @click="back">Atrás</VBtn>
        <VSpacer />
        <VBtn v-if="step === 1" variant="tonal" @click="clear">Dejar que TaxiCarga elija</VBtn>
        <VBtn v-else color="primary" @click="confirm">Confirmar</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
