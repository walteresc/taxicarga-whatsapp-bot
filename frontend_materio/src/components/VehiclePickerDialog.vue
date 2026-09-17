<script setup>
// Modal "Elegir vehículo" (opcional) — con datos reales del catálogo
// (apps/catalogo). Por defecto dejamos que TaxiCarga elija el vehículo
// según la carga descrita; este picker es solo para el cliente que ya
// sabe qué necesita.
//
// Un solo panel, sin pasos/pantallas separadas: categoría de PESO arriba
// (Menores/Livianos/Medianos/Pesados/Especiales — la decisión de menor
// fricción, la que más acota la lista) + lista de unidades. Al tocar una
// unidad, se expande EN EL LUGAR (no cambia de pantalla ni de modal) para
// elegir carrocería, con "Cualquiera" (compatible con mi carga) como
// opción por defecto — no es obligatorio acertarla: si no calza, el
// transportista lo evalúa al aceptar (ve foto/descripción/peso) y puede
// rechazar. Elegir cualquier opción confirma y cierra directo — menos
// clics, menos pantallas.
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
const expandedUnit = ref('')     // code de la unidad con el panel de carrocería abierto

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
  if (v) load()
  else expandedUnit.value = ''
})

const filteredUnits = computed(() => selectedWeight.value
  ? units.value.filter(u => u.weightCategory === selectedWeight.value)
  : units.value)

const capacityLabel = u => {
  if (u.minTon == null && u.maxTon == null) return ''
  if (u.maxTon == null) return `Desde ${u.minTon} ton`
  if (u.minTon === 0) return `Hasta ${u.maxTon} ton`

  return `${u.minTon} – ${u.maxTon} ton`
}
const bodyOptionsFor = u => (u.bodyTypes || [])
  .map(code => bodyTypes.value.find(bt => bt.code === code))
  .filter(Boolean)

const close = () => emit('update:modelValue', false)
const toggleUnit = u => { expandedUnit.value = expandedUnit.value === u.code ? '' : u.code }
const pickBody = (unit, bt) => {
  const label = bt ? `${unit.name} (${bt.name})` : unit.name
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
          <span class="text-subtitle-1 font-weight-bold d-block">Elegir vehículo</span>
          <span class="text-caption text-medium-emphasis">Elegí la unidad — la carrocería es opcional.</span>
        </div>
        <VBtn icon variant="text" size="small" @click="close">
          <VIcon icon="ri-close-line" />
        </VBtn>
      </VCardTitle>
      <VDivider />

      <VCardText class="vehicle-picker-body pa-4">
        <VProgressLinear v-if="loading" indeterminate class="mb-3 flex-shrink-0" />

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
            v-for="u in filteredUnits" :key="u.code" variant="outlined" class="mb-2 unit-card"
            :class="{ 'unit-card--expanded': expandedUnit === u.code }"
          >
            <div class="d-flex align-center pa-3" style="cursor: pointer;" @click="toggleUnit(u)">
              <VAvatar :color="expandedUnit === u.code ? 'primary' : 'surface-variant'" :variant="expandedUnit === u.code ? 'elevated' : 'tonal'" size="40" class="mr-3">
                <VIcon icon="ri-truck-line" :color="expandedUnit === u.code ? 'white' : undefined" />
              </VAvatar>
              <div class="flex-grow-1">
                <div class="text-body-2 font-weight-bold">{{ u.name }}</div>
                <div class="text-caption text-medium-emphasis">{{ capacityLabel(u) }}</div>
              </div>
              <VIcon :icon="expandedUnit === u.code ? 'ri-arrow-up-s-line' : 'ri-arrow-right-s-line'" class="text-medium-emphasis" />
            </div>

            <template v-if="expandedUnit === u.code">
              <VDivider />
              <div class="pa-3 body-panel">
                <div class="text-caption text-medium-emphasis mb-2">
                  ¿Alguna carrocería en particular? Elegí "Cualquiera" si no te importa.
                </div>
                <div class="d-flex flex-wrap ga-2">
                  <VChip variant="tonal" color="primary" prepend-icon="ri-checkbox-multiple-blank-line" @click="pickBody(u, null)">
                    Cualquiera
                  </VChip>
                  <VChip
                    v-for="bt in bodyOptionsFor(u)" :key="bt.code" variant="outlined"
                    :prepend-icon="bt.icon" @click="pickBody(u, bt)"
                  >
                    {{ bt.name }}
                  </VChip>
                </div>
              </div>
            </template>
          </VCard>
          <div v-if="!loading && !filteredUnits.length" class="text-medium-emphasis text-body-2 text-center py-6">
            No hay unidades para esa categoría.
          </div>
        </div>
      </VCardText>

      <VDivider />
      <VCardActions class="px-4 py-3 flex-shrink-0">
        <VSpacer />
        <VBtn variant="tonal" @click="clear">Dejar que TaxiCarga elija</VBtn>
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
   Se anula ese flex-basis (flex: 0 0 auto) con !important porque el
   selector de Vuetify (3 clases encadenadas) tiene más especificidad que
   esta clase sola. */
.vehicle-picker-card {
  width: 100%;
  height: 600px;
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

.unit-card {
  transition: border-color 0.15s ease;
}
.unit-card:hover {
  border-color: rgb(var(--v-theme-primary));
}
.unit-card--expanded {
  border-color: rgb(var(--v-theme-primary));
  border-width: 2px;
}
.body-panel {
  background: rgba(var(--v-theme-primary), 0.05);
}
</style>
