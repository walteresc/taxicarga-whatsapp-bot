<script setup>
/**
 * Autocompletado de direcciones (Mapbox Geocoding v6, Fase "Direcciones" 2026-09).
 *
 * v-model = { address, district, province, region, lat, lng }.
 * El usuario escribe, elige una sugerencia → se llenan distrito/provincia/región/lat/lng.
 * El campo "Distrito" queda SIEMPRE editable: la cobertura de Mapbox en Perú no es
 * perfecta y el mapeo región/provincia/distrito es best-effort (Mapbox no tiene una
 * jerarquía admin 1:1 con departamento/provincia/distrito peruano) — por eso nunca
 * se bloquea la corrección manual, solo se usa para acelerar la captura y para
 * geolocalizar (necesario para detectar carga local vs. nacional por distancia).
 */
import { onBeforeUnmount, reactive, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Object, required: true },
  label: { type: String, default: 'Dirección' },
})
const emit = defineEmits(['update:modelValue'])

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || ''

const query = ref(props.modelValue?.address || '')
const district = ref(props.modelValue?.district || '')
const suggestions = ref([])
const menuOpen = ref(false)
const loading = ref(false)
const located = ref(!!(props.modelValue?.lat && props.modelValue?.lng))

let debounceTimer = null
let abortCtrl = null

const emitValue = patch => {
  emit('update:modelValue', { ...props.modelValue, district: district.value, address: query.value, ...patch })
}

const search = async text => {
  if (!MAPBOX_TOKEN || text.trim().length < 3) { suggestions.value = []; return }
  abortCtrl?.abort()
  abortCtrl = new AbortController()
  loading.value = true
  try {
    const url = `https://api.mapbox.com/search/geocode/v6/forward?q=${encodeURIComponent(text)}` +
      `&autocomplete=true&country=pe&language=es&limit=6&access_token=${MAPBOX_TOKEN}`
    const res = await fetch(url, { signal: abortCtrl.signal })
    const data = await res.json()
    suggestions.value = data.features || []
    menuOpen.value = suggestions.value.length > 0
  } catch (e) {
    if (e.name !== 'AbortError') suggestions.value = []
  } finally { loading.value = false }
}

const onInput = value => {
  query.value = value
  located.value = false
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => search(value), 350)
}

const pick = feature => {
  const ctx = feature.properties?.context || {}
  // Best-effort: la jerarquía de Mapbox no calza 1:1 con región/provincia/distrito
  // del Perú. Se usa como punto de partida; el usuario puede corregir el distrito.
  const region = ctx.region?.name || ''
  const province = ctx.district?.name || ''
  const dist = ctx.place?.name || ctx.locality?.name || ''
  const [lng, lat] = feature.geometry?.coordinates || [null, null]

  query.value = feature.properties?.full_address || feature.properties?.place_formatted || query.value
  district.value = dist
  located.value = lat != null && lng != null
  suggestions.value = []
  menuOpen.value = false
  emitValue({ address: query.value, district: dist, province, region, lat, lng })
}

const onDistrictEdit = value => {
  district.value = value
  emitValue({ district: value })
}

// Si el padre resetea el modelo (p.ej. limpiar el formulario), reflejarlo.
watch(() => props.modelValue, v => {
  if ((v?.address || '') !== query.value) query.value = v?.address || ''
  if ((v?.district || '') !== district.value) district.value = v?.district || ''
  located.value = !!(v?.lat && v?.lng)
}, { deep: true })

onBeforeUnmount(() => { clearTimeout(debounceTimer); abortCtrl?.abort() })
</script>

<template>
  <div>
    <VMenu v-model="menuOpen" :close-on-content-click="false" location="bottom" :open-on-click="false">
      <template #activator="{ props: menuProps }">
        <VTextField
          v-bind="menuProps"
          :model-value="query" :label="label" density="comfortable" class="mb-2"
          :append-inner-icon="located ? 'ri-map-pin-2-fill' : undefined"
          :color="located ? 'success' : undefined"
          :hint="!MAPBOX_TOKEN ? 'Autocompletado no disponible: escribí la dirección completa.' : ''"
          persistent-hint
          @update:model-value="onInput"
        />
      </template>
      <VList density="compact">
        <VListItem v-if="loading" title="Buscando…" />
        <VListItem
          v-for="f in suggestions" :key="f.properties.mapbox_id"
          :title="f.properties.name" :subtitle="f.properties.place_formatted"
          @click="pick(f)"
        />
      </VList>
    </VMenu>
    <VTextField
      :model-value="district" label="Distrito" density="comfortable"
      hint="Se completa solo al elegir una sugerencia — corregilo si no coincide." persistent-hint
      @update:model-value="onDistrictEdit"
    />
  </div>
</template>
