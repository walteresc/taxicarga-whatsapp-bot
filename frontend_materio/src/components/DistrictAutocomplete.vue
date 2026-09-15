<script setup>
/**
 * Autocompletado de DISTRITO/PROVINCIA/REGIÓN (no dirección exacta) — para
 * cotizar rápido. La dirección completa (calle, número, piso) recién se pide
 * al reservar, no acá: acelera la cotización y evita pedir un dato que en
 * esta etapa no hace falta.
 *
 * v-model = { district, province, region, lat, lng }. Reutiliza el mismo
 * Mapbox Geocoding v6 que AddressAutocomplete, pero acotado a tipos
 * administrativos (place/locality/district/region) — sin direcciones/POIs.
 */
import { onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Object, required: true },
  label: { type: String, default: 'Distrito o provincia' },
})
const emit = defineEmits(['update:modelValue'])

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || ''

const displayText = v => [v?.district, v?.province].filter(Boolean).join(', ')

const query = ref(displayText(props.modelValue))
const suggestions = ref([])
const menuOpen = ref(false)
const loading = ref(false)
const located = ref(!!(props.modelValue?.lat && props.modelValue?.lng))

let debounceTimer = null
let abortCtrl = null

const search = async text => {
  if (!MAPBOX_TOKEN || text.trim().length < 2) { suggestions.value = []; return }
  abortCtrl?.abort()
  abortCtrl = new AbortController()
  loading.value = true
  try {
    // proximity sesgado a Lima Metropolitana: la mayoría de las cotizaciones
    // arrancan ahí, y sin esto un distrito común (p.ej. "San Isidro") puede
    // salir primero de otra región homónima.
    const url = `https://api.mapbox.com/search/geocode/v6/forward?q=${encodeURIComponent(text)}` +
      `&autocomplete=true&country=pe&language=es&limit=6&proximity=-77.0428,-12.0464` +
      `&types=place,locality,district,region&access_token=${MAPBOX_TOKEN}`
    const res = await fetch(url, { signal: abortCtrl.signal })
    const data = await res.json()
    suggestions.value = data.features || []
  } catch (e) {
    if (e.name !== 'AbortError') suggestions.value = []
  } finally { loading.value = false }
}

const onFocus = () => { menuOpen.value = true }

const onInput = value => {
  query.value = value
  located.value = false
  menuOpen.value = true
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => search(value), 300)
}

const pick = feature => {
  const ctx = feature.properties?.context || {}
  const region = ctx.region?.name || ''
  const province = ctx.district?.name || ''
  const dist = ctx.place?.name || ctx.locality?.name || feature.properties?.name || ''
  const [lng, lat] = feature.geometry?.coordinates || [null, null]

  query.value = displayText({ district: dist, province }) || feature.properties?.name || ''
  located.value = lat != null && lng != null
  suggestions.value = []
  menuOpen.value = false
  emit('update:modelValue', { ...props.modelValue, district: dist, province, region, lat, lng })
}

const clear = () => {
  query.value = ''
  located.value = false
  suggestions.value = []
  emit('update:modelValue', { ...props.modelValue, district: '', province: '', region: '', lat: null, lng: null })
}

watch(() => props.modelValue, v => {
  const text = displayText(v)
  if (text !== query.value) query.value = text
  located.value = !!(v?.lat && v?.lng)
}, { deep: true })

onBeforeUnmount(() => { clearTimeout(debounceTimer); abortCtrl?.abort() })
</script>

<template>
  <VMenu v-model="menuOpen" :close-on-content-click="false" location="bottom" :open-on-click="false">
    <template #activator="{ props: menuProps }">
      <VTextField
        v-bind="menuProps"
        :model-value="query" :label="label" density="comfortable"
        prepend-inner-icon="ri-map-pin-line"
        :append-inner-icon="located ? 'ri-map-pin-2-fill' : undefined"
        :color="located ? 'success' : undefined"
        :hint="!MAPBOX_TOKEN ? 'Autocompletado no disponible: escribí el distrito.' : ''"
        persistent-hint clearable
        @click:clear="clear"
        @focus="onFocus"
        @update:model-value="onInput"
      />
    </template>
    <VList density="compact" min-width="260">
      <VListItem v-if="loading" title="Buscando…" />
      <VListItem
        v-else-if="!suggestions.length"
        :title="query.trim().length < 2 ? 'Escribí el distrito o provincia…' : 'Sin resultados — probá con otro nombre.'"
        class="text-medium-emphasis"
      />
      <VListItem
        v-for="f in suggestions" :key="f.properties.mapbox_id"
        :title="f.properties.name" :subtitle="f.properties.place_formatted"
        @click="pick(f)"
      />
    </VList>
  </VMenu>
</template>
