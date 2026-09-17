<script setup>
/**
 * Autocompletado de origen/destino — acepta tanto un DISTRITO/PROVINCIA como
 * una DIRECCIÓN completa en el mismo campo (el cliente puede escribir
 * cualquiera de los dos). Reutiliza el mismo Mapbox Geocoding v6 que
 * AddressAutocomplete, con tipos administrativos + direcciones.
 *
 * v-model = { district, province, region, address, lat, lng }. `district`
 * siempre se resuelve (aunque se haya elegido una dirección puntual) porque
 * el motor de precios y el resto del backend lo necesitan; `address` solo se
 * completa cuando la sugerencia elegida es una dirección puntual.
 */
import { onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Object, required: true },
  label: { type: String, default: 'Distrito o provincia' },
  // El mockup de Carga muestra el campo limpio (sin ícono de pin adentro) y
  // usa un punto de color afuera, en el "riel" origen→destino, para eso.
  hideIcons: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || ''

// Apodos de distritos conocidos que en el geocoder de Mapbox pierden contra
// un lugar homónimo mucho menos conocido (p.ej. escribir solo "Surco" trae
// primero un caserío de la provincia de Yauyos, y "Santiago de Surco" — el
// distrito de Lima — no aparece ni escribiendo el nombre completo del
// apodo). Acá se busca también por el nombre real y esos resultados van
// primero, sin ocultar lo que Mapbox hubiera devuelto igual.
const DISTRICT_ALIASES = {
  surco: 'Santiago de Surco',
  // Mapbox guarda ese distrito solo como "Lima" — el nombre coloquial
  // "Cercado de Lima" no existe en su base, así que buscarlo literal no
  // trae nada útil (a veces ni siquiera "Lima" a secas aparece).
  'cercado de lima': 'Lima',
}

const displayText = v => v?.address || [v?.district, v?.province].filter(Boolean).join(', ')

const query = ref(displayText(props.modelValue))
const suggestions = ref([])
const menuOpen = ref(false)
const loading = ref(false)
const located = ref(!!(props.modelValue?.lat && props.modelValue?.lng))

let debounceTimer = null
let blurTimer = null
let abortCtrl = null

const geocode = async (text, signal) => {
  // proximity sesgado a Lima Metropolitana: la mayoría de las cotizaciones
  // arrancan ahí, y sin esto un distrito común (p.ej. "San Isidro") puede
  // salir primero de otra región homónima.
  // "district"/"region" en la taxonomía de Mapbox son provincia/departamento
  // (demasiado amplios para cotizar) — se dejan afuera a propósito. "place"
  // es el nivel que corresponde a distrito en Perú.
  const url = `https://api.mapbox.com/search/geocode/v6/forward?q=${encodeURIComponent(text)}` +
    `&autocomplete=true&country=pe&language=es&limit=6&proximity=-77.0428,-12.0464` +
    `&types=address,street,place,locality&access_token=${MAPBOX_TOKEN}`
  const res = await fetch(url, { signal })
  const data = await res.json()

  return data.features || []
}

const search = async text => {
  if (!MAPBOX_TOKEN || text.trim().length < 2) { suggestions.value = []; return }
  abortCtrl?.abort()
  abortCtrl = new AbortController()
  loading.value = true
  try {
    // Match por prefijo desde el mínimo que ya buscamos (2 caracteres): si
    // el alias dispara recién con la palabra completa, alcanzás a hacer
    // click en una sugerencia de una búsqueda parcial anterior (p.ej. "sur")
    // que todavía no lo incluía — ahí es cuando se cuela el lugar homónimo
    // equivocado.
    const t = text.trim().toLowerCase()
    const alias = Object.entries(DISTRICT_ALIASES).find(([key]) => key === t || key.startsWith(t))?.[1]
    const results = alias
      ? await Promise.all([geocode(alias, abortCtrl.signal), geocode(text, abortCtrl.signal)])
      : [await geocode(text, abortCtrl.signal)]
    const seen = new Set()
    suggestions.value = results.flat().filter(f => {
      const id = f.properties?.mapbox_id
      if (seen.has(id)) return false
      seen.add(id)

      return true
    })
  } catch (e) {
    if (e.name !== 'AbortError') suggestions.value = []
  } finally { loading.value = false }
}

const onFocus = () => { clearTimeout(blurTimer); menuOpen.value = true }
// Sin esto, el menú de un campo se queda abierto para siempre al pasar a otro
// (tab o click) porque nada lo cierra salvo elegir una sugerencia — con
// varias paradas se apilaban varios menús abiertos a la vez. El delay deja
// que el click sobre un ítem de la lista (mousedown → blur → click) alcance
// a disparar `pick()` antes de que el menú se desmonte.
const onBlur = () => { blurTimer = setTimeout(() => { menuOpen.value = false }, 150) }

const onInput = value => {
  query.value = value
  located.value = false
  menuOpen.value = true
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => search(value), 300)
}

// Para direcciones dentro de Lima Metropolitana, Mapbox pone SIEMPRE "Lima"
// en context.place (es el bucket ancho de toda la metrópoli, no el
// distrito) — el distrito real (Surco, Comas, San Isidro...) vive en
// context.locality. En otras provincias (p.ej. Callao) es al revés: place
// ya es el distrito correcto y locality es más granular todavía — por eso
// el fallback a locality-primero solo aplica cuando place es justo ese
// "Lima" ambiguo. Se usa tanto al elegir una sugerencia como para mostrar
// el distrito correcto en el subtítulo de la lista.
const resolveDistrict = feature => {
  const ctx = feature.properties?.context || {}

  return (ctx.place?.name === 'Lima' && ctx.locality?.name)
    ? ctx.locality.name
    : (ctx.place?.name || ctx.locality?.name || feature.properties?.name || '')
}
const suggestionSubtitle = feature => {
  const ctx = feature.properties?.context || {}
  const dist = resolveDistrict(feature)
  const province = ctx.district?.name || ''

  return [dist, province].filter((v, i, arr) => v && arr.indexOf(v) === i).join(', ') || feature.properties?.place_formatted
}

const pick = feature => {
  const ctx = feature.properties?.context || {}
  const region = ctx.region?.name || ''
  const province = ctx.district?.name || ''
  const dist = resolveDistrict(feature)
  const isAddress = ['address', 'street'].includes(feature.properties?.feature_type)
  const address = isAddress ? (feature.properties?.full_address || feature.properties?.place_formatted || feature.properties?.name || '') : ''
  const [lng, lat] = feature.geometry?.coordinates || [null, null]

  query.value = displayText({ district: dist, province, address }) || feature.properties?.name || ''
  located.value = lat != null && lng != null
  suggestions.value = []
  menuOpen.value = false
  emit('update:modelValue', { ...props.modelValue, district: dist, province, region, address, lat, lng })
}

const clear = () => {
  query.value = ''
  located.value = false
  suggestions.value = []
  emit('update:modelValue', { ...props.modelValue, district: '', province: '', region: '', address: '', lat: null, lng: null })
}

watch(() => props.modelValue, v => {
  const text = displayText(v)
  if (text !== query.value) query.value = text
  located.value = !!(v?.lat && v?.lng)
}, { deep: true })

onBeforeUnmount(() => { clearTimeout(debounceTimer); clearTimeout(blurTimer); abortCtrl?.abort() })
</script>

<template>
  <VMenu v-model="menuOpen" :close-on-content-click="false" location="bottom" :open-on-click="false">
    <template #activator="{ props: menuProps }">
      <VTextField
        v-bind="menuProps"
        :model-value="query" :label="label" density="comfortable"
        :prepend-inner-icon="hideIcons ? undefined : 'ri-map-pin-line'"
        :append-inner-icon="hideIcons ? undefined : (located ? 'ri-map-pin-2-fill' : undefined)"
        :color="located ? 'success' : undefined"
        :hint="!MAPBOX_TOKEN ? 'Autocompletado no disponible: escribí el distrito o la dirección.' : ''"
        persistent-hint clearable
        @click:clear="clear"
        @focus="onFocus"
        @blur="onBlur"
        @update:model-value="onInput"
      />
    </template>
    <VList density="compact" min-width="260">
      <VListItem v-if="loading" title="Buscando…" />
      <VListItem
        v-else-if="!suggestions.length"
        :title="query.trim().length < 2 ? 'Escribí el distrito o la dirección…' : 'Sin resultados — probá con otro nombre.'"
        class="text-medium-emphasis"
      />
      <VListItem
        v-for="f in suggestions" :key="f.properties.mapbox_id"
        :title="f.properties.name" :subtitle="suggestionSubtitle(f)"
        @click="pick(f)"
      />
    </VList>
  </VMenu>
</template>
