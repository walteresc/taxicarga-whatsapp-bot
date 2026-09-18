<script setup>
// Paso "Precio" del cotizador de Carga interprovincial: Consolidada (comparte
// camión, más barata y más lenta) vs. Express (camión dedicado). El precio
// que se muestra acá es SUGERIDO — sirve de referencia para negociar, no es
// el precio final (eso se confirma después, con un asesor si hace falta).
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: String, required: true },   // 'completa' | 'parcial'
  loading: { type: Boolean, default: false },
  express: { type: Object, default: null },
  consolidated: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue'])

const soles = n => (n == null ? null : `S/ ${Math.round(n).toLocaleString('es-PE')}`)

const priceLine = price => {
  if (!price) return null
  if (price.amount == null) return { text: 'A confirmar', sub: null }
  const range = price.range && price.range[0] !== price.range[1]
    ? `${soles(price.range[0])} – ${soles(price.range[1])}`
    : null

  return { text: soles(price.amount), sub: range }
}

const options = computed(() => {
  const list = [
    {
      value: 'parcial', icon: 'ri-truck-line', title: 'Consolidada',
      subtitle: 'Comparte camión — más económico.',
      price: props.consolidated,
    },
  ]
  list.push({
    value: 'completa', icon: 'ri-truck-fill', title: 'Express',
    subtitle: 'Camión exclusivo — más rápido.',
    price: props.express,
  })

  return list.filter(o => o.value !== 'parcial' || props.consolidated)
})
// Con una sola modalidad disponible no hay nada que "elegir" — mostrarla
// como tarjeta seleccionable (con media pantalla de hueco vacío al lado)
// confunde. Se muestra como una franja informativa, sin affordance de click.
const single = computed(() => (options.value.length === 1 ? options.value[0] : null))
</script>

<template>
  <div>
    <VProgressLinear v-if="loading" indeterminate class="mb-4" />
    <template v-else-if="single">
      <VCard variant="tonal" color="primary" class="pa-4 d-flex align-center ga-3 flex-wrap">
        <VAvatar size="40" color="primary" variant="elevated">
          <VIcon :icon="single.icon" size="20" color="white" />
        </VAvatar>
        <div class="flex-grow-1">
          <div class="text-subtitle-1 font-weight-bold">{{ single.title }}</div>
          <div class="text-caption text-medium-emphasis">{{ single.subtitle }}</div>
        </div>
        <div v-if="priceLine(single.price)" class="text-end">
          <div class="text-h6 font-weight-bold">{{ priceLine(single.price).text }}</div>
          <div v-if="priceLine(single.price).sub" class="text-caption text-medium-emphasis">
            {{ priceLine(single.price).sub }}
          </div>
        </div>
      </VCard>
      <p class="text-caption text-medium-emphasis mt-2 mb-0">Precio referencial — se confirma al reservar.</p>
    </template>
    <template v-else>
      <VRow dense>
        <VCol v-for="o in options" :key="o.value" cols="12" sm="6">
          <VCard
            :variant="modelValue === o.value ? 'tonal' : 'outlined'"
            :color="modelValue === o.value ? 'primary' : undefined"
            class="pa-4 h-100 position-relative price-tile" style="cursor: pointer;"
            @click="emit('update:modelValue', o.value)"
          >
            <VIcon
              v-if="modelValue === o.value" icon="ri-checkbox-circle-fill" color="primary" size="18"
              style="position:absolute; top:10px; right:10px;"
            />
            <VAvatar
              size="40" class="mb-2" :variant="modelValue === o.value ? 'elevated' : 'tonal'"
              :color="modelValue === o.value ? 'primary' : 'surface-variant'"
            >
              <VIcon :icon="o.icon" size="20" :color="modelValue === o.value ? 'white' : undefined" />
            </VAvatar>
            <div class="text-subtitle-1 font-weight-bold">{{ o.title }}</div>
            <div class="text-caption text-medium-emphasis mb-2">{{ o.subtitle }}</div>
            <template v-if="priceLine(o.price)">
              <VDivider class="mb-2" />
              <div class="text-h6 font-weight-bold">{{ priceLine(o.price).text }}</div>
              <div v-if="priceLine(o.price).sub" class="text-caption text-medium-emphasis">
                {{ priceLine(o.price).sub }}
              </div>
            </template>
          </VCard>
        </VCol>
      </VRow>
      <p class="text-caption text-medium-emphasis mt-2 mb-0">Precio referencial — se confirma al reservar.</p>
    </template>
  </div>
</template>

<style scoped>
.price-tile {
  transition: border-color 0.15s ease, transform 0.1s ease;
}
.price-tile:hover {
  border-color: rgb(var(--v-theme-primary));
}
</style>
