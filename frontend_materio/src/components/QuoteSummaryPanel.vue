<script setup>
// Panel de resumen (columna derecha del cotizador): tarjeta "Resumen del
// servicio" + mapa con la ruta real dibujada (Mapbox Directions), para que
// el cliente sienta que "ve" su solicitud mientras la completa. Colores de
// los puntos tomados del tema (success/primary), no inventados.
import { computed, ref, watch } from 'vue'

import { extractVolumeM3, extractWeightKg } from '@/utils/cargoText'

const props = defineProps({
  serviceLabel: { type: String, default: '' },
  origin: { type: Object, default: () => ({}) },
  destination: { type: Object, default: () => ({}) },
  stops: { type: Array, default: () => [] },
  detail: { type: String, default: '' },
  date: { type: String, default: '' },
  truckLabel: { type: String, default: '' },
})
const emit = defineEmits(['edit-type'])

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || ''
const COLOR_ORIGIN = '56CA00'    // theme success
const COLOR_DEST = '8C57FF'      // theme primary
const COLOR_STOP = 'F9A825'

const hasOrigin = computed(() => props.origin?.lat != null && props.origin?.lng != null)
const hasDestination = computed(() => props.destination?.lat != null && props.destination?.lng != null)
const validStops = computed(() => (props.stops || []).filter(s => s?.district))

// Ruta real (distancia/duración + geometría) vía Mapbox Directions — se
// recalcula cuando cambian origen/destino, con debounce para no disparar un
// fetch por cada carácter tipeado en el autocomplete.
const route = ref(null)
let routeDebounce = null

const fetchRoute = async () => {
  if (!hasOrigin.value || !hasDestination.value || !MAPBOX_TOKEN) { route.value = null; return }
  try {
    const url = `https://api.mapbox.com/directions/v5/mapbox/driving/` +
      `${props.origin.lng},${props.origin.lat};${props.destination.lng},${props.destination.lat}` +
      `?geometries=polyline&overview=simplified&access_token=${MAPBOX_TOKEN}`
    const res = await fetch(url)
    const data = await res.json()
    const r = data.routes?.[0]
    route.value = r ? { distanceKm: r.distance / 1000, durationMin: r.duration / 60, polyline: r.geometry } : null
  } catch (e) { route.value = null }
}

watch(
  () => [props.origin?.lat, props.origin?.lng, props.destination?.lat, props.destination?.lng].join(','),
  () => { clearTimeout(routeDebounce); routeDebounce = setTimeout(fetchRoute, 400) },
  { immediate: true },
)

const distanceLabel = computed(() => {
  if (!route.value) return null
  const km = Math.round(route.value.distanceKm)
  const totalMin = Math.round(route.value.durationMin)
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  const dur = h > 0 ? `${h} h${m ? ` ${m} min` : ''}` : `${m} min`

  return `${km} km · ${dur} aprox.`
})

const mapUrl = computed(() => {
  if (!MAPBOX_TOKEN) return ''
  const overlays = []
  if (route.value?.polyline) overlays.push(`path-4+${COLOR_DEST}-0.85(${encodeURIComponent(route.value.polyline)})`)
  if (hasOrigin.value) overlays.push(`pin-s-a+${COLOR_ORIGIN}(${props.origin.lng},${props.origin.lat})`)
  validStops.value.forEach(s => {
    if (s.lat != null && s.lng != null) overlays.push(`pin-s+${COLOR_STOP}(${s.lng},${s.lat})`)
  })
  if (hasDestination.value) overlays.push(`pin-s-b+${COLOR_DEST}(${props.destination.lng},${props.destination.lat})`)
  if (!overlays.length) return ''

  return `https://api.mapbox.com/styles/v1/mapbox/streets-v12/static/${overlays.join(',')}/auto/640x420@2x` +
    `?padding=50&access_token=${MAPBOX_TOKEN}`
})

const weightVolumeLabel = computed(() => {
  const w = extractWeightKg(props.detail)
  const v = extractVolumeM3(props.detail)
  if (w == null && v == null) return null
  const parts = []
  if (w != null) parts.push(`Peso total: ${Math.round(w)} kg`)
  if (v != null) parts.push(`Volumen total: ${v} m³`)

  return parts.join(' · ')
})

const fmtDate = iso => {
  if (!iso) return null
  try {
    return new Date(`${iso}T00:00:00`).toLocaleDateString('es-PE', { weekday: 'long', day: 'numeric', month: 'long' })
  } catch { return iso }
}
</script>

<template>
  <VCard variant="outlined" class="mb-4">
    <VCardText>
      <div class="d-flex align-center justify-space-between mb-3">
        <span class="text-subtitle-1 font-weight-bold">Resumen del servicio</span>
        <VChip
          v-if="serviceLabel" size="small" variant="tonal" color="primary"
          append-icon="ri-pencil-line" style="cursor:pointer;" @click="emit('edit-type')"
        >
          Tipo: {{ serviceLabel }}
        </VChip>
      </div>

      <div class="d-flex align-start ga-2 mb-2">
        <div class="mt-1 flex-shrink-0" style="width:10px; height:10px; border-radius:50%; background:#56CA00;" />
        <div>
          <div class="text-caption text-medium-emphasis">Origen</div>
          <div class="text-body-2 font-weight-medium">{{ origin?.district || 'Por definir' }}</div>
        </div>
      </div>
      <div v-for="(s, i) in validStops" :key="i" class="d-flex align-start ga-2 mb-2">
        <div class="mt-1 flex-shrink-0" style="width:10px; height:10px; border-radius:50%; background:#F9A825;" />
        <div>
          <div class="text-caption text-medium-emphasis">Parada {{ i + 1 }}</div>
          <div class="text-body-2 font-weight-medium">{{ s.district }}</div>
        </div>
      </div>
      <div class="d-flex align-start ga-2">
        <div class="mt-1 flex-shrink-0" style="width:10px; height:10px; border-radius:50%; background:#8C57FF;" />
        <div>
          <div class="text-caption text-medium-emphasis">Destino</div>
          <div class="text-body-2 font-weight-medium">{{ destination?.district || 'Por definir' }}</div>
        </div>
      </div>
      <div v-if="distanceLabel" class="text-caption text-medium-emphasis mt-1" style="padding-left: 18px;">
        {{ distanceLabel }}
      </div>

      <template v-if="detail || weightVolumeLabel || truckLabel || fmtDate(date)">
        <VDivider class="my-3" />
        <div v-if="detail" class="mb-2">
          <div class="text-caption text-medium-emphasis">Descripción</div>
          <div class="text-body-2">{{ detail }}</div>
        </div>
        <div v-if="weightVolumeLabel" class="mb-2">
          <div class="text-caption text-medium-emphasis">Peso / volumen</div>
          <div class="text-body-2">{{ weightVolumeLabel }}</div>
        </div>
        <div v-if="truckLabel" class="mb-2">
          <div class="text-caption text-medium-emphasis">Vehículo</div>
          <div class="text-body-2">{{ truckLabel }}</div>
        </div>
        <div v-if="fmtDate(date)">
          <div class="text-caption text-medium-emphasis">Fecha</div>
          <div class="text-body-2 text-capitalize">{{ fmtDate(date) }}</div>
        </div>
      </template>
    </VCardText>
  </VCard>

  <VCard variant="outlined" class="position-relative overflow-hidden">
    <img v-if="mapUrl" :src="mapUrl" alt="Mapa de ruta" class="w-100" style="display:block; height:360px; object-fit:cover;">
    <div
      v-else class="d-flex align-center justify-center text-medium-emphasis"
      style="height:220px; background:rgba(var(--v-theme-on-surface), 0.04);"
    >
      <div class="text-center px-4">
        <VIcon icon="ri-map-2-line" size="32" class="mb-1" />
        <div class="text-caption">El mapa aparece cuando cargás origen y destino</div>
      </div>
    </div>

    <VCard
      v-if="mapUrl" variant="elevated" class="position-absolute pa-3 d-flex ga-2"
      style="left:12px; right:12px; bottom:12px; max-width:300px;"
    >
      <VIcon icon="ri-map-2-line" size="18" class="mt-1" />
      <div>
        <div class="text-body-2 font-weight-medium">Mapa de ruta</div>
        <div class="text-caption text-medium-emphasis">La ruta se mostrará con más detalle en los siguientes pasos.</div>
      </div>
    </VCard>
  </VCard>
</template>
