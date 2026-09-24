<script setup>
// Mapa interactivo de corredores — vista de solo consulta (la edición sigue
// siendo en configuracion/corredores/index.vue). Dibuja el trazado real de
// los 40 corredores a la vez (cada uno ya calculado vía Mapbox Directions,
// ver calcular_tramos_corredores) y permite:
//   1) Tocar un corredor en la lista para resaltarlo en el mapa.
//   2) Buscar "¿qué corredores cubren este trayecto?" (origen/destino) —
//      reusa el mismo endpoint de detección de corredores compartidos que
//      ya expone el backend (apps.tercerizacion.corredores.detectar_corredores_compartidos).
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { corridorSharedRoutes, corridors, localities } from '@/services/publicationService'

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || ''
const LIMA_CENTER = [-77.0428, -12.0464]
const SOURCE_ALL = 'corridors-all'
const SOURCE_FOCUS = 'corridors-focus'

// Paleta fija (no colores inventados por corredor) — se cicla por índice,
// suficiente para distinguir rutas vecinas a simple vista sin depender de
// azar de render.
const PALETTE = [
  '#8C57FF', '#56CA00', '#FF4C51', '#FFB400', '#16B1FF', '#EB3EA5',
  '#7367F0', '#26C6DA', '#FB8C00', '#8A2BE2', '#2E7D32', '#C2185B',
]

const loading = ref(true)
const list = ref([])
const localityList = ref([])
const search = ref('')
const focused = ref(null)   // corredor actualmente resaltado (o null = ninguno)

const filteredList = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return list.value

  return list.value.filter(c => `${c.code} ${c.name}`.toLowerCase().includes(q))
})

// -- consulta "que corredores cubren este trayecto" ----------------------
const query = ref({ origin: null, destination: null })
const queryLoading = ref(false)
const queryResult = ref(null)   // null = todavia no se consulto
const queryError = ref('')
const localityItems = computed(() => localityList.value.map(l => ({
  title: l.department ? `${l.name} (${l.department})` : l.name, value: l.name,
})))

const runQuery = async () => {
  if (!query.value.origin || !query.value.destination) return
  queryLoading.value = true
  queryError.value = ''
  try {
    const r = await corridorSharedRoutes(query.value.origin, query.value.destination)
    if (!r.originResolved || !r.destinationResolved) {
      queryError.value = 'No se pudo resolver una de las dos localidades.'
      queryResult.value = null
    } else {
      queryResult.value = r
    }
  } catch (e) { queryError.value = e.message || 'No se pudo consultar.' } finally { queryLoading.value = false }
  drawFocusFromQuery()
}

// -- mapa ------------------------------------------------------------------
const mapEl = ref(null)
const map = ref(null)
const mapReady = ref(false)
let queryMarkers = []

const corridorColor = c => PALETTE[list.value.findIndex(x => x.id === c.id) % PALETTE.length]

const allFeatures = () => list.value
  .filter(c => c.trace?.length > 1)
  .map(c => ({
    type: 'Feature',
    properties: { id: c.id, code: c.code, name: c.name },
    geometry: { type: 'LineString', coordinates: c.trace },
  }))

const ensureLayers = () => {
  if (!map.value.getSource(SOURCE_ALL)) {
    map.value.addSource(SOURCE_ALL, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    map.value.addLayer({
      id: SOURCE_ALL, type: 'line', source: SOURCE_ALL,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': ['get', 'color'], 'line-width': 2, 'line-opacity': 0.55 },
    })
  }
  if (!map.value.getSource(SOURCE_FOCUS)) {
    map.value.addSource(SOURCE_FOCUS, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    map.value.addLayer({
      id: SOURCE_FOCUS, type: 'line', source: SOURCE_FOCUS,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': ['get', 'color'], 'line-width': 5, 'line-opacity': 0.95 },
    })
  }
}

const redrawAll = () => {
  if (!mapReady.value) return
  const features = allFeatures().map(f => ({ ...f, properties: { ...f.properties, color: corridorColor(f.properties) } }))
  map.value.getSource(SOURCE_ALL).setData({ type: 'FeatureCollection', features })
}

const clearQueryMarkers = () => { queryMarkers.forEach(m => m.remove()); queryMarkers = [] }

const drawFocus = corredor => {
  if (!mapReady.value) return
  clearQueryMarkers()
  if (!corredor || !corredor.trace?.length) {
    map.value.getSource(SOURCE_FOCUS).setData({ type: 'FeatureCollection', features: [] })
    return
  }
  const color = corridorColor(corredor)
  map.value.getSource(SOURCE_FOCUS).setData({
    type: 'FeatureCollection',
    features: [{ type: 'Feature', properties: { color }, geometry: { type: 'LineString', coordinates: corredor.trace } }],
  })
  corredor.stops.forEach(s => {
    queryMarkers.push(new mapboxgl.Marker({ color, scale: 0.7 }).setLngLat([s.lng, s.lat]).addTo(map.value))
  })
  const bounds = corredor.trace.reduce((b, p) => b.extend(p), new mapboxgl.LngLatBounds(corredor.trace[0], corredor.trace[0]))
  map.value.fitBounds(bounds, { padding: 60, duration: 500 })
}

const drawFocusFromQuery = () => {
  if (!mapReady.value || !queryResult.value) return
  clearQueryMarkers()
  const codes = new Set(queryResult.value.corridors.map(c => c.code))
  const features = list.value
    .filter(c => codes.has(c.code) && c.trace?.length > 1)
    .map(c => ({ type: 'Feature', properties: { color: corridorColor(c) }, geometry: { type: 'LineString', coordinates: c.trace } }))
  map.value.getSource(SOURCE_FOCUS).setData({ type: 'FeatureCollection', features })

  const { origin, destination } = queryResult.value
  queryMarkers.push(new mapboxgl.Marker({ color: '#56CA00' }).setLngLat([origin.lng, origin.lat]).addTo(map.value))
  queryMarkers.push(new mapboxgl.Marker({ color: '#FF4C51' }).setLngLat([destination.lng, destination.lat]).addTo(map.value))
  const bounds = new mapboxgl.LngLatBounds([origin.lng, origin.lat], [origin.lng, origin.lat]).extend([destination.lng, destination.lat])
  map.value.fitBounds(bounds, { padding: 100, duration: 500 })
}

const focusCorridor = c => {
  focused.value = focused.value?.id === c.id ? null : c
  queryResult.value = null
  drawFocus(focused.value)
}

const load = async () => {
  loading.value = true
  try {
    const [corridorsRes, localitiesRes] = await Promise.all([corridors(), localities()])
    list.value = corridorsRes.corridors.filter(c => c.active)
    localityList.value = localitiesRes.localities
  } finally { loading.value = false }
  redrawAll()
}

onMounted(async () => {
  await load()
  if (!MAPBOX_TOKEN || !mapEl.value) return
  map.value = new mapboxgl.Map({ container: mapEl.value, style: 'mapbox://styles/mapbox/streets-v12', center: LIMA_CENTER, zoom: 5 })
  map.value.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'bottom-right')
  map.value.on('load', () => {
    mapReady.value = true
    ensureLayers()
    redrawAll()
    map.value.on('click', SOURCE_ALL, e => {
      const props = e.features[0]?.properties
      const c = list.value.find(x => x.id === props.id)
      if (c) focusCorridor(c)
    })
    map.value.on('mouseenter', SOURCE_ALL, () => { map.value.getCanvas().style.cursor = 'pointer' })
    map.value.on('mouseleave', SOURCE_ALL, () => { map.value.getCanvas().style.cursor = '' })
  })
})

onBeforeUnmount(() => { clearQueryMarkers(); map.value?.remove() })
</script>

<template>
  <section>
    <div class="d-flex align-center mb-1">
      <h1 class="text-h4 font-weight-bold">Mapa de corredores</h1>
      <VSpacer />
      <VBtn variant="text" prepend-icon="ri-list-check-2" to="/configuracion/corredores">Ver lista / editar</VBtn>
    </div>
    <p class="text-body-2 text-medium-emphasis mb-4" style="max-width: 80ch;">
      Trazado real de los {{ list.length }} corredores activos. Tocá una ruta (en el mapa o en la lista) para
      resaltarla, o buscá dos localidades para ver qué corredores cubren ese trayecto.
    </p>

    <VProgressLinear v-if="loading" indeterminate class="mb-4" />

    <VRow v-else>
      <VCol cols="12" md="4" lg="3">
        <VCard variant="outlined" class="mb-3">
          <VCardText>
            <div class="text-subtitle-2 font-weight-bold mb-2">¿Qué corredores cubren este trayecto?</div>
            <VAutocomplete
              v-model="query.origin" :items="localityItems" label="Origen" density="compact" class="mb-2"
              clearable hide-details
            />
            <VAutocomplete
              v-model="query.destination" :items="localityItems" label="Destino" density="compact" class="mb-3"
              clearable hide-details
            />
            <VBtn
              block color="primary" size="small" :loading="queryLoading"
              :disabled="!query.origin || !query.destination" @click="runQuery"
            >
              Buscar
            </VBtn>
            <VAlert v-if="queryError" type="error" variant="tonal" density="compact" class="mt-3">{{ queryError }}</VAlert>
            <template v-if="queryResult">
              <VDivider class="my-3" />
              <div v-if="!queryResult.corridors.length" class="text-caption text-medium-emphasis">
                Ningún corredor cubre ese trayecto en ese sentido.
              </div>
              <template v-else>
                <div class="text-caption text-medium-emphasis mb-1">
                  {{ queryResult.corridors.length }} corredor{{ queryResult.corridors.length === 1 ? '' : 'es' }} lo cubre{{ queryResult.corridors.length === 1 ? '' : 'n' }}:
                </div>
                <VChip
                  v-for="c in queryResult.corridors" :key="c.id" size="small" class="mr-1 mb-1"
                  :color="c.requiresDetour ? 'warning' : 'primary'" variant="tonal"
                >
                  {{ c.code }} {{ c.name }}
                </VChip>
              </template>
            </template>
          </VCardText>
        </VCard>

        <VTextField
          v-model="search" label="Buscar corredor" density="compact" class="mb-2"
          prepend-inner-icon="ri-search-line" clearable hide-details
        />
        <VCard variant="outlined" style="max-height: 480px; overflow-y: auto;">
          <VList density="compact" nav>
            <VListItem
              v-for="c in filteredList" :key="c.id" :active="focused?.id === c.id"
              @click="focusCorridor(c)"
            >
              <template #prepend>
                <span class="d-inline-block" :style="{ width: '10px', height: '10px', borderRadius: '50%', background: corridorColor(c) }" />
              </template>
              <VListItemTitle class="text-body-2">
                <span class="font-weight-medium">{{ c.code }}</span> {{ c.name }}
              </VListItemTitle>
              <VListItemSubtitle class="text-caption">
                {{ c.totalDistanceKm ? `${Math.round(c.totalDistanceKm)} km` : 'sin distancia' }} · {{ c.stops.length }} paradas
              </VListItemSubtitle>
            </VListItem>
          </VList>
        </VCard>
      </VCol>

      <VCol cols="12" md="8" lg="9">
        <VCard variant="outlined" style="height: 640px; position: relative; overflow: hidden;">
          <div ref="mapEl" style="position: absolute; inset: 0;" />
          <div
            v-if="!MAPBOX_TOKEN" class="d-flex align-center justify-center text-medium-emphasis"
            style="position: absolute; inset: 0; background: rgba(var(--v-theme-on-surface), 0.04);"
          >
            Mapa no disponible
          </div>
          <VCard
            v-if="focused" variant="elevated" class="position-absolute pa-3" style="top: 12px; left: 12px; max-width: 320px; z-index: 5;"
          >
            <div class="d-flex align-center ga-2 mb-1">
              <span class="font-weight-bold">{{ focused.code }}</span>
              <span class="font-weight-medium">{{ focused.name }}</span>
            </div>
            <div class="text-caption text-medium-emphasis mb-1">
              {{ focused.totalDistanceKm ? `${Math.round(focused.totalDistanceKm)} km` : 'sin distancia calculada' }}
              · {{ focused.stops.length }} paradas
            </div>
            <div class="text-caption">{{ focused.stops.map(s => s.name).join(' · ') || 'Sin paradas intermedias' }}</div>
          </VCard>
        </VCard>
      </VCol>
    </VRow>
  </section>
</template>
