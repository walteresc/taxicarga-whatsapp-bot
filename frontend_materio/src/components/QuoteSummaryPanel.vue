<script setup>
// Panel de resumen (columna derecha del cotizador): mapa estático con
// origen/destino + los datos que el cliente ya cargó, para que sienta que
// "ve" su solicitud mientras la completa.
import { computed } from 'vue'

const props = defineProps({
  serviceLabel: { type: String, default: '' },
  origin: { type: Object, default: () => ({}) },
  destination: { type: Object, default: () => ({}) },
  detail: { type: String, default: '' },
  date: { type: String, default: '' },
  truckLabel: { type: String, default: '' },
})

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || ''

const hasOrigin = computed(() => props.origin?.lat != null && props.origin?.lng != null)
const hasDestination = computed(() => props.destination?.lat != null && props.destination?.lng != null)

const mapUrl = computed(() => {
  if (!MAPBOX_TOKEN) return ''
  const pins = []
  if (hasOrigin.value) pins.push(`pin-s-a+2E7D32(${props.origin.lng},${props.origin.lat})`)
  if (hasDestination.value) pins.push(`pin-s-b+C62828(${props.destination.lng},${props.destination.lat})`)
  if (!pins.length) return ''

  return `https://api.mapbox.com/styles/v1/mapbox/streets-v12/static/${pins.join(',')}/auto/600x360@2x` +
    `?padding=40&access_token=${MAPBOX_TOKEN}`
})

const fmtDate = iso => {
  if (!iso) return null
  try {
    return new Date(`${iso}T00:00:00`).toLocaleDateString('es-PE', { weekday: 'long', day: 'numeric', month: 'long' })
  } catch { return iso }
}
</script>

<template>
  <VCard variant="outlined" class="h-100">
    <div v-if="mapUrl" class="position-relative">
      <img :src="mapUrl" alt="Mapa origen y destino" class="w-100" style="display:block; max-height: 260px; object-fit: cover;">
    </div>
    <div
      v-else class="d-flex align-center justify-center text-medium-emphasis"
      style="height: 160px; background: rgba(var(--v-theme-on-surface), 0.04);"
    >
      <div class="text-center px-4">
        <VIcon icon="ri-map-2-line" size="32" class="mb-1" />
        <div class="text-caption">El mapa aparece cuando cargás origen y destino</div>
      </div>
    </div>

    <VCardText>
      <div v-if="serviceLabel" class="text-overline text-primary mb-2">{{ serviceLabel }}</div>

      <div class="d-flex align-start ga-2 mb-2">
        <VIcon icon="ri-record-circle-line" color="success" size="16" class="mt-1" />
        <div>
          <div class="text-caption text-medium-emphasis">Origen</div>
          <div class="text-body-2 font-weight-medium">{{ origin?.district || 'Por definir' }}</div>
        </div>
      </div>
      <div class="d-flex align-start ga-2 mb-3">
        <VIcon icon="ri-map-pin-fill" color="error" size="16" class="mt-1" />
        <div>
          <div class="text-caption text-medium-emphasis">Destino</div>
          <div class="text-body-2 font-weight-medium">{{ destination?.district || 'Por definir' }}</div>
        </div>
      </div>

      <VDivider class="mb-3" />

      <div v-if="detail" class="mb-2">
        <div class="text-caption text-medium-emphasis">Qué llevás</div>
        <div class="text-body-2">{{ detail }}</div>
      </div>
      <div v-if="truckLabel" class="mb-2">
        <div class="text-caption text-medium-emphasis">Vehículo</div>
        <div class="text-body-2">{{ truckLabel }}</div>
      </div>
      <div v-if="fmtDate(date)">
        <div class="text-caption text-medium-emphasis">Fecha</div>
        <div class="text-body-2 text-capitalize">{{ fmtDate(date) }}</div>
      </div>

      <p class="text-caption text-medium-emphasis mt-4 mb-0">
        La dirección exacta (calle, número, piso) te la pedimos recién al reservar.
      </p>
    </VCardText>
  </VCard>
</template>
