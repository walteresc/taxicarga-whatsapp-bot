<script setup>
// Modal "Elegir vehículo" (opcional) — con datos reales del catálogo
// (apps/catalogo). Por defecto dejamos que TaxiCarga elija el vehículo
// según la carga descrita; este picker es solo para el cliente que ya
// sabe qué necesita.
//
// Flujo en 2 pasos (v-if/v-else — a propósito NO se usa VWindow, ver abajo):
//  1) Categoría de PESO (Menores/Livianos/Medianos/Pesados/Especiales) +
//     unidad — es la decisión de menor fricción para un cliente que no
//     conoce términos técnicos, y la que más acota la lista.
//  2) Carrocería PARA esa unidad, con "Cualquiera" (compatible con mi
//     carga) como opción por defecto — no es obligatorio acertarla: si no
//     calza, el transportista lo evalúa al aceptar (ve foto/descripción/
//     peso) y puede rechazar.
//
// El modal tiene tamaño FIJO (.vehicle-picker-card) para que no "salte" al
// cambiar de paso. Se probó con VWindow (como el wizard principal) pero
// VWindow anima su propio alto entre items (mide el contenido y lo
// interpola) — forzar una altura fija ahí adentro rompía su mecanismo de
// v-show y los dos pasos quedaban visibles superpuestos. Con v-if/v-else
// simple no hay ese conflicto: un solo paso existe en el DOM a la vez.
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
const unitBodyOptions = computed(() => (chosenUnit.value?.bodyTypes || [])
  .map(code => bodyTypes.value.find(bt => bt.code === code))
  .filter(Boolean))

const close = () => emit('update:modelValue', false)
const chooseUnit = unit => { chosenUnit.value = unit; chosenBody.value = ''; step.value = 2 }
const back = () => { step.value = 1 }
const confirm = () => {
  const bt = unitBodyOptions.value.find(b => b.code === chosenBody.value)
  const label = bt ? `${chosenUnit.value.name} (${bt.name})` : chosenUnit.value.name
  emit('select', label)
  close()
}
const clear = () => { emit('clear'); close() }
</script>

<template>
  <VDialog :model-value="modelValue" max-width="560" @update:model-value="v => emit('update:modelValue', v)">
    <VCard class="vehicle-picker-card">
      <VCardTitle class="d-flex align-center justify-space-between flex-shrink-0 pb-2">
        <div>
          <div class="d-flex align-center ga-2 mb-1">
            <span class="text-subtitle-1 font-weight-bold">Elegir vehículo</span>
            <div class="d-flex ga-1">
              <div class="step-dot" :class="{ 'step-dot--active': step === 1 }" />
              <div class="step-dot" :class="{ 'step-dot--active': step === 2 }" />
            </div>
          </div>
          <span v-if="step === 1" class="text-caption text-medium-emphasis">Paso 1 de 2 — elegí por capacidad.</span>
          <span v-else class="text-caption text-medium-emphasis">Paso 2 de 2 — carrocería (opcional).</span>
        </div>
        <VBtn icon variant="text" size="small" @click="close">
          <VIcon icon="ri-close-line" />
        </VBtn>
      </VCardTitle>
      <VDivider />

      <VCardText class="vehicle-picker-body pa-4">
        <VProgressLinear v-if="loading" indeterminate class="mb-3 flex-shrink-0" />

        <template v-if="step === 1">
          <div class="h-100 d-flex flex-column">
            <div v-if="weightCategories.length" class="d-flex flex-wrap ga-2 mb-3 flex-shrink-0">
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

            <div class="flex-grow-1" style="overflow-y: auto; min-height: 0;">
              <VCard
                v-for="u in filteredUnits" :key="u.code" variant="outlined" class="d-flex align-center pa-3 mb-2 unit-card"
                @click="chooseUnit(u)"
              >
                <VAvatar color="primary" variant="tonal" size="40" class="mr-3">
                  <VIcon icon="ri-truck-line" />
                </VAvatar>
                <div class="flex-grow-1">
                  <div class="text-body-2 font-weight-bold">{{ u.name }}</div>
                  <div class="text-caption text-medium-emphasis">{{ capacityLabel(u) }}</div>
                </div>
                <VIcon icon="ri-arrow-right-s-line" class="text-medium-emphasis" />
              </VCard>
              <div v-if="!loading && !filteredUnits.length" class="text-medium-emphasis text-body-2 text-center py-6">
                No hay unidades para esa categoría.
              </div>
            </div>
          </div>
        </template>

        <template v-else>
          <div class="h-100 d-flex flex-column">
            <VCard variant="tonal" color="primary" class="d-flex align-center pa-3 mb-4 flex-shrink-0">
              <VAvatar color="primary" variant="elevated" size="40" class="mr-3">
                <VIcon icon="ri-truck-line" />
              </VAvatar>
              <div>
                <div class="text-body-2 font-weight-bold">{{ chosenUnit.name }}</div>
                <div class="text-caption text-medium-emphasis">{{ capacityLabel(chosenUnit) }}</div>
              </div>
            </VCard>

            <p class="text-body-2 font-weight-medium mb-3 flex-shrink-0">¿Necesitás una carrocería en particular?</p>

            <div class="flex-grow-1" style="overflow-y: auto; min-height: 0;">
              <VCard
                variant="outlined" class="d-flex align-center pa-3 mb-2 unit-card"
                :color="!chosenBody ? 'primary' : undefined"
                @click="chosenBody = ''"
              >
                <VAvatar :color="!chosenBody ? 'primary' : 'surface-variant'" :variant="!chosenBody ? 'elevated' : 'tonal'" size="40" class="mr-3">
                  <VIcon icon="ri-checkbox-multiple-blank-line" :color="!chosenBody ? 'white' : undefined" />
                </VAvatar>
                <div class="flex-grow-1">
                  <div class="text-body-2 font-weight-bold">Cualquiera</div>
                  <div class="text-caption text-medium-emphasis">Compatible con mi carga</div>
                </div>
                <VIcon v-if="!chosenBody" icon="ri-checkbox-circle-fill" color="primary" />
              </VCard>
              <VCard
                v-for="bt in unitBodyOptions" :key="bt.code" variant="outlined" class="d-flex align-center pa-3 mb-2 unit-card"
                :color="chosenBody === bt.code ? 'primary' : undefined"
                @click="chosenBody = bt.code"
              >
                <VAvatar :color="chosenBody === bt.code ? 'primary' : 'surface-variant'" :variant="chosenBody === bt.code ? 'elevated' : 'tonal'" size="40" class="mr-3">
                  <VIcon :icon="bt.icon" :color="chosenBody === bt.code ? 'white' : undefined" />
                </VAvatar>
                <div class="flex-grow-1 text-body-2 font-weight-bold">{{ bt.name }}</div>
                <VIcon v-if="chosenBody === bt.code" icon="ri-checkbox-circle-fill" color="primary" />
              </VCard>
              <p v-if="!unitBodyOptions.length" class="text-caption text-medium-emphasis mt-2 mb-0">
                Esta unidad no tiene carrocerías específicas cargadas — queda en "Cualquiera".
              </p>
            </div>
          </div>
        </template>
      </VCardText>

      <VDivider />
      <VCardActions class="px-4 py-3 flex-shrink-0">
        <VBtn v-if="step === 2" variant="text" prepend-icon="ri-arrow-left-line" @click="back">Atrás</VBtn>
        <VSpacer />
        <VBtn v-if="step === 1" variant="tonal" @click="clear">Dejar que TaxiCarga elija</VBtn>
        <VBtn v-else color="primary" variant="elevated" rounded="lg" @click="confirm">Confirmar</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* Tamaño fijo real. OJO: dentro de un VDialog, Vuetify le aplica a la VCard
   "flex: 1 1 100%" por su propio CSS (.v-dialog > .v-overlay__content >
   .v-card) — con flex-basis en 100% (no "auto"), el algoritmo de flexbox
   IGNORA la propiedad height por completo (así lo define el spec: un
   flex-basis explícito reemplaza a height/width para el tamaño principal).
   Por eso el height de acá abajo nunca se aplicaba y el modal seguía
   ajustándose al contenido. Se anula ese flex-basis (flex: 0 0 auto) con
   !important porque el selector de Vuetify (3 clases encadenadas) tiene más
   especificidad que esta clase sola. */
.vehicle-picker-card {
  width: 100%;
  height: 640px;
  max-height: 88vh;
  flex: 0 0 auto !important;
  display: flex;
  flex-direction: column;
}
.vehicle-picker-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.step-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(var(--v-theme-on-surface), 0.2);
}
.step-dot--active {
  background: rgb(var(--v-theme-primary));
}

.unit-card {
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.unit-card:hover {
  border-color: rgb(var(--v-theme-primary));
}
</style>
