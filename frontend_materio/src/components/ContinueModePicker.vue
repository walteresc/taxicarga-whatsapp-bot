<script setup>
// "¿Cómo quieres continuar?" — recibir ofertas de transportistas (el
// asesor/red de transportistas proponen precio) vs. publicar con un precio
// propio (fijo o negociable). El precio que pone el cliente acá es REAL —
// es lo que está dispuesto a pagar, no un dato decorativo.
const props = defineProps({
  mode: { type: String, default: 'ofertas' },       // v-model:mode — 'ofertas' | 'propio'
  price: { type: [String, Number], default: '' },   // v-model:price
  negotiable: { type: Boolean, default: true },      // v-model:negotiable
})
const emit = defineEmits(['update:mode', 'update:price', 'update:negotiable'])

const OPTIONS = [
  {
    value: 'ofertas', icon: 'ri-team-line', title: 'Recibir ofertas',
    subtitle: 'Los transportistas proponen su precio.',
  },
  {
    value: 'propio', icon: 'ri-price-tag-3-line', title: 'Poner mi precio',
    subtitle: 'Vos decidís cuánto pagar.',
  },
]
</script>

<template>
  <div>
    <div class="text-h6 font-weight-bold mb-3">¿Cómo quieres continuar?</div>
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
        </VCard>
      </VCol>
    </VRow>

    <template v-if="mode === 'propio'">
      <VTextField
        :model-value="price" label="Tu precio (S/)" type="number" density="comfortable" class="mt-4 mb-3"
        prefix="S/" @update:model-value="v => emit('update:price', v)"
      />
      <VBtnToggle
        :model-value="negotiable" color="primary" variant="outlined" divided density="comfortable" mandatory
        class="price-btn-toggle"
        @update:model-value="v => emit('update:negotiable', v)"
      >
        <VBtn :value="false" class="px-6">Fijo</VBtn>
        <VBtn :value="true" class="px-6">Negociable</VBtn>
      </VBtnToggle>
      <p class="text-caption text-medium-emphasis mt-2 mb-0">
        {{ negotiable ? 'Aceptan tu precio o proponen otro.' : 'Se paga exactamente ese monto.' }}
      </p>
    </template>
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

/* El tema (Materio) fuerza en .v-btn-toggle un ancho fijo de 44/52px por
   botón (pensado para toggles de solo ícono) — con texto ("Fijo" /
   "Negociable") eso los aplasta y superpone. Se anula ese ancho fijo acá;
   la especificidad extra (dos clases en el mismo elemento) es necesaria
   para ganarle al !important del tema. */
:deep(.price-btn-toggle.v-btn-toggle .v-btn) {
  inline-size: auto !important;
  block-size: 40px !important;
}
</style>
