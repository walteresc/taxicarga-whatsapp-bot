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
// rechazar.
//
// "Dejar que TaxiCarga elija" solo tiene sentido ANTES de elegir una
// unidad (deja que TaxiCarga elija el VEHÍCULO) — una vez que el cliente
// ya eligió un camión específico, ese botón confundiría ("¿elige la
// carrocería?"). Por eso el botón de abajo cambia a "Confirmar" (con
// "Cualquiera" preseleccionado) apenas se expande una unidad.
import { computed, ref, watch } from 'vue'

import CarroceriaIcon from '@/components/CarroceriaIcon.vue'
import { vehiclePickerCatalog } from '@/services/catalogService'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // Estimado por el padre (regex o IA — ver apps/cotizador/services_estimacion.py).
  // Solo se usa para RESALTAR una unidad como recomendada y preseleccionar
  // su categoría de peso — nunca para ocultar ni filtrar el resto: puede
  // haber una razón real (frágil, urgente) para elegir otra igual.
  estimatedWeightKg: { type: Number, default: null },
  estimatedVolumeM3: { type: Number, default: null },
})
const emit = defineEmits(['update:modelValue', 'select', 'clear'])

const loading = ref(false)
const bodyTypes = ref([])
const weightCategories = ref([])
const units = ref([])
const selectedWeight = ref('')   // '' = Todas
const expandedUnit = ref('')     // code de la unidad con el panel de carrocería abierto
const chosenUnit = ref(null)
const chosenBody = ref(null)     // null = Cualquiera

const recommendedUnitCode = computed(() => {
  if (props.estimatedWeightKg == null) return null
  const ton = props.estimatedWeightKg / 1000

  return units.value.find(u =>
    (u.minTon == null || ton >= u.minTon) && (u.maxTon == null || ton <= u.maxTon))?.code || null
})

const load = async () => {
  if (units.value.length) return   // ya cargado, no repetir
  loading.value = true
  try {
    const data = await vehiclePickerCatalog()
    bodyTypes.value = data.bodyTypes || []
    weightCategories.value = data.weightCategories || []
    units.value = data.units || []
    // Preselecciona el filtro de peso recomendado (una sola vez, si el
    // cliente todavía no tocó el filtro) — el resto de categorías sigue a
    // un toque de distancia en "Todas".
    if (!selectedWeight.value && recommendedUnitCode.value) {
      selectedWeight.value = units.value.find(u => u.code === recommendedUnitCode.value)?.weightCategory || ''
    }
  } catch (e) { /* si falla, queda el picker vacío — "TaxiCarga elige" sigue disponible */ }
  finally { loading.value = false }
}
// Si la unidad expandida queda afuera del filtro (p. ej. se cambia de
// categoría de peso mientras hay una unidad abierta), había quedado el
// botón "Confirmar"/"Cambiar unidad" activo para una unidad que ya no se
// veía en la lista — colapsa el panel para evitar ese estado fantasma.
watch(selectedWeight, () => {
  if (expandedUnit.value && !filteredUnits.value.some(u => u.code === expandedUnit.value)) {
    expandedUnit.value = ''
    chosenUnit.value = null
    chosenBody.value = null
  }
})

watch(() => props.modelValue, v => {
  if (v) load()
  else { expandedUnit.value = ''; chosenUnit.value = null; chosenBody.value = null }
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
// Tocar la fila de una unidad ABIERTA solo la colapsa (no descarta la
// carrocería ya elegida — antes se perdía silenciosamente si el usuario
// volvía a tocar la fila, p. ej. pensando que así confirmaba su elección).
// La carrocería solo se reinicia a "Cualquiera" al abrir una unidad
// DISTINTA a la que estaba elegida.
const toggleUnit = u => {
  // Unidad "virtual" con carrocería fija (p. ej. "Cigüeña" — ver
  // apps/catalogo, nombre_cliente): ya trae su carrocería resuelta, no
  // tiene sentido pedirle al cliente que elija una — se confirma directo.
  if (u.fixedBodyType) {
    emit('select', u.name)
    close()
    return
  }
  if (expandedUnit.value === u.code) {
    expandedUnit.value = ''
    return
  }
  expandedUnit.value = u.code
  if (chosenUnit.value?.code !== u.code) chosenBody.value = null
  chosenUnit.value = u
}
const pickBody = bt => { chosenBody.value = bt }
const confirm = () => {
  const label = chosenBody.value ? `${chosenUnit.value.name} (${chosenBody.value.name})` : chosenUnit.value.name
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
                <div class="d-flex align-center ga-2">
                  <div class="text-body-2 font-weight-bold">{{ u.name }}</div>
                  <VChip v-if="u.code === recommendedUnitCode" size="x-small" color="primary" variant="flat">Recomendado</VChip>
                </div>
                <div class="text-caption text-medium-emphasis">{{ capacityLabel(u) }}</div>
              </div>
              <VIcon
                v-if="!u.fixedBodyType"
                :icon="expandedUnit === u.code ? 'ri-arrow-up-s-line' : 'ri-arrow-right-s-line'" class="text-medium-emphasis"
              />
              <VIcon v-else icon="ri-checkbox-circle-line" class="text-medium-emphasis" />
            </div>

            <template v-if="expandedUnit === u.code">
              <VDivider />
              <div class="pa-3 body-panel">
                <div class="text-caption text-medium-emphasis mb-2">
                  <strong>Opcional:</strong> elegí un tipo de carrocería, o dejala en "Compatible" para conseguir vehículos compatibles con tu carga.
                </div>
                <div class="d-flex flex-wrap ga-2">
                  <VChip
                    :color="!chosenBody ? 'primary' : undefined" :variant="!chosenBody ? 'flat' : 'outlined'"
                    prepend-icon="ri-checkbox-multiple-blank-line" @click="pickBody(null)"
                  >
                    Compatible
                  </VChip>
                  <VChip
                    v-for="bt in bodyOptionsFor(u)" :key="bt.code"
                    :color="chosenBody?.code === bt.code ? 'primary' : undefined" :variant="chosenBody?.code === bt.code ? 'flat' : 'outlined'"
                    @click="pickBody(bt)"
                  >
                    <CarroceriaIcon :code="bt.code" size="16" class="mr-1" />
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
        <VBtn v-if="expandedUnit" variant="text" prepend-icon="ri-close-line" @click="toggleUnit(chosenUnit)">Cambiar unidad</VBtn>
        <VSpacer />
        <VBtn v-if="!expandedUnit" variant="outlined" @click="clear">Dejar que TaxiCarga elija</VBtn>
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
  border-color: rgb(var(--v-theme-primary)) !important;
  border-inline-start: 3px solid rgb(var(--v-theme-primary)) !important;
  box-shadow: 0 4px 14px rgba(var(--v-theme-primary), 0.22);
}
.body-panel {
  background: rgba(var(--v-theme-primary), 0.05);
}
</style>
