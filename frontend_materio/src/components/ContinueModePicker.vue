<script setup>
// "¿Cómo quieres fijar el precio?" — recibir ofertas de transportistas (el
// asesor/red de transportistas proponen precio) vs. publicar con un precio
// propio (fijo o negociable). El precio que pone el cliente acá es REAL —
// es lo que está dispuesto a pagar, no un dato decorativo. Título elegido
// para que el paso se explique solo (antes decía "¿Cómo quieres
// continuar?", que no aclaraba continuar A QUÉ).
import { ref } from 'vue'

const props = defineProps({
  mode: { type: String, default: 'ofertas' },       // v-model:mode — 'ofertas' | 'propio'
  // Ya llega precargado con el precio sugerido desde el padre (ver
  // priceTouched/watch en cotizar.vue y publicar/index.vue) — acá solo se
  // muestra y se deja editar.
  price: { type: [String, Number], default: '' },   // v-model:price
  negotiable: { type: Boolean, default: true },      // v-model:negotiable
  // Solo para mostrar la referencia "Precio sugerido: S/X" junto al campo —
  // no cambia aunque el cliente edite `price` (así puede comparar).
  suggestedPrice: { type: [String, Number], default: null },
})
const emit = defineEmits(['update:mode', 'update:price', 'update:negotiable'])

// Los dos títulos deben leerse como ACCIONES paralelas (qué pasa si elegís
// esta), no una acción y una etiqueta — "Recibir ofertas" ya lo es;
// "Publicar con tu precio" es el título por defecto (sin precio sugerido
// todavía, o editando a mano), y cuando SÍ hay un precio sugerido listo, el
// título se reemplaza por "PUBLICAR CON" + el monto (ver template) — misma
// forma de acción, con el número real en vez de "tu precio".
const OPTIONS = [
  {
    value: 'ofertas', icon: 'ri-team-line', title: 'Recibir ofertas',
    subtitle: 'Los transportistas proponen su precio — tú decides si aceptar o negociar.',
  },
  {
    value: 'propio', icon: 'ri-price-tag-3-line', title: 'Publicar con tu precio',
    subtitle: '',
  },
]

// Un campo abierto obliga a inventar un número sin referencia (¿es mucho?
// ¿es poco?) — esa es la fricción real, no el nombre del botón. Por eso el
// camino por defecto es publicar directo al precio ya sugerido (sin editar);
// "customizing" recién muestra el campo si alguien lo pide a propósito. Sin
// precio sugerido (modo asesor) no hay nada que "aceptar", así que ahí se
// muestra el campo directo, sin el paso de más.
const customizing = ref(false)
</script>

<template>
  <div>
    <div class="text-h6 font-weight-bold mb-3">¿Cómo quieres fijar el precio?</div>
    <VRow dense>
      <VCol v-for="o in OPTIONS" :key="o.value" cols="12" sm="6">
        <VCard
          variant="outlined"
          class="pa-4 h-100 position-relative price-tile"
          :class="{ 'price-tile--selected': mode === o.value }"
          style="cursor: pointer;"
          @click="emit('update:mode', o.value)"
        >
          <VIcon
            v-if="mode === o.value" icon="ri-checkbox-circle-fill" color="primary" size="18"
            style="position:absolute; top:10px; right:10px;"
          />
          <VAvatar
            size="40" class="mb-2" :variant="mode === o.value ? 'elevated' : 'tonal'"
            :color="mode === o.value ? 'primary' : 'surface-variant'"
          >
            <VIcon :icon="o.icon" size="20" :color="mode === o.value ? 'white' : undefined" />
          </VAvatar>
          <!-- Cuando hay precio sugerido listo para publicar, el título pasa
               a ser la acción completa "Publicar con S/X" — mismo estilo
               (tamaño, peso, mayúscula/minúscula, color) que "Recibir
               ofertas", para que las dos tiles se lean como opciones
               comparables, no una acción y una etiqueta distinta. -->
          <template v-if="o.value === 'propio' && !customizing && suggestedPrice != null">
            <div class="text-subtitle-1 font-weight-bold">Publicar con S/ {{ suggestedPrice }}</div>
          </template>
          <template v-else>
            <div class="text-subtitle-1 font-weight-bold">{{ o.title }}</div>
            <div v-if="o.subtitle" class="text-caption text-medium-emphasis">{{ o.subtitle }}</div>
          </template>

          <!-- Siempre visible (no solo tras elegir el tile) — así el cliente ve el
               precio sugerido ya cargado antes de decidir, en vez de un tile vacío. -->
          <template v-if="o.value === 'propio'">
            <template v-if="!customizing && suggestedPrice != null">
              <div class="text-caption text-medium-emphasis mt-1">
                Precio calculado según servicios similares en tu ruta.
              </div>
              <VBtn
                size="small" variant="text" color="primary" class="px-0 mt-1" style="text-transform: none; height: auto;"
                @click.stop="customizing = true; emit('update:mode', 'propio')"
              >
                ¿Quieres poner otro precio?
              </VBtn>
            </template>

            <template v-else>
              <div v-if="suggestedPrice != null" class="text-caption mt-3 d-flex align-center ga-1 flex-wrap">
                <span class="text-medium-emphasis">Precio sugerido: S/ {{ suggestedPrice }}</span>
                <VBtn
                  size="x-small" variant="text" color="primary" class="px-1" style="text-transform: none; height: auto; min-width: 0;"
                  @click.stop="customizing = false; emit('update:price', suggestedPrice)"
                >
                  Usar este
                </VBtn>
              </div>
              <div v-else class="text-caption text-medium-emphasis mt-1">
                Todavía no tenemos un precio sugerido para tu carga.
              </div>
              <VTextField
                :model-value="price" label="Tu precio (S/)" type="number" variant="outlined" density="comfortable"
                class="mt-2" prefix="S/" hide-details @click.stop
                @update:model-value="v => { customizing = true; emit('update:price', v) }"
              />

              <VRadioGroup
                :model-value="negotiable" inline hide-details density="comfortable"
                class="radio-pill-group mt-3" @click.stop
                @update:model-value="v => emit('update:negotiable', v)"
              >
                <VRadio :value="false" label="Fijo" />
                <VRadio :value="true" label="Negociable" />
              </VRadioGroup>
              <p class="text-caption text-medium-emphasis mt-2 mb-0">
                {{ negotiable ? 'Aceptan tu precio o proponen otro.' : 'Se paga exactamente ese monto.' }}
              </p>
            </template>
          </template>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>

<style scoped>
.price-tile {
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.price-tile:hover {
  border-color: rgb(var(--v-theme-primary));
}
.price-tile--selected {
  border-color: rgb(var(--v-theme-primary)) !important;
  border-inline-start: 3px solid rgb(var(--v-theme-primary)) !important;
  box-shadow: 0 4px 14px rgba(var(--v-theme-primary), 0.22);
}

/* Radio "tipo Materio" en caja compartida — mismo tratamiento que
   ScheduleStepPicker.vue (Fecha fija/flexible, Horario flexible/exacta),
   en vez del VBtnToggle (pill plano, sin punto de radio) que se veía
   "poco profesional". */
.radio-pill-group :deep(.v-selection-control-group) {
  display: flex;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  overflow: hidden;
}
.radio-pill-group :deep(.v-radio) {
  flex: 1 1 0;
  min-width: 0;
  margin: 0 !important;
  padding: 10px 14px;
  transition: background-color 0.15s ease;
}
.radio-pill-group :deep(.v-radio:not(:last-child)) {
  border-inline-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.radio-pill-group :deep(.v-radio.v-selection-control--dirty) {
  background: rgba(var(--v-theme-primary), 0.06);
}
.radio-pill-group :deep(.v-label) {
  font-size: 0.875rem;
  white-space: nowrap;
}

/* Las flechitas nativas del input number quedan desalineadas con el resto
   de los campos (Fecha/Hora no las tienen) — se ocultan, sigue siendo
   numérico (teclado numérico en mobile, valida solo dígitos). */
:deep(input[type='number']::-webkit-outer-spin-button),
:deep(input[type='number']::-webkit-inner-spin-button) {
  -webkit-appearance: none;
  margin: 0;
}
:deep(input[type='number']) {
  -moz-appearance: textfield;
}
</style>
