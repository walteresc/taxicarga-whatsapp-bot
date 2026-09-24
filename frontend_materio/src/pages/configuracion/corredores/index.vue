<script setup>
// Corredores de carga nacional (rutas troncales, p. ej. "Lima - Ica - Tacna")
// — deciden cuándo se ofrece Carga Compartida/Consolidada y hasta qué
// parada, cuando el destino se desvía de la ruta (ver
// apps.tercerizacion.corredores.resolver_corredor). CRUD manual (como
// Comisiones), no CrudResourcePage: necesita mapa embebido en el form.
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'

import DistrictAutocomplete from '@/components/DistrictAutocomplete.vue'
import { corridorCreate, corridorDelete, corridors, corridorUpdate } from '@/services/publicationService'

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || ''
const LIMA_CENTER = [-77.0428, -12.0464]

// Estado de la GEOMETRÍA (independiente de "activo", la habilitación
// comercial) — VALIDADO es siempre una aprobación humana explícita, nunca
// se auto-promueve.
const VALIDATION_LABEL = {
  PENDIENTE_TRAZADO: 'Pendiente de trazado', TRAZADO_CALCULADO: 'Trazado calculado',
  PENDIENTE_VALIDACION: 'Pendiente de validación', VALIDADO: 'Validado',
  ERROR_TRAZADO: 'Error de trazado', INACTIVO: 'Inactivo',
}
const VALIDATION_COLOR = {
  PENDIENTE_TRAZADO: 'warning', TRAZADO_CALCULADO: 'info', PENDIENTE_VALIDACION: 'warning',
  VALIDADO: 'success', ERROR_TRAZADO: 'error', INACTIVO: undefined,
}
// Cuántos tramos de este corredor son compartidos con al menos otro
// corredor — advertencia antes de editar (una edición no debería romper
// otro corredor sin avisar).
const tramosCompartidos = c => (c.segments || []).filter(s => s.sharedWithOtherCorridors > 0).length

const search = ref('')
const filterStatus = ref(null)
const filterActive = ref(true)
const statusFilterOptions = Object.entries(VALIDATION_LABEL).map(([value, title]) => ({ title, value }))
const activeFilterOptions = [
  { title: 'Todos', value: null }, { title: 'Activos', value: true }, { title: 'Inactivos', value: false },
]
const filteredList = computed(() => list.value.filter(c => {
  if (filterActive.value !== null && c.active !== filterActive.value) return false
  if (filterStatus.value && c.validationStatus !== filterStatus.value) return false
  const q = search.value.trim().toLowerCase()
  if (q && !`${c.code} ${c.name}`.toLowerCase().includes(q)) return false
  return true
}))

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snackbar, { show: true, text: t, color: c })

const list = ref([])
const loading = ref(true)
const busy = ref(false)

const load = async () => {
  loading.value = true
  try { list.value = (await corridors()).corridors } catch (e) { notify(e.message || 'No se pudo cargar.', 'error') } finally { loading.value = false }
}
onMounted(load)

const emptyPoint = () => ({ district: '', province: '', region: '', address: '', lat: null, lng: null })
const emptyForm = () => ({
  open: false, id: null, name: '', active: true,
  axisToleranceKm: 1, maxDetourKm: 30,
  origin: { ...emptyPoint(), district: 'Lima' },
  destination: emptyPoint(),
  trace: [],
  stops: [],
})
const form = reactive(emptyForm())
const calculatingTrace = ref(false)

const openEdit = c => Object.assign(form, {
  open: true, id: c.id, name: c.name, active: c.active,
  axisToleranceKm: c.axisToleranceKm, maxDetourKm: c.maxDetourKm,
  origin: { ...emptyPoint(), district: c.originLabel || '', lat: c.originLat, lng: c.originLng },
  destination: { ...emptyPoint(), district: c.destinationLabel || '', lat: c.destinationLat, lng: c.destinationLng },
  trace: c.trace || [],
  stops: c.stops.map(s => ({
    name: s.name, radiusKm: s.radiusKm, active: s.active,
    point: { ...emptyPoint(), district: s.name, lat: s.lat, lng: s.lng },
  })),
})
const openCreate = () => { Object.assign(form, emptyForm()); form.open = true }

const addStop = () => form.stops.push({ name: '', radiusKm: 1, active: true, point: emptyPoint() })
const removeStop = i => form.stops.splice(i, 1)
const moveStop = (i, dir) => {
  const j = i + dir
  if (j < 0 || j >= form.stops.length) return
  ;[form.stops[i], form.stops[j]] = [form.stops[j], form.stops[i]]
}
// El nombre de la parada es el texto que después matchea contra
// TarifaCargaParcial.destino — se toma del distrito elegido en el
// autocompletado, no hay que escribirlo dos veces.
watch(() => form.stops.map(s => s.point.district), districts => {
  districts.forEach((d, i) => { if (d) form.stops[i].name = d })
}, { deep: true })

// --- mapa (mismo patrón que QuoteSummaryPanel.vue: GeoJSON LineString + Marker) ---
const mapEl = ref(null)
const map = ref(null)
const mapReady = ref(false)
const ROUTE_SOURCE = 'corridor-route'
let markers = []

const ensureRouteLayer = () => {
  if (map.value.getSource(ROUTE_SOURCE)) return
  map.value.addSource(ROUTE_SOURCE, { type: 'geojson', data: { type: 'Feature', geometry: { type: 'LineString', coordinates: [] } } })
  map.value.addLayer({
    id: ROUTE_SOURCE, type: 'line', source: ROUTE_SOURCE,
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': '#8C57FF', 'line-width': 4, 'line-opacity': 0.85 },
  })
}
const clearMarkers = () => { markers.forEach(m => m.remove()); markers = [] }
const redrawMap = () => {
  if (!mapReady.value) return
  ensureRouteLayer()
  map.value.getSource(ROUTE_SOURCE).setData({ type: 'Feature', geometry: { type: 'LineString', coordinates: form.trace || [] } })
  clearMarkers()
  const points = []
  if (form.origin.lat != null) { markers.push(new mapboxgl.Marker({ color: '#56CA00' }).setLngLat([form.origin.lng, form.origin.lat]).addTo(map.value)); points.push([form.origin.lng, form.origin.lat]) }
  form.stops.forEach(s => {
    if (s.point.lat == null) return
    markers.push(new mapboxgl.Marker({ color: '#F9A825' }).setLngLat([s.point.lng, s.point.lat]).addTo(map.value))
    points.push([s.point.lng, s.point.lat])
  })
  if (form.destination.lat != null) { markers.push(new mapboxgl.Marker({ color: '#8C57FF' }).setLngLat([form.destination.lng, form.destination.lat]).addTo(map.value)); points.push([form.destination.lng, form.destination.lat]) }
  if (points.length > 1) {
    const bounds = points.reduce((b, p) => b.extend(p), new mapboxgl.LngLatBounds(points[0], points[0]))
    map.value.fitBounds(bounds, { padding: 40, maxZoom: 12, duration: 400 })
  } else if (points.length === 1) {
    map.value.flyTo({ center: points[0], zoom: 10 })
  }
}

// El mapa se crea recién cuando el diálogo abre (el contenedor no existe
// hasta entonces) — se destruye al cerrar, así no queda un mapa Mapbox vivo
// por cada vez que se abre el form.
watch(() => form.open, async open => {
  if (!open || !MAPBOX_TOKEN) return
  await nextTick()
  if (!mapEl.value) return
  map.value = new mapboxgl.Map({ container: mapEl.value, style: 'mapbox://styles/mapbox/streets-v12', center: LIMA_CENTER, zoom: 5 })
  map.value.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'bottom-right')
  map.value.on('load', () => { mapReady.value = true; redrawMap() })
})
watch(() => form.open, open => {
  if (open) return
  map.value?.remove()
  map.value = null
  mapReady.value = false
})
watch(() => [form.trace, form.origin.lat, form.destination.lat, form.stops.map(s => s.point.lat).join(',')], redrawMap, { deep: true })

const calcularTrazado = async () => {
  if (!MAPBOX_TOKEN || form.origin.lat == null || form.destination.lat == null) return
  calculatingTrace.value = true
  try {
    const url = `https://api.mapbox.com/directions/v5/mapbox/driving/` +
      `${form.origin.lng},${form.origin.lat};${form.destination.lng},${form.destination.lat}` +
      `?geometries=geojson&overview=full&access_token=${MAPBOX_TOKEN}`
    const res = await fetch(url)
    const data = await res.json()
    const r = data.routes?.[0]
    if (r) { form.trace = r.geometry.coordinates; notify('Trazado calculado.') }
    else notify('Mapbox no encontró una ruta entre esos puntos.', 'error')
  } catch (e) { notify('No se pudo calcular el trazado.', 'error') } finally { calculatingTrace.value = false }
}

const save = async () => {
  if (!form.name.trim()) { notify('Ponele un nombre al corredor.', 'error'); return }
  busy.value = true
  const body = {
    name: form.name, active: form.active,
    axisToleranceKm: form.axisToleranceKm, maxDetourKm: form.maxDetourKm,
    originLabel: form.origin.district, originLat: form.origin.lat, originLng: form.origin.lng,
    destinationLabel: form.destination.district, destinationLat: form.destination.lat, destinationLng: form.destination.lng,
    trace: form.trace,
    stops: form.stops.map(s => ({ name: s.name, lat: s.point.lat, lng: s.point.lng, radiusKm: s.radiusKm, active: s.active })),
  }
  try {
    if (form.id) await corridorUpdate(form.id, body)
    else await corridorCreate(body)
    form.open = false
    notify('Corredor guardado.')
    await load()
  } catch (e) { notify(e.message || 'Revisá los datos.', 'error') } finally { busy.value = false }
}

const remove = async c => {
  if (!confirm(`¿Eliminar el corredor "${c.name}" y sus ${c.stops.length} paradas?`)) return
  busy.value = true
  try { await corridorDelete(c.id); notify('Corredor eliminado.'); await load() }
  catch (e) { notify(e.message || 'No se pudo eliminar.', 'error') } finally { busy.value = false }
}
</script>

<template>
  <section>
    <div class="d-flex align-center mb-1 ga-2">
      <h1 class="text-h4 font-weight-bold">Corredores de carga nacional</h1>
      <VSpacer />
      <VBtn variant="tonal" prepend-icon="ri-map-2-line" to="/configuracion/corredores/mapa">Ver mapa</VBtn>
      <VBtn color="primary" prepend-icon="ri-add-line" @click="openCreate">Nuevo corredor</VBtn>
    </div>
    <p class="text-body-2 text-medium-emphasis mb-4" style="max-width: 70ch;">
      Rutas troncales (p. ej. "Lima - Ica - Tacna") con las ciudades atendidas en el trayecto. Si el destino de una
      carga cae dentro del radio de una parada (o sobre el eje de la ruta) se ofrece Compartida; si se desvía de la
      ruta, la Compartida llega solo hasta la última parada alcanzable — el resto se cotiza como Exclusivo.
    </p>

    <VProgressLinear v-if="loading" indeterminate class="mb-4" />

    <template v-else>
      <div class="d-flex ga-3 mb-4 flex-wrap">
        <VTextField
          v-model="search" label="Buscar por código o nombre" density="compact" style="max-width: 280px;"
          prepend-inner-icon="ri-search-line" clearable hide-details
        />
        <VSelect
          v-model="filterStatus" :items="statusFilterOptions" label="Estado" density="compact"
          style="max-width: 220px;" clearable hide-details
        />
        <VSelect
          v-model="filterActive" :items="activeFilterOptions" label="Activo" density="compact"
          style="max-width: 160px;" hide-details
        />
      </div>

      <VCard variant="outlined">
        <VTable>
          <thead>
            <tr>
              <th>Código</th><th>Nombre</th><th>Variante</th><th>Estado</th>
              <th class="text-right">Paradas</th><th class="text-right">Distancia</th>
              <th>Compartido</th><th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in filteredList" :key="c.id" :class="{ 'text-disabled': !c.active }">
              <td class="font-weight-medium">{{ c.code || '—' }}</td>
              <td>{{ c.name }}</td>
              <td>{{ c.variant || '—' }}</td>
              <td>
                <VChip size="x-small" :color="c.active ? VALIDATION_COLOR[c.validationStatus] : undefined" variant="tonal">
                  {{ c.active ? (VALIDATION_LABEL[c.validationStatus] || c.validationStatus) : 'Inactivo' }}
                </VChip>
              </td>
              <td class="text-right">{{ c.stops.length }}</td>
              <td class="text-right">{{ c.totalDistanceKm ? `${Math.round(c.totalDistanceKm)} km` : '—' }}</td>
              <td>
                <span v-if="tramosCompartidos(c) > 0" class="text-caption text-primary">
                  <VIcon icon="ri-share-line" size="12" /> {{ tramosCompartidos(c) }} tramo{{ tramosCompartidos(c) === 1 ? '' : 's' }}
                </span>
                <span v-else class="text-caption text-medium-emphasis">—</span>
              </td>
              <td class="text-right text-no-wrap">
                <VBtn icon="ri-pencil-line" size="x-small" variant="text" @click="openEdit(c)" />
                <VBtn icon="ri-delete-bin-line" size="x-small" variant="text" color="error" @click="remove(c)" />
              </td>
            </tr>
            <tr v-if="!filteredList.length">
              <td colspan="8" class="text-center text-medium-emphasis py-6">
                {{ list.length ? 'Ningún corredor coincide con el filtro.' : 'Todavía no hay corredores cargados.' }}
              </td>
            </tr>
          </tbody>
        </VTable>
      </VCard>
    </template>

    <VDialog v-model="form.open" max-width="900" scrollable>
      <VCard>
        <VCardTitle>{{ form.id ? 'Editar corredor' : 'Nuevo corredor' }}</VCardTitle>
        <VCardText style="max-height: 75vh;">
          <VRow dense>
            <VCol cols="12" sm="8">
              <VTextField v-model="form.name" label="Nombre del corredor" density="comfortable" />
            </VCol>
            <VCol cols="12" sm="4" class="d-flex align-center">
              <VCheckbox v-model="form.active" label="Activo" density="compact" hide-details />
            </VCol>
            <VCol cols="6">
              <VTextField
                v-model.number="form.axisToleranceKm" label="Tolerancia del eje (km)" type="number" density="comfortable"
                hint="Cuán lejos de la carretera puede caer un punto sin ciudad propia y seguir contando como 'sobre la ruta'."
                persistent-hint
              />
            </VCol>
            <VCol cols="6">
              <VTextField
                v-model.number="form.maxDetourKm" label="Desvío máximo (km)" type="number" density="comfortable"
                hint="Más allá de esto, el punto ya no tiene nada que ver con este corredor — solo Exclusivo."
                persistent-hint
              />
            </VCol>
          </VRow>

          <VDivider class="my-4" />
          <div class="text-subtitle-2 font-weight-bold mb-2">Extremos del corredor</div>
          <VRow dense>
            <VCol cols="12" sm="6">
              <DistrictAutocomplete v-model="form.origin" label="Origen" />
            </VCol>
            <VCol cols="12" sm="6">
              <DistrictAutocomplete v-model="form.destination" label="Destino" />
            </VCol>
          </VRow>
          <VBtn
            class="mt-2" size="small" variant="tonal" prepend-icon="ri-route-line" :loading="calculatingTrace"
            :disabled="form.origin.lat == null || form.destination.lat == null" @click="calcularTrazado"
          >
            Calcular trazado
          </VBtn>
          <span v-if="form.trace.length" class="text-caption text-medium-emphasis ml-2">
            {{ form.trace.length }} puntos calculados
          </span>

          <div class="mt-3" style="height: 260px; border-radius: 8px; overflow: hidden; position: relative;">
            <div ref="mapEl" style="position: absolute; inset: 0;" />
            <div
              v-if="!MAPBOX_TOKEN" class="d-flex align-center justify-center text-medium-emphasis"
              style="position: absolute; inset: 0; background: rgba(var(--v-theme-on-surface), 0.04);"
            >
              Mapa no disponible
            </div>
          </div>

          <VDivider class="my-4" />
          <div class="d-flex align-center mb-2">
            <span class="text-subtitle-2 font-weight-bold">Paradas</span>
            <VSpacer />
            <VBtn size="small" variant="text" prepend-icon="ri-add-line" @click="addStop">Agregar parada</VBtn>
          </div>
          <VCard v-for="(s, i) in form.stops" :key="i" variant="outlined" class="pa-3 mb-2">
            <VRow dense align="center">
              <VCol cols="12" sm="5">
                <DistrictAutocomplete v-model="s.point" label="Ciudad" />
              </VCol>
              <VCol cols="6" sm="3">
                <VTextField v-model.number="s.radiusKm" label="Radio (km)" type="number" density="comfortable" />
              </VCol>
              <VCol cols="6" sm="2" class="d-flex align-center">
                <VCheckbox v-model="s.active" label="Activa" density="compact" hide-details />
              </VCol>
              <VCol cols="12" sm="2" class="d-flex justify-end ga-1">
                <VBtn icon="ri-arrow-up-line" size="small" variant="text" :disabled="i === 0" @click="moveStop(i, -1)" />
                <VBtn icon="ri-arrow-down-line" size="small" variant="text" :disabled="i === form.stops.length - 1" @click="moveStop(i, 1)" />
                <VBtn icon="ri-delete-bin-line" size="small" variant="text" color="error" @click="removeStop(i)" />
              </VCol>
            </VRow>
          </VCard>
          <p v-if="!form.stops.length" class="text-caption text-medium-emphasis">Todavía no hay paradas.</p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="form.open = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="busy" @click="save">Guardar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
