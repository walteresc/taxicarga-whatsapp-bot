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
</script>

<template>
  <div>
    <div class="text-subtitle-2 mb-2">¿Cómo quieres continuar?</div>
    <VRow dense>
      <VCol cols="12" sm="6">
        <VCard
          :variant="mode === 'ofertas' ? 'tonal' : 'outlined'" :color="mode === 'ofertas' ? 'primary' : undefined"
          class="pa-4 h-100" style="cursor: pointer;" @click="emit('update:mode', 'ofertas')"
        >
          <VIcon icon="ri-team-line" size="24" class="mb-2" />
          <div class="text-subtitle-2 font-weight-bold mb-1">Publicar sin precio, recibir ofertas</div>
          <div class="text-caption text-medium-emphasis">
            Nuestros transportistas proponen su precio — vos aceptás o negociás el que más te convenga.
          </div>
        </VCard>
      </VCol>
      <VCol cols="12" sm="6">
        <VCard
          :variant="mode === 'propio' ? 'tonal' : 'outlined'" :color="mode === 'propio' ? 'primary' : undefined"
          class="pa-4 h-100" style="cursor: pointer;" @click="emit('update:mode', 'propio')"
        >
          <VIcon icon="ri-price-tag-3-line" size="24" class="mb-2" />
          <div class="text-subtitle-2 font-weight-bold mb-1">Publicar con mi precio</div>
          <div class="text-caption text-medium-emphasis">
            Indicá el precio que querés pagar — fijo o abierto a que te contraofrezcan.
          </div>
        </VCard>
      </VCol>
    </VRow>

    <template v-if="mode === 'propio'">
      <VTextField
        :model-value="price" label="Tu precio (S/)" type="number" density="comfortable" class="mt-3 mb-2"
        prefix="S/" @update:model-value="v => emit('update:price', v)"
      />
      <VRadioGroup
        :model-value="negotiable" density="comfortable" inline hide-details
        @update:model-value="v => emit('update:negotiable', v)"
      >
        <VRadio :value="false" label="Fijo" />
        <VRadio :value="true" label="Negociable" />
      </VRadioGroup>
      <p class="text-caption text-medium-emphasis mt-1 mb-0">
        Los transportistas aceptan tu precio {{ negotiable ? 'o proponen una contraoferta.' : '.' }}
      </p>
    </template>
  </div>
</template>
