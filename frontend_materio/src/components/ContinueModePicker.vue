<script setup>
// "Elige cómo quieres publicar tu carga" — recibir ofertas de transportistas
// vs. publicar con un precio propio. El precio que pone el cliente acá es
// REAL — es lo que está dispuesto a pagar, no un dato decorativo.
//
// Ya no se pregunta Fijo/Negociable (decisión de UX, 2026-09-24): el
// transportista SIEMPRE puede aceptar el precio propuesto o contraproponer
// — quitamos la elección porque no agregaba nada que el cliente pudiera
// usar bien, y confundía más de lo que ayudaba.
import { computed, ref } from 'vue'

const props = defineProps({
  mode: { type: String, default: 'ofertas' },       // v-model:mode — 'ofertas' | 'propio'
  // Ya llega precargado con el precio sugerido desde el padre (ver
  // priceTouched/watch en cotizar.vue y publicar/index.vue) — acá solo se
  // muestra y se deja editar.
  price: { type: [String, Number], default: '' },   // v-model:price
  // Solo para mostrar la referencia al editar, y como fallback del título
  // mientras el cliente no tocó nada.
  suggestedPrice: { type: [String, Number], default: null },
})
const emit = defineEmits(['update:mode', 'update:price'])

// Un campo abierto obliga a inventar un número sin referencia — por eso el
// camino por defecto es publicar directo al precio ya sugerido (sin editar);
// "customizing" recién muestra el campo si alguien lo pide con "Cambiar precio".
const customizing = ref(false)

// El tile de precio propio muestra el monto en el TÍTULO ("Publicar con
// S/X") — es la acción concreta que confirma al elegir esa opción.
const displayAmount = computed(() => props.price || props.suggestedPrice)

const OPTIONS = computed(() => [
  {
    value: 'ofertas', icon: 'ri-team-line', title: 'Recibir ofertas',
    subtitle: 'Publica sin indicar un precio. Los transportistas te enviarán propuestas y tú eliges la que más te convenga.',
  },
  {
    value: 'propio', icon: 'ri-price-tag-3-line',
    title: displayAmount.value != null ? `Publicar con S/ ${displayAmount.value}` : 'Publicar con tu precio',
    subtitle: 'Los transportistas podrán aceptar tu precio o enviarte una contrapropuesta.',
  },
])
</script>

<template>
  <div>
    <!-- El título "Publicar Carga" + "Elige cómo quieres publicar tu carga"
         ya lo pone la página, antes de la cabecera de precio — no se repite
         acá para no mostrarlo dos veces seguidas. -->
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
          <div class="text-subtitle-1 font-weight-bold">{{ o.title }}</div>
          <div class="text-caption text-medium-emphasis">{{ o.subtitle }}</div>

          <template v-if="o.value === 'propio'">
            <VBtn
              v-if="!customizing"
              size="small" variant="text" color="primary" class="px-0 mt-2" style="text-transform: none; height: auto;"
              prepend-icon="ri-pencil-line" @click.stop="customizing = true; emit('update:mode', 'propio')"
            >
              Cambiar precio
            </VBtn>

            <template v-else>
              <VTextField
                :model-value="price" label="Tu precio (S/)" type="number" variant="outlined" density="comfortable"
                class="mt-2" prefix="S/" hide-details autofocus @click.stop
                @update:model-value="v => emit('update:price', v)"
              />
              <VBtn
                v-if="suggestedPrice != null" size="x-small" variant="text" color="primary" class="px-0 mt-1"
                style="text-transform: none; height: auto;"
                @click.stop="customizing = false; emit('update:price', suggestedPrice)"
              >
                Usar precio sugerido (S/ {{ suggestedPrice }})
              </VBtn>
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
