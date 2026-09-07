<script setup>
import { computed } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  value: { type: [String, Number], default: '—' },
  icon: { type: String, default: '' },
  color: { type: String, default: 'primary' },
  subtitle: { type: String, default: '' },
  // Delta en %, opcional. Positivo = verde, negativo = rojo.
  change: { type: Number, default: null },
})

const isPositive = computed(() => Number(props.change) >= 0)
</script>

<template>
  <VCard class="h-100">
    <VCardText class="d-flex align-center ga-4">
      <VAvatar
        v-if="icon"
        size="42"
        rounded="lg"
        :color="color"
        variant="tonal"
      >
        <VIcon :icon="icon" size="24" />
      </VAvatar>

      <div class="flex-grow-1 overflow-hidden">
        <div class="text-body-2 text-medium-emphasis text-truncate">
          {{ title }}
        </div>
        <div class="d-flex align-center flex-wrap ga-2">
          <span class="text-h5 font-weight-medium">{{ value }}</span>
          <span
            v-if="change !== null"
            class="text-body-2 d-inline-flex align-center"
            :class="isPositive ? 'text-success' : 'text-error'"
          >
            <VIcon :icon="isPositive ? 'ri-arrow-up-s-line' : 'ri-arrow-down-s-line'" size="18" />
            {{ Math.abs(change) }}%
          </span>
        </div>
        <div v-if="subtitle" class="text-caption text-medium-emphasis text-truncate">
          {{ subtitle }}
        </div>
      </div>
    </VCardText>
  </VCard>
</template>
