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
  if (price.amount == null) return { text: 'Un asesor te confirma el precio', sub: null }
  const range = price.range && price.range[0] !== price.range[1]
    ? `Rango ${soles(price.range[0])} – ${soles(price.range[1])}`
    : null

  return { text: soles(price.amount), sub: range }
}

const options = computed(() => {
  const list = [
    {
      value: 'parcial', icon: 'ri-truck-line', title: 'Carga consolidada',
      subtitle: 'Tu carga viaja junto con otras — más económico, llega un poco más tarde.',
      price: props.consolidated,
    },
  ]
  list.push({
    value: 'completa', icon: 'ri-truck-fill', title: 'Carga express',
    subtitle: 'Un camión dedicado solo para tu carga — más rápido.',
    price: props.express,
  })

  return list.filter(o => o.value !== 'parcial' || props.consolidated)
})
</script>

<template>
  <div>
    <VProgressLinear v-if="loading" indeterminate class="mb-4" />
    <template v-else>
      <VRow dense>
        <VCol v-for="o in options" :key="o.value" cols="12" sm="6">
          <VCard
            :variant="modelValue === o.value ? 'tonal' : 'outlined'"
            :color="modelValue === o.value ? 'primary' : undefined"
            class="pa-4 h-100" style="cursor: pointer;"
            @click="emit('update:modelValue', o.value)"
          >
            <VIcon :icon="o.icon" size="26" class="mb-2" />
            <div class="text-subtitle-1 font-weight-bold mb-1">{{ o.title }}</div>
            <div class="text-caption text-medium-emphasis mb-3">{{ o.subtitle }}</div>
            <VDivider class="mb-3" />
            <template v-if="priceLine(o.price)">
              <div class="text-caption text-medium-emphasis">Precio sugerido</div>
              <div class="text-h6 font-weight-bold">{{ priceLine(o.price).text }}</div>
              <div v-if="priceLine(o.price).sub" class="text-caption text-medium-emphasis">
                {{ priceLine(o.price).sub }}
              </div>
            </template>
          </VCard>
        </VCol>
      </VRow>
      <p class="text-caption text-medium-emphasis mt-3 mb-0">
        Precio de referencia para negociar — el precio final se confirma al reservar.
      </p>
    </template>
  </div>
</template>
