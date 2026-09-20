<script setup>
// Panel de resumen (columna derecha del cotizador): mapa INTERACTIVO real
// (Mapbox GL JS — zoom/pan con el mouse o los controles) con la ruta
// dibujada (Mapbox Directions), y "Resumen del servicio" flotando encima
// como una tarjeta, no como un bloque aparte. Colores tomados del tema
// (success/primary/warning), no inventados.
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'

import { extractVolumeM3, extractWeightKg } from '@/utils/cargoText'

const props = defineProps({
  serviceLabel: { type: String, default: '' },
  origin: { type: Object, default: () => ({}) },
  destination: { type: Object, default: () => ({}) },
  stops: { type: Array, default: () => [] },
  detail: { type: String, default: '' },
  date: { type: String, default: '' },
  truckLabel: { type: String, default: '' },
  // Peso/volumen ya resuelto por el padre (regex o estimación por IA — ver
  // apps/cotizador/services_estimacion.py) — se prioriza sobre volver a
  // extraerlo acá con regex solamente, que se perdería la estimación de IA.
  estimatedWeightKg: { type: Number, default: null },
  estimatedVolumeM3: { type: Number, default: null },
  // Precio de referencia (un solo número, un rango, o "un asesor confirma")
  // — ver cotizar.vue::priceEstimate. null = Carga sin datos suficientes
  // todavía, o no es Carga.
  priceEstimate: { type: Object, default: null },
})
const emit = defineEmits(['edit-type'])

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || ''
const COLOR_ORIGIN = '#56CA00'    // theme success
const COLOR_DEST = '#8C57FF'      // theme primary
const COLOR_STOP = '#F9A825'      // theme warning
const LIMA_CENTER = [-77.0428, -12.0464]
const ROUTE_SOURCE = 'route-line'

if (MAPBOX_TOKEN) mapboxgl.accessToken = MAPBOX_TOKEN

const hasOrigin = computed(() => props.origin?.lat != null && props.origin?.lng != null)
const hasDestination = computed(() => props.destination?.lat != null && props.destination?.lng != null)
const validStops = computed(() => (props.stops || []).filter(s => s?.district && s.lat != null && s.lng != null))

const mapEl = ref(null)
const map = shallowRef(null)
const mapReady = ref(false)
let markers = []

const clearMarkers = () => { markers.forEach(m => m.remove()); markers = [] }

const ensureRouteLayer = () => {
  if (map.value.getSource(ROUTE_SOURCE)) return
  map.value.addSource(ROUTE_SOURCE, {
    type: 'geojson', data: { type: 'Feature', geometry: { type: 'LineString', coordinates: [] } },
  })
  map.value.addLayer({
    id: ROUTE_SOURCE, type: 'line', source: ROUTE_SOURCE,
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': COLOR_DEST, 'line-width': 4, 'line-opacity': 0.85 },
  })
}

// Ruta real (distancia/duración + geometría) vía Mapbox Directions — se
// recalcula cuando cambian origen/destino, con debounce para no disparar un
// fetch por cada carácter tipeado en el autocomplete.
const route = ref(null)
let routeDebounce = null

const updateRouteLayer = () => {
  if (!mapReady.value) return
  ensureRouteLayer()
  map.value.getSource(ROUTE_SOURCE).setData({
    type: 'Feature', geometry: { type: 'LineString', coordinates: route.value?.coordinates || [] },
  })
}

const fetchRoute = async () => {
  if (!hasOrigin.value || !hasDestination.value || !MAPBOX_TOKEN) { route.value = null; updateRouteLayer(); return }
  try {
    const url = `https://api.mapbox.com/directions/v5/mapbox/driving/` +
      `${props.origin.lng},${props.origin.lat};${props.destination.lng},${props.destination.lat}` +
      `?geometries=geojson&overview=simplified&access_token=${MAPBOX_TOKEN}`
    const res = await fetch(url)
    const data = await res.json()
    const r = data.routes?.[0]
    route.value = r ? { distanceKm: r.distance / 1000, durationMin: r.duration / 60, coordinates: r.geometry.coordinates } : null
  } catch (e) { route.value = null }
  updateRouteLayer()
}

const updateMarkers = () => {
  if (!mapReady.value) return
  clearMarkers()
  if (hasOrigin.value) markers.push(new mapboxgl.Marker({ color: COLOR_ORIGIN }).setLngLat([props.origin.lng, props.origin.lat]).addTo(map.value))
  validStops.value.forEach(s => markers.push(new mapboxgl.Marker({ color: COLOR_STOP }).setLngLat([s.lng, s.lat]).addTo(map.value)))
  if (hasDestination.value) markers.push(new mapboxgl.Marker({ color: COLOR_DEST }).setLngLat([props.destination.lng, props.destination.lat]).addTo(map.value))
}

// El mapa recién es visible por debajo de la tarjeta "Resumen del servicio"
// (flota arriba) — el padding del fitBounds evita que la ruta quede tapada.
const fitToRoute = () => {
  if (!mapReady.value) return
  const points = []
  if (hasOrigin.value) points.push([props.origin.lng, props.origin.lat])
  validStops.value.forEach(s => points.push([s.lng, s.lat]))
  if (hasDestination.value) points.push([props.destination.lng, props.destination.lat])
  if (!points.length) return
  if (points.length === 1) { map.value.flyTo({ center: points[0], zoom: 12 }); return }
  const bounds = points.reduce((b, p) => b.extend(p), new mapboxgl.LngLatBounds(points[0], points[0]))
  map.value.fitBounds(bounds, { padding: { top: 170, bottom: 40, left: 40, right: 40 }, maxZoom: 14, duration: 600 })
}

watch(
  () => [props.origin?.lat, props.origin?.lng, props.destination?.lat, props.destination?.lng, validStops.value.length].join(','),
  () => {
    updateMarkers()
    fitToRoute()
    clearTimeout(routeDebounce)
    routeDebounce = setTimeout(fetchRoute, 400)
  },
)

onMounted(() => {
  if (!MAPBOX_TOKEN || !mapEl.value) return
  map.value = new mapboxgl.Map({
    container: mapEl.value, style: 'mapbox://styles/mapbox/streets-v12', center: LIMA_CENTER, zoom: 10,
  })
  map.value.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'bottom-right')
  map.value.on('load', () => {
    mapReady.value = true
    ensureRouteLayer()
    updateMarkers()
    fitToRoute()
  })
})

onBeforeUnmount(() => {
  clearTimeout(routeDebounce)
  clearMarkers()
  map.value?.remove()
})

const distanceLabel = computed(() => {
  if (!route.value) return null
  const km = Math.round(route.value.distanceKm)
  const totalMin = Math.round(route.value.durationMin)
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  const dur = h > 0 ? `${h} h${m ? ` ${m} min` : ''}` : `${m} min`

  return `${km} km · ${dur} aprox.`
})

const weightVolumeLabel = computed(() => {
  const w = props.estimatedWeightKg ?? extractWeightKg(props.detail)
  const v = props.estimatedVolumeM3 ?? extractVolumeM3(props.detail)
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
  <VCard variant="outlined" class="h-100 position-relative overflow-hidden" style="min-height: 560px;">
    <div ref="mapEl" class="position-absolute" style="inset: 0;" />
    <div
      v-if="!MAPBOX_TOKEN" class="position-absolute d-flex align-center justify-center text-medium-emphasis"
      style="inset: 0; background: rgba(var(--v-theme-on-surface), 0.04);"
    >
      <div class="text-center px-4">
        <VIcon icon="ri-map-2-line" size="32" class="mb-1" />
        <div class="text-caption">Mapa no disponible</div>
      </div>
    </div>

    <!-- "Resumen del servicio" flota sobre el mapa, no ocupa un bloque
         aparte — el mapa abarca todo el panel. -->
    <VCard variant="elevated" class="position-absolute pa-4" style="top: 12px; left: 12px; right: 12px;">
      <div class="d-flex align-center justify-space-between mb-3">
        <span class="text-subtitle-1 font-weight-bold">Resumen del servicio</span>
        <VChip
          v-if="serviceLabel" size="small" variant="tonal" color="primary"
          append-icon="ri-pencil-line" style="cursor:pointer;" @click="emit('edit-type')"
        >
          Tipo: {{ serviceLabel }}
        </VChip>
      </div>

      <div class="d-flex align-center flex-wrap ga-1 mb-1">
        <div class="d-flex align-center ga-1">
          <div class="flex-shrink-0" style="width:9px; height:9px; border-radius:50%; background:#56CA00;" />
          <span class="text-body-2 font-weight-medium">{{ origin?.district || 'Por definir' }}</span>
        </div>
        <template v-for="(s, i) in validStops" :key="i">
          <VIcon icon="ri-arrow-right-line" size="14" class="text-medium-emphasis" />
          <div class="d-flex align-center ga-1">
            <div class="flex-shrink-0" style="width:9px; height:9px; border-radius:50%; background:#F9A825;" />
            <span class="text-body-2 font-weight-medium">{{ s.district }}</span>
          </div>
        </template>
        <VIcon icon="ri-arrow-right-line" size="14" class="text-medium-emphasis" />
        <div class="d-flex align-center ga-1">
          <div class="flex-shrink-0" style="width:9px; height:9px; border-radius:50%; background:#8C57FF;" />
          <span class="text-body-2 font-weight-medium">{{ destination?.district || 'Por definir' }}</span>
        </div>
      </div>
      <div v-if="distanceLabel" class="text-caption text-medium-emphasis mb-1">
        {{ distanceLabel }}
      </div>

      <template v-if="detail || weightVolumeLabel || truckLabel || fmtDate(date) || priceEstimate">
        <VDivider class="my-3" />
        <div v-if="detail" class="d-flex align-start ga-2 mb-3">
          <VIcon icon="ri-file-text-line" size="16" class="text-medium-emphasis mt-1" />
          <div>
            <div class="summary-label">Descripción de la carga</div>
            <div class="text-body-2 font-weight-medium">{{ detail }}</div>
          </div>
        </div>
        <div v-if="weightVolumeLabel" class="d-flex align-start ga-2 mb-3">
          <VIcon icon="ri-scales-3-line" size="16" class="text-medium-emphasis mt-1" />
          <div>
            <div class="summary-label">Peso / volumen</div>
            <div class="text-body-2 font-weight-medium">{{ weightVolumeLabel }}</div>
          </div>
        </div>
        <div v-if="truckLabel" class="d-flex align-start ga-2 mb-3">
          <VIcon icon="ri-truck-line" size="16" class="text-medium-emphasis mt-1" />
          <div>
            <div class="summary-label">Vehículo elegido</div>
            <div class="text-body-2 font-weight-medium">{{ truckLabel }}</div>
          </div>
        </div>
        <div v-if="fmtDate(date)" class="d-flex align-start ga-2 mb-3">
          <VIcon icon="ri-calendar-line" size="16" class="text-medium-emphasis mt-1" />
          <div>
            <div class="summary-label">Fecha del servicio</div>
            <div class="text-body-2 font-weight-medium text-capitalize">{{ fmtDate(date) }}</div>
          </div>
        </div>
        <div v-if="priceEstimate" class="d-flex align-start ga-2">
          <VIcon icon="ri-price-tag-3-line" size="16" class="text-medium-emphasis mt-1" />
          <div>
            <div class="summary-label">Precio estimado</div>
            <template v-if="priceEstimate.mode === 'loading'">
              <VProgressCircular indeterminate size="14" width="2" color="primary" />
            </template>
            <template v-else>
              <div class="text-body-2 font-weight-medium">{{ priceEstimate.text }}</div>
              <div v-if="priceEstimate.sub" class="text-caption text-medium-emphasis">{{ priceEstimate.sub }}</div>
            </template>
          </div>
        </div>
      </template>
    </VCard>
  </VCard>
</template>

<style scoped>
/* Etiqueta claramente distinta del valor que describe — chica, mayúscula,
   espaciada — para que nunca se confunda con el contenido real (p. ej.
   "Descripción" no debe leerse igual que la descripción en sí). */
.summary-label {
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  margin-bottom: 2px;
}
</style>
