<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import AddressAutocomplete from '@/components/AddressAutocomplete.vue'
import CargoPhotosPicker from '@/components/CargoPhotosPicker.vue'
import ContinueModePicker from '@/components/ContinueModePicker.vue'
import DistrictAutocomplete from '@/components/DistrictAutocomplete.vue'
import QuoteSummaryPanel from '@/components/QuoteSummaryPanel.vue'
import ScheduleStepPicker from '@/components/ScheduleStepPicker.vue'
import VehiclePickerDialog from '@/components/VehiclePickerDialog.vue'
import { customerLoad, customerLoads, customerPublish } from '@/services/customerPortalService'
import { guestCargoEstimate, guestQuotePreview, guestQuotePreviewBatch } from '@/services/guestService'
import { useBrandStore } from '@/stores/brandStore'
import { extractVolumeM3, extractWeightKg, recomendarModalidad } from '@/utils/cargoText'

const router = useRouter()
const brand = useBrandStore()

// "¿Qué necesitas?" — mismo criterio que /cotizar (invitado): de cara al
// cliente el negocio se presenta en 3 líneas (Paquetes/Encomiendas = reparto,
// Fletes y Carga = carga, Mudanzas), por dentro las 3 siguen siendo una
// "carga" con distinta categoría/detalle. El orden y las etiquetas separan
// por QUÉ se envía (paquete a mano / camión / se carga con personal y
// escaleras), no por local vs. provincia — eso ya lo detecta el sistema solo.
const SERVICE_TYPES = [
  { value: 'reparto', icon: 'ri-archive-line', title: 'Paquetes y Encomiendas', subtitle: 'Cajas y bultos chicos o medianos. Local o a provincias.' },
  { value: 'carga', icon: 'ri-truck-line', title: 'Fletes y Carga', subtitle: 'Mercancías, equipos y carga general.' },
  { value: 'mudanza', icon: 'ri-home-4-line', title: 'Mudanzas', subtitle: 'Desde un mueble hasta tu oficina o casa completa.' },
]
const serviceType = ref('carga')

// Cliente recurrente que siempre publica el mismo tipo de servicio (p. ej.
// un negocio que solo hace Reparto): se premarca según su última carga
// publicada, para no obligarlo a re-elegir cada vez — sigue pudiendo
// cambiarlo. "otros" (carga/categoria_carga) no distingue Carga de Reparto
// en la lista, por eso hace falta el detalle de la última carga puntual.
onMounted(async () => {
  try {
    const { results } = await customerLoads()
    const last = results?.[0]
    if (!last) return
    if (last.cargoCategory === 'mudanza') { selectService('mudanza'); return }
    const detail = await customerLoad(last.code)
    selectService((detail.cargoDetail || '').startsWith('[REPARTO]') ? 'reparto' : 'carga')
  } catch (e) { /* sin historial, o falló — queda el default 'carga' */ }
})

const step = ref(1)
const form = reactive({
  origin: { district: '', address: '', floor: null, province: '', region: '', lat: null, lng: null },
  destination: { district: '', address: '', floor: null, province: '', region: '', lat: null, lng: null },
  cargo: { category: 'otros', detail: '', operators: null, truckType: null },
  date: '',
  schedule: '',
  quoteMode: 'por_carga',
  loadMode: 'completa',   // completa|parcial — solo importa si la ruta es nacional
  proposedPrice: '',      // solo si continueMode === 'propio'
})
const continueMode = ref('ofertas')   // 'ofertas' | 'propio' — solo Carga

// El botón final refleja la decisión tomada en "¿Cómo quieres continuar?" en
// vez de un genérico "Publicar y cotizar" — solo aplica a Carga, único
// servicio con continueMode.
const submitLabel = computed(() => {
  if (serviceType.value !== 'carga') return 'Publicar y cotizar'
  if (continueMode.value === 'propio' && form.proposedPrice) return `Publicar con S/ ${form.proposedPrice}`
  return 'Publicar sin precio'
})

const showVehiclePicker = ref(false)
const chosenTruckLabel = computed(() => form.cargo.truckType || '')
// Capacidad (minTon/maxTon) de la unidad elegida — ver effectiveWeightKg más
// abajo: si el camión elegido pide más capacidad que lo estimado, el precio
// se recalcula con esa capacidad como piso, no con el estimado original.
const chosenTruckUnit = ref(null)

const selectService = value => {
  serviceType.value = value
  form.quoteMode = 'por_carga'   // "elegir vehículo" solo aplica a Carga
  form.cargo.truckType = null
  chosenTruckUnit.value = null
  if (value === 'mudanza') form.cargo.category = 'mudanza'
  else form.cargo.category = 'otros'
}
// Elegir un camión puntual ya es una señal clara de que quiere precio — no
// hace falta que además toque "Ver precio estimado" por separado. Se resuelve
// el estimado completo (no solo un flag) para no perderse un peso real más
// grande que el del camión, si la descripción ya lo tenía.
const pickTruck = (value, unit) => {
  form.cargo.truckType = value; form.quoteMode = 'por_vehiculo'; chosenTruckUnit.value = unit || null
  requestPriceEstimate()
}
const clearTruck = () => { form.cargo.truckType = null; form.quoteMode = 'por_carga'; chosenTruckUnit.value = null }

// Paradas intermedias (multipunto) — solo Carga. Ver cotizar.vue: el motor de
// precios no las contempla, así que una solicitud con paradas siempre pasa a
// modo asesor, a propósito.
const photos = ref([])
const stops = reactive([])
const addStop = () => stops.push({ district: '', province: '', region: '', lat: null, lng: null })
const removeStop = index => stops.splice(index, 1)
const hasStops = computed(() => stops.some(s => s.district))
const step1ok = computed(() => !!(serviceType.value && form.origin.district && form.destination.district))
// Precio sí es opcional (se puede continuar sin él) — la descripción de la
// carga no: sin eso ni el transportista ni el motor de precios tienen nada
// para trabajar. Mudanza y Reparto quedan afuera: sus campos ya están
// marcados opcionales en el propio label ("...(opcional)").
const step2ok = computed(() => serviceType.value !== 'carga' || !!form.cargo.detail.trim())

// Peso/volumen: primero regex sobre el texto (instantáneo); si no encuentra
// nada y hay texto o fotos, se le pide a la IA que estime (la mayoría de las
// descripciones reales no traen números — "un juego de sala", no "500 kg").
// Con fotos, la IA las usa como evidencia principal para el volumen. Ver
// apps/cotizador/services_estimacion.py — nunca "otro agente", es una
// extracción de un solo turno, misma pieza base que ya usa el proyecto.
const estimatedWeightKg = ref(null)
const estimatedVolumeM3 = ref(null)
const estimatingCargo = ref(false)
// Pregunta de aclaración en lenguaje simple que arma la propia IA cuando ni
// el texto ni las fotos alcanzan (nunca pide kg/m3 directos — ver
// services_estimacion.py). Un solo reintento: se contesta una vez o se
// ignora, nunca se vuelve a preguntar de nuevo.
const suggestedQuestion = ref(null)
const questionAnswer = ref(null)
const answeringQuestion = ref(false)
// El precio (y su pregunta de aclaración, si hace falta) se pide solo al
// pausar de escribir (debounce, ver watch de form.cargo.detail más abajo) —
// "Ver precio estimado"/las tarjetas de vehículo siguen sirviendo para
// forzarlo antes de esa pausa.
const priceRequested = ref(false)
const requestingPrice = ref(false)
// Pidió precio sin haber escrito nada ni subido fotos — sin esto, el pedido
// se corta en silencio (a propósito, no hay nada que cotizar) y se siente
// como que el botón/tile no responde.
const missingDetail = computed(() =>
  priceRequested.value && !form.cargo.detail.trim() && !photos.value.length)
const cargoEstimateFailed = computed(() =>
  priceRequested.value && serviceType.value === 'carga' && !estimatingCargo.value &&
  !suggestedQuestion.value && form.cargo.detail.trim() &&
  estimatedWeightKg.value == null && estimatedVolumeM3.value == null)
const hasSuggestedQuestion = computed(() =>
  priceRequested.value && serviceType.value === 'carga' && !estimatingCargo.value &&
  !answeringQuestion.value && !!suggestedQuestion.value)

// Misma protección que fetchPricePreview: si el cliente sigue escribiendo o
// contesta la pregunta de aclaración mientras un pedido anterior todavía
// está en vuelo, esa respuesta vieja no debe pisar el peso/volumen ya
// actualizado por una llamada más nueva.
let estimateRequestSeq = 0
const estimateCargo = async () => {
  const text = form.cargo.detail
  const w = extractWeightKg(text)
  const v = extractVolumeM3(text)
  if (w != null || v != null) {
    estimateRequestSeq++   // invalida cualquier pedido a la IA todavía en vuelo
    estimatedWeightKg.value = w; estimatedVolumeM3.value = v; suggestedQuestion.value = null
    return
  }
  if (!text.trim() && !photos.value.length) {
    estimateRequestSeq++
    estimatedWeightKg.value = null; estimatedVolumeM3.value = null; suggestedQuestion.value = null
    return
  }
  const seq = ++estimateRequestSeq
  estimatingCargo.value = true
  try {
    const r = await guestCargoEstimate({ detail: text }, photos.value)
    if (seq !== estimateRequestSeq) return   // llegó una respuesta vieja, se descarta
    estimatedWeightKg.value = r.weightKg
    estimatedVolumeM3.value = r.volumeM3
    suggestedQuestion.value = r.suggestedQuestion || null
  } catch (e) {
    if (seq === estimateRequestSeq) { estimatedWeightKg.value = null; estimatedVolumeM3.value = null; suggestedQuestion.value = null }
  } finally { if (seq === estimateRequestSeq) estimatingCargo.value = false }
}
// Evita que el propio append de la respuesta (más abajo) dispare otra vez
// este watch y pise el estimado recién resuelto con una segunda llamada
// redundante a la IA.
let skipNextDetailWatch = false
// Al pausar de escribir (o subir/sacar una foto), se pide el precio solo —
// ya no hace falta tocar "Ver precio estimado" a propósito. Sigue existiendo
// como respaldo (por si alguien quiere forzarlo antes de la pausa).
let autoRequestDebounce = null
watch([() => form.cargo.detail, photos], () => {
  if (skipNextDetailWatch) { skipNextDetailWatch = false; return }
  // Editar la descripción invalida cualquier precio/pregunta ya resuelta —
  // vuelve a aparecer "Toca para ver el precio" un instante, hasta que la
  // pausa dispare el pedido de nuevo — sin arrastrar datos viejos de una
  // carga distinta.
  priceRequested.value = false
  questionAnswer.value = null
  suggestedQuestion.value = null
  estimatedWeightKg.value = null
  estimatedVolumeM3.value = null
  clearTimeout(autoRequestDebounce)
  if (form.cargo.detail.trim() || photos.value.length) {
    autoRequestDebounce = setTimeout(() => requestPriceEstimate(), 700)
  }
})

const answerSuggestedQuestion = async () => {
  if (questionAnswer.value == null || questionAnswer.value === '') return
  const question = suggestedQuestion.value
  const seq = ++estimateRequestSeq   // invalida cualquier estimateCargo() todavía en vuelo
  answeringQuestion.value = true
  try {
    const augmented = `${form.cargo.detail}\n${question.text}: ${questionAnswer.value} ${question.unit}`
    const r = await guestCargoEstimate({ detail: augmented }, photos.value)
    if (seq !== estimateRequestSeq) return   // llegó una respuesta vieja, se descarta
    estimatedWeightKg.value = r.weightKg
    estimatedVolumeM3.value = r.volumeM3
    // Deja la respuesta en la descripción visible — si no, el precio queda
    // calculado con un dato (la cantidad) que el cliente nunca ve escrito.
    skipNextDetailWatch = true
    form.cargo.detail = augmented
    suggestedQuestion.value = null
    // Se pide el precio en el mismo tramo — sin esto quedaría "Calculando…"
    // colgado hasta el próximo cambio en ruta/tipo de servicio.
    clearTimeout(previewDebounce)
    await fetchPricePreview()
  } catch (e) { if (seq === estimateRequestSeq) suggestedQuestion.value = null }
  finally { if (seq === estimateRequestSeq) answeringQuestion.value = false }
}

// Precio de referencia: no crea nada, es un estimado (ver
// apps/cotizador/api/guest_views.py::PreviewQuoteView). Antes se mostraba
// como paso propio comparando dos tarjetas (Consolidada/Express) — ahora es
// un solo número (o un rango, en la franja donde ambas modalidades tienen
// sentido real) en el panel lateral, coherente con la modalidad marcada en
// ese momento.
const pricePreview = ref(null)
const previewLoading = ref(false)
// El backend ya calcula esto (evaluar_ambito, sin importar el peso) — no
// hay Compartido/Exclusivo que preguntar en una ruta local: Consolidada
// NUNCA existe fuera de rutas interprovinciales (ver
// apps.tercerizacion.services.existe_tarifa_especifica). Mientras no se
// conoce todavía (preview sin resolver), se trata como "no interprovincial"
// para no mostrar el toggle y después tener que retirarlo.
const isInterprovincial = computed(() => pricePreview.value?.isInterprovincial === true)
// Si el camión elegido pide más capacidad que lo estimado por texto/fotos,
// se cotiza con la capacidad del camión como piso — elegir una unidad más
// grande sí debe subir el precio, aunque la carga descrita sea chica.
const effectiveWeightKg = computed(() => {
  const floorKg = chosenTruckUnit.value?.minTon != null ? chosenTruckUnit.value.minTon * 1000 : null
  if (floorKg == null) return estimatedWeightKg.value

  return estimatedWeightKg.value == null ? floorKg : Math.max(estimatedWeightKg.value, floorKg)
})
let previewDebounce = null
// Varios disparadores pueden pedir el precio casi al mismo tiempo (el peso
// de la IA se resuelve en pasos, cada paso dispara su propio pedido) — sin
// esto, la respuesta que LLEGA última pisa a la que se pidió última, y si
// esa es una más vieja (peso/destino todavía sin resolver), el precio que
// queda en pantalla no es el correcto. Cada llamada se numera; solo la
// numerada más alta puede escribir en `pricePreview`.
let previewRequestSeq = 0
const fetchPricePreview = async () => {
  // Sin pedido explícito del cliente ("Ver precio estimado") no hay nada que
  // calcular — evita mostrar un precio que nadie pidió todavía.
  if (
    !['carga', 'reparto'].includes(serviceType.value) || hasStops.value || !step1ok.value ||
    !form.cargo.detail.trim() || !priceRequested.value
  ) {
    pricePreview.value = null
    return
  }
  const seq = ++previewRequestSeq
  previewLoading.value = true
  try {
    const r = await guestQuotePreview({
      origin: form.origin, destination: form.destination, serviceType: serviceType.value,
      cargo: { category: form.cargo.category, weightKg: effectiveWeightKg.value },
    })
    if (seq === previewRequestSeq) pricePreview.value = r
  } catch (e) { if (seq === previewRequestSeq) pricePreview.value = null }
  finally { if (seq === previewRequestSeq) previewLoading.value = false }
}
// Cambios de ruta/tipo/camión elegido después de ya haber pedido el precio
// lo refrescan solos — no hace falta volver a tocar el botón. La
// descripción/fotos NO están acá: esas las dispara
// requestPriceEstimate/answerSuggestedQuestion explícitamente (ver abajo),
// nunca solas mientras se escribe.
watch([() => serviceType.value, () => form.origin.district, () => form.destination.district,
  hasStops, priceRequested, effectiveWeightKg], () => {
  clearTimeout(previewDebounce)
  previewDebounce = setTimeout(fetchPricePreview, 400)
})

// Precio Express de cada unidad del catálogo, para el selector de vehículo
// (ver VehiclePickerDialog :fetch-prices) — un solo pedido para toda la
// lista, no uno por unidad.
const fetchUnitPrices = async weightsKg => {
  try {
    const r = await guestQuotePreviewBatch({
      origin: form.origin, destination: form.destination, serviceType: serviceType.value,
      cargo: { category: form.cargo.category }, weights: weightsKg,
    })

    return r.prices || []
  } catch (e) { return [] }
}

// Acción explícita del botón "Ver precio estimado" — resuelve peso/volumen
// (o la pregunta de aclaración) y, si no quedó nada pendiente, el precio en
// el mismo tramo, sin esperar el debounce del watch de arriba.
const requestPriceEstimate = async () => {
  priceRequested.value = true
  requestingPrice.value = true
  try {
    await estimateCargo()
    if (!hasSuggestedQuestion.value) {
      clearTimeout(previewDebounce)
      await fetchPricePreview()
    }
  } finally { requestingPrice.value = false }
}

// Modalidad Compartido/Exclusivo: el cliente NUNCA elige Consolidada/Express
// directamente — eso lo declara el transportista al ofertar (ver
// apps/tercerizacion, campo OfertaTransportista.modalidad). Acá solo se
// recomienda una modalidad premarcada según el tamaño de la carga, con
// opción de cambiarla; deja de seguir la recomendación en cuanto el
// cliente toca el toggle a mano. Solo tiene sentido en ruta interprovincial
// (ver isInterprovincial arriba) — en una ruta local nunca se toca
// form.loadMode, queda en 'completa' (Express), que es lo único que existe.
const modalityTouched = ref(false)
// El backend solo arma `consolidated` cuando existe_tarifa_especifica(destino)
// — hay tarifa propia cargada para ESE destino (Configuración → Comisiones de
// tercerización → "Carga parcial"), no la tabla general. Sin eso, no hay
// evidencia real de que ese destino tenga tráfico para consolidar: no tiene
// sentido recomendar Compartido (igual queda seleccionable a mano, por si un
// transportista ofrece consolidar de todas formas).
const hasSpecificTariff = computed(() => isInterprovincial.value && pricePreview.value?.consolidated != null)
const recommendedMode = computed(() => hasSpecificTariff.value
  ? recomendarModalidad({ weightKg: estimatedWeightKg.value })
  : 'exclusivo')
watch([recommendedMode, isInterprovincial], ([mode, interprovincial]) => {
  if (modalityTouched.value || !interprovincial) return
  form.loadMode = mode === 'exclusivo' ? 'completa' : 'parcial'
})
const setLoadMode = mode => { modalityTouched.value = true; form.loadMode = mode }
watch(() => form.loadMode, mode => { if (mode === 'parcial') clearTruck() })

const soles = n => (n == null ? null : `S/ ${Math.round(n).toLocaleString('es-PE')}`)
const priceEstimate = computed(() => {
  if (!['carga', 'reparto'].includes(serviceType.value)) return null
  if (hasStops.value) return { mode: 'advisor', text: 'Un asesor te confirma el precio (hay paradas intermedias).' }
  // Todo el tramo de requestPriceEstimate (resolver peso/volumen y recién
  // después pedir el precio) cuenta como "cargando" — sin esto, el resumen y
  // el tile se quedaban sin nada que mostrar en la primera mitad de ese
  // tramo (mientras se resuelve estimateCargo, antes de que exista
  // previewLoading/pricePreview).
  if (requestingPrice.value) return { mode: 'loading' }
  // Mientras la IA todavía necesita un dato para estimar peso/volumen, no
  // mostramos un precio "confiado" — sería contradictorio con la pregunta
  // de aclaración que se le está por mostrar (o ya se le mostró).
  if (suggestedQuestion.value) return { mode: 'loading' }
  if (previewLoading.value) return { mode: 'loading' }
  if (!pricePreview.value) return null
  const { express, consolidated } = pricePreview.value

  // Reparto no tiene Compartido/Exclusivo — un solo precio (o asesor si no
  // hay cobertura de zona), ver apps/cotizador/services.py::_calcular_reparto.
  if (serviceType.value === 'reparto') {
    if (!express || express.amount == null) return { mode: 'advisor', text: 'Un asesor te confirma el precio.' }
    const hasRange = express.range && express.range[0] !== express.range[1]

    return {
      mode: 'unico',
      text: hasRange ? `${soles(express.range[0])} – ${soles(express.range[1])} aprox.` : soles(express.amount),
      suggestedAmount: Math.round(express.amount),
    }
  }

  // Sin tocar el toggle y en la franja ambigua: un rango, no dos tarjetas.
  // suggestedAmount usa Compartido (el más económico) como ancla editable —
  // el cliente puede subirlo si prefiere Exclusivo.
  if (!modalityTouched.value && recommendedMode.value === 'rango' && express?.amount != null && consolidated?.amount != null) {
    return {
      mode: 'rango', text: `${soles(consolidated.amount)} – ${soles(express.amount)} aprox.`, sub: 'según el transportista',
      suggestedAmount: Math.round(consolidated.amount),
    }
  }
  const chosen = form.loadMode === 'parcial' ? consolidated : express
  if (!chosen || chosen.amount == null) return { mode: 'advisor', text: 'Un asesor te confirma el precio.' }
  const hasRange = chosen.range && chosen.range[0] !== chosen.range[1]

  return {
    mode: 'unico',
    text: hasRange ? `${soles(chosen.range[0])} – ${soles(chosen.range[1])} aprox.` : soles(chosen.amount),
    suggestedAmount: Math.round(chosen.amount),
  }
})

// Precarga "Tu precio" con el precio sugerido apenas hay uno, y lo sigue
// actualizando si la sugerencia cambia (p. ej. el cliente vuelve atrás y
// cambia la carga) — hasta que la edita a mano (priceTouched), para no
// pisarle un valor que ya cambió a propósito.
const priceTouched = ref(false)
watch(() => priceEstimate.value?.suggestedAmount, amount => {
  if (priceTouched.value || amount == null) return
  form.proposedPrice = amount
})

// 3 pasos siempre: "Servicio y ruta" → "Detalles" → "Reserva". El precio
// (Carga) vive en el panel lateral, no en un paso propio; "¿cómo quieres
// continuar?" se sumó al paso Reserva.
const stepperItems = ['Servicio y ruta', 'Detalles', 'Reserva']
const maxStep = 3

// El precio ya es una acción explícita (botón "Ver precio estimado", arriba)
// — "Continuar" no necesita esperar ni resolver nada, nunca bloquea. Solo
// limpia una pregunta sin contestar para que el paso 3 no quede colgado en
// "Calculando…" (priceEstimate: mientras suggestedQuestion exista, no
// muestra número).
const goToStep3 = () => {
  suggestedQuestion.value = null
  step.value++
}

const submitting = ref(false)
const result = ref(null)
const error = ref('')
const submitted = ref(false)

const submit = async () => {
  submitting.value = true
  error.value = ''
  try {
    // El cotizador solo conoce categorías de carga — Reparto se manda como
    // 'otros' marcado en el detalle (ver mismo criterio en /cotizar).
    const cargo = serviceType.value === 'reparto'
      ? { ...form.cargo, detail: `[REPARTO] ${form.cargo.detail}`.trim() }
      : serviceType.value === 'carga'
        ? { ...form.cargo, weightKg: estimatedWeightKg.value, volumeM3: estimatedVolumeM3.value }
        : form.cargo
    const validStops = serviceType.value === 'carga' ? stops.filter(s => s.district) : []
    const wantsOwnPrice = serviceType.value === 'carga' && continueMode.value === 'propio'
    const payload = {
      ...form, cargo, stops: validStops, serviceType: serviceType.value,
      proposedPrice: wantsOwnPrice ? form.proposedPrice : null,
      // Siempre negociable — ya no se le pregunta al cliente Fijo/Negociable
      // (decisión de UX: el transportista siempre puede contraproponer).
      priceNegotiable: true,
    }
    result.value = await customerPublish(payload, photos.value)
    submitted.value = true
  } catch (e) { error.value = e.message || 'No se pudo publicar.' } finally { submitting.value = false }
}
</script>

<template>
  <!-- Placa flotante con el precio de referencia — el Paso 3 (Reserva) es
       largo (fecha + hora + contacto) y no hay panel lateral fijo visible en
       mobile, así que sin esto se pierde de vista el precio sugerido al
       hacer scroll más abajo. -->
  <div v-if="step === 3 && !submitted && serviceType === 'carga' && priceEstimate?.mode === 'unico'" class="price-float-badge">
    <VIcon icon="ri-price-tag-3-line" size="14" color="primary" />
    <span class="text-caption text-medium-emphasis">Sugerido</span>
    <span class="text-body-2 font-weight-bold text-primary">{{ priceEstimate.text }}</span>
  </div>

  <div>
    <h1 class="text-h5 font-weight-bold mb-2">Publicar solicitud</h1>
    <div class="mb-4">
      <VStepper v-if="!submitted" v-model="step" flat class="bg-transparent route-stepper w-100" hide-actions>
        <VStepperHeader>
          <template v-for="(label, i) in stepperItems" :key="i">
            <VStepperItem :title="label" :value="i + 1" :complete="step > i + 1" color="primary" />
            <VDivider v-if="i < stepperItems.length - 1" />
          </template>
        </VStepperHeader>
      </VStepper>
    </div>

    <VRow>
    <VCol cols="12" md="7">
    <VCard v-if="!submitted">
      <VCardText>
        <VWindow v-model="step">
          <VWindowItem :value="1">
            <div class="text-h6 font-weight-bold mb-4">Elige el tipo de servicio que mejor se adapta a tu carga</div>
            <VRow class="mb-3" dense>
              <VCol v-for="s in SERVICE_TYPES" :key="s.value" cols="12" sm="4">
                <VCard
                  variant="outlined"
                  class="pa-4 text-center h-100 position-relative service-tile"
                  :class="{ 'service-tile--selected': serviceType === s.value }"
                  style="cursor: pointer;"
                  @click="selectService(s.value)"
                >
                  <VIcon
                    v-if="serviceType === s.value" icon="ri-checkbox-circle-fill" color="primary" size="20"
                    style="position:absolute; top:10px; right:10px;"
                  />
                  <VAvatar
                    size="48" class="mb-3" :variant="serviceType === s.value ? 'elevated' : 'tonal'"
                    :color="serviceType === s.value ? 'primary' : 'surface-variant'"
                  >
                    <VIcon :icon="s.icon" size="24" :color="serviceType === s.value ? 'white' : undefined" />
                  </VAvatar>
                  <div class="text-subtitle-1 font-weight-bold mb-1">{{ s.title }}</div>
                  <div class="text-caption text-medium-emphasis">{{ s.subtitle }}</div>
                </VCard>
              </VCol>
            </VRow>

            <VDivider class="mb-3" />
            <template v-if="serviceType === 'reparto'">
              <div class="d-flex align-center ga-2 mb-3">
                <VAvatar size="28" color="primary" variant="tonal"><VIcon icon="ri-map-pin-line" size="16" /></VAvatar>
                <span class="text-subtitle-2 font-weight-bold">Ingresa la ruta de tu reparto</span>
              </div>
              <VRow dense>
                <VCol cols="12" sm="6">
                  <AddressAutocomplete v-model="form.origin" label="Punto de recojo / almacén" />
                </VCol>
                <VCol cols="12" sm="6">
                  <AddressAutocomplete v-model="form.destination" label="Zona de reparto (referencia)" />
                </VCol>
              </VRow>
            </template>
            <template v-else>
              <div class="d-flex align-center ga-2 mb-1">
                <VAvatar size="28" color="primary" variant="tonal"><VIcon icon="ri-map-pin-line" size="16" /></VAvatar>
                <span class="text-subtitle-2 font-weight-bold">Ingresa la ruta de tu {{ serviceType === 'mudanza' ? 'mudanza' : 'carga' }}</span>
              </div>

              <div class="d-flex mt-3">
                <div class="d-flex flex-column align-center mr-3" style="width: 10px;">
                  <div style="width:10px; height:10px; border-radius:50%; background:#56CA00; flex-shrink:0;" />
                  <div style="flex:1; width:0; border-left:2px dotted rgba(var(--v-theme-on-surface), 0.3); margin: 4px 0;" />
                  <template v-if="serviceType === 'carga'">
                    <template v-for="(stop, i) in stops" :key="i">
                      <div style="width:10px; height:10px; border-radius:50%; background:#F9A825; flex-shrink:0;" />
                      <div style="flex:1; width:0; border-left:2px dotted rgba(var(--v-theme-on-surface), 0.3); margin: 4px 0;" />
                    </template>
                  </template>
                  <div style="width:10px; height:10px; border-radius:50%; background:#8C57FF; flex-shrink:0;" />
                </div>
                <div class="flex-grow-1">
                  <DistrictAutocomplete v-model="form.origin" label="Origen" hide-icons class="mb-1" />
                  <VTextField v-if="serviceType === 'mudanza'" v-model.number="form.origin.floor" label="Piso (opcional)" type="number" class="mb-2" />
                  <div v-else class="mb-3" />

                  <template v-if="serviceType === 'carga'">
                    <div v-for="(stop, i) in stops" :key="i" class="d-flex align-center ga-2 mb-4">
                      <DistrictAutocomplete v-model="stops[i]" :label="`Parada ${i + 1}`" hide-icons class="flex-grow-1" />
                      <VBtn icon variant="text" size="small" @click="removeStop(i)">
                        <VIcon icon="ri-close-line" />
                      </VBtn>
                    </div>
                  </template>

                  <DistrictAutocomplete v-model="form.destination" label="Destino" hide-icons />
                  <VTextField v-if="serviceType === 'mudanza'" v-model.number="form.destination.floor" label="Piso (opcional)" type="number" />
                </div>
              </div>

              <template v-if="serviceType === 'carga'">
                <VBtn variant="text" size="small" prepend-icon="ri-add-line" class="mt-3" @click="addStop">
                  Agregar parada
                </VBtn>
                <p class="text-caption text-medium-emphasis mt-1 mb-0">Puedes añadir paradas intermedias (opcional).</p>
              </template>
            </template>
          </VWindowItem>

          <VWindowItem :value="2">
            <template v-if="serviceType === 'carga'">
              <div class="text-h6 font-weight-bold mb-1">¿Qué vas a transportar?</div>
              <p class="text-caption text-medium-emphasis mb-4">
                Ingresa los detalles de tu carga y {{ brand.displayName }} te muestra el precio.
              </p>
              <VTextarea
                v-model="form.cargo.detail" rows="4" auto-grow class="mb-2"
                counter maxlength="500" label="Descripción de la carga"
                placeholder="Ej: 40 cajas de repuestos automotrices, del tamaño de una caja de zapatos cada una"
              />
              <div class="d-flex align-center ga-1 mb-4">
                <VIcon icon="ri-information-line" size="14" class="text-medium-emphasis" />
                <span class="text-caption text-medium-emphasis">
                  Cuanto más claro sea el detalle, más preciso será el precio estimado.
                </span>
              </div>
            </template>
            <template v-else-if="serviceType === 'mudanza'">
              <div class="text-h6 font-weight-bold mb-4">¿Qué vas a mudar?</div>
              <VTextarea
                v-model="form.cargo.detail" rows="2" auto-grow class="mb-2"
                label="Ambientes, pisos, ascensor, muebles grandes (opcional)"
              />
              <VTextField v-model.number="form.cargo.operators" label="¿Necesitas operarios para la mudanza? ¿Cuántos?" type="number" />
            </template>
            <template v-else-if="serviceType === 'reparto'">
              <div class="text-h6 font-weight-bold mb-4">Cuéntanos tu operación de reparto</div>
              <VTextarea
                v-model="form.cargo.detail" rows="2" auto-grow class="mb-2"
                label="Cuántos pedidos, frecuencia, si es ecommerce o contra-entrega (opcional)"
              />
            </template>

            <CargoPhotosPicker v-model="photos" class="mb-2" />

            <!-- La pregunta de aclaración (si hace falta un dato) siempre va
                 acá, sea que el precio se pida con el botón de abajo o desde
                 el tile "TaxiCarga elige" más abajo. -->
            <template v-if="['carga', 'reparto'].includes(serviceType)">
              <VAlert v-if="hasSuggestedQuestion" type="info" variant="tonal" density="comfortable" class="mt-2">
                <div class="mb-2">
                  Para darte un precio estimado nos falta un dato: <strong>{{ suggestedQuestion.text }}</strong>
                </div>
                <div class="d-flex align-center ga-2 flex-wrap">
                  <VTextField
                    v-model="questionAnswer" type="number" density="compact" hide-details style="max-width: 140px;"
                    :suffix="suggestedQuestion.unit" @keyup.enter="answerSuggestedQuestion"
                  />
                  <VBtn size="small" color="primary" variant="tonal" :loading="answeringQuestion" @click="answerSuggestedQuestion">
                    Estimar precio
                  </VBtn>
                </div>
                <div class="text-caption text-medium-emphasis mt-2">
                  También puedes continuar sin este dato — tu solicitud se publica igual, solo que sin precio
                  estimado (un asesor te lo confirma después).
                  <VBtn size="small" variant="text" class="px-1" @click="suggestedQuestion = null">Continuar sin precio</VBtn>
                </div>
              </VAlert>

              <VAlert v-else-if="cargoEstimateFailed" type="info" variant="tonal" density="comfortable" class="mt-2">
                No pudimos calcular el precio estimado por falta de detalle de carga (peso, cantidad, volumen, etc.).
                Puedes editar la descripción, agregar fotos, o continuar así sin precio, no hay problema.
              </VAlert>

              <VAlert v-else-if="missingDetail" type="info" variant="tonal" density="comfortable" class="mt-2">
                Escribe qué vas a transportar (o agrega una foto) para poder calcular un precio — igual puedes
                continuar sin ponerlo.
              </VAlert>
            </template>

            <template v-if="serviceType === 'carga'">
              <VDivider class="my-3" />
              <!-- Compartido/Exclusivo solo existe en rutas interprovinciales —
                   Consolidada nunca es una opción real dentro de una misma
                   ciudad, así que ni se pregunta ahí. -->
              <template v-if="isInterprovincial">
                <div class="text-subtitle-2 font-weight-bold mb-2">¿Cómo quieres tu carga?</div>
                <VRadioGroup
                  :model-value="form.loadMode" inline hide-details density="comfortable"
                  class="radio-pill-group mb-2" @update:model-value="setLoadMode"
                >
                  <VRadio value="parcial" @click="setLoadMode('parcial')">
                    <template #label>
                      <span>Compartido</span>
                      <VChip v-if="recommendedMode === 'compartido' && !modalityTouched" size="x-small" color="primary" variant="flat" class="ml-2">Recomendado</VChip>
                      <span v-if="pricePreview?.consolidated?.amount != null" class="text-caption font-weight-bold text-primary ml-2">
                        {{ soles(pricePreview.consolidated.amount) }}
                      </span>
                    </template>
                  </VRadio>
                  <VRadio value="completa" @click="setLoadMode('completa')">
                    <template #label>
                      <span>Exclusivo</span>
                      <VChip v-if="recommendedMode === 'exclusivo' && !modalityTouched" size="x-small" color="primary" variant="flat" class="ml-2">Recomendado</VChip>
                      <span v-if="pricePreview?.express?.amount != null" class="text-caption font-weight-bold text-primary ml-2">
                        {{ soles(pricePreview.express.amount) }}
                      </span>
                    </template>
                  </VRadio>
                </VRadioGroup>
                <p class="text-caption text-medium-emphasis mb-3">
                  {{ form.loadMode === 'parcial'
                    ? 'Tu carga viaja junto con otra — más económico.'
                    : 'Un camión solo para tu carga — más rápido.' }}
                </p>
              </template>

              <template v-if="!isInterprovincial || form.loadMode === 'completa'">
                <div class="text-subtitle-2 font-weight-bold mb-1">¿Deseas elegir un vehículo específico?</div>
                <p class="text-caption text-medium-emphasis mb-2">
                  Si no tienes uno en mente, {{ brand.displayName }} encontrará un vehículo adecuado para tu carga.
                </p>
                <VRow dense>
                  <VCol cols="12" sm="6">
                    <VCard
                      variant="outlined" class="pa-3 h-100 position-relative service-tile"
                      :class="{ 'service-tile--selected': !form.cargo.truckType }"
                      style="cursor: pointer;" @click="clearTruck"
                    >
                      <VIcon
                        v-if="!form.cargo.truckType" icon="ri-checkbox-circle-fill" color="primary" size="16"
                        style="position:absolute; top:8px; right:8px;"
                      />
                      <VAvatar size="36" variant="tonal" color="primary" class="mb-2">
                        <VIcon icon="ri-magic-line" size="18" />
                      </VAvatar>
                      <div class="text-body-2 font-weight-bold">No, que {{ brand.displayName }} elija por mí</div>
                      <div class="text-caption text-medium-emphasis mb-2">
                        Encontramos el vehículo ideal según tu carga y ruta.
                      </div>
                      <VChip size="x-small" color="primary" variant="tonal">Recomendado</VChip>
                    </VCard>
                  </VCol>
                  <VCol cols="12" sm="6">
                    <VCard
                      variant="outlined" class="pa-3 h-100 position-relative service-tile"
                      :class="{ 'service-tile--selected': !!form.cargo.truckType }"
                      style="cursor: pointer;" @click="showVehiclePicker = true"
                    >
                      <VIcon
                        v-if="form.cargo.truckType" icon="ri-checkbox-circle-fill" color="primary" size="16"
                        style="position:absolute; top:8px; right:8px;"
                      />
                      <VAvatar size="36" variant="tonal" color="primary" class="mb-2">
                        <VIcon icon="ri-truck-line" size="18" />
                      </VAvatar>
                      <div class="text-body-2 font-weight-bold">Sí, quiero elegir un vehículo</div>
                      <div class="text-caption text-medium-emphasis">
                        {{ form.cargo.truckType ? chosenTruckLabel : 'Elige el vehículo que necesitas para tu carga.' }}
                      </div>
                    </VCard>
                  </VCol>
                </VRow>
                <div v-if="isInterprovincial" class="text-caption text-medium-emphasis mt-2">
                  Al elegir un camión puntual, tu carga se cotiza como <strong>Exclusiva</strong> y el precio se
                  ajusta según su capacidad.
                </div>
                <VehiclePickerDialog
                  v-model="showVehiclePicker"
                  :estimated-weight-kg="estimatedWeightKg" :estimated-volume-m3="estimatedVolumeM3"
                  :fetch-prices="fetchUnitPrices"
                  @select="pickTruck" @clear="clearTruck"
                />
              </template>
            </template>
          </VWindowItem>

          <VWindowItem :value="3">
            <template v-if="serviceType === 'carga'">
              <div class="text-h5 font-weight-bold mb-1">Publicar Carga</div>
              <p class="text-body-2 text-medium-emphasis mb-4">Elige cómo quieres publicar tu carga</p>
            </template>
            <!-- Cabecera de precio ÚNICA para todo el paso, en dos columnas
                 (sugerido | rango) — reemplaza la versión apilada anterior. -->
            <VCard v-if="priceEstimate" variant="tonal" :color="priceEstimate.mode === 'advisor' ? undefined : 'primary'" class="mb-4">
              <VCardText>
                <div v-if="priceEstimate.mode === 'loading'" class="d-flex align-center ga-2">
                  <VProgressCircular indeterminate size="18" width="2" color="primary" />
                  <span class="text-body-2">Calculando precio…</span>
                </div>
                <div v-else-if="priceEstimate.mode === 'advisor'" class="d-flex align-center ga-3">
                  <VAvatar size="40" color="primary" variant="tonal"><VIcon icon="ri-price-tag-3-line" size="20" /></VAvatar>
                  <span class="text-body-2 font-weight-medium">{{ priceEstimate.text }}</span>
                </div>
                <div v-else class="d-flex align-center flex-wrap ga-4">
                  <div class="d-flex align-center ga-3">
                    <VAvatar size="40" color="primary" variant="tonal"><VIcon icon="ri-price-tag-3-line" size="20" /></VAvatar>
                    <div>
                      <div class="d-flex align-center ga-1">
                        <span class="text-caption text-medium-emphasis">Precio sugerido para esta carga</span>
                        <VTooltip text="Calculado según servicios similares en tu ruta.">
                          <template #activator="{ props: tip }">
                            <VIcon v-bind="tip" icon="ri-information-line" size="14" class="text-medium-emphasis" />
                          </template>
                        </VTooltip>
                      </div>
                      <div class="text-h5 font-weight-bold text-primary">
                        {{ priceEstimate.suggestedAmount != null ? soles(priceEstimate.suggestedAmount) : priceEstimate.text }}
                      </div>
                    </div>
                  </div>

                  <template v-if="priceEstimate.suggestedAmount != null && priceEstimate.text.includes('–')">
                    <VDivider vertical class="d-none d-sm-block" style="min-height: 44px;" />
                    <div>
                      <div class="text-caption text-medium-emphasis">Rango estimado:</div>
                      <div class="text-body-1 font-weight-bold text-primary">{{ priceEstimate.text }}</div>
                      <div class="text-caption text-medium-emphasis">Basado en precios de transportes similares.</div>
                    </div>
                  </template>
                  <div v-else-if="priceEstimate.sub" class="text-caption text-medium-emphasis">{{ priceEstimate.sub }}</div>
                </div>
              </VCardText>
            </VCard>
            <template v-if="serviceType === 'carga'">
              <ContinueModePicker
                :mode="continueMode" :price="form.proposedPrice"
                :suggested-price="priceEstimate?.suggestedAmount"
                @update:mode="v => continueMode = v"
                @update:price="v => { form.proposedPrice = v; priceTouched = true }"
              />
              <VDivider class="my-4" />
            </template>
            <ScheduleStepPicker
              :date="form.date" :schedule="form.schedule"
              @update:date="v => form.date = v" @update:schedule="v => form.schedule = v"
            />
            <VAlert v-if="error" type="error" variant="tonal" class="mt-3">{{ error }}</VAlert>
          </VWindowItem>
        </VWindow>
      </VCardText>

      <VCardActions class="px-4 pb-4">
        <VBtn v-if="step > 1" variant="text" @click="step--">Atrás</VBtn>
        <VSpacer />
        <VBtn v-if="step === 1" color="primary" variant="elevated" rounded="lg" size="large" min-width="180" :disabled="!step1ok" @click="step = 2">Siguiente</VBtn>
        <VBtn
          v-else-if="step < maxStep" color="primary" variant="elevated" rounded="lg" size="large" min-width="180"
          :disabled="step === 2 && !step2ok" @click="goToStep3"
        >
          Continuar
        </VBtn>
        <VBtn
          v-else color="primary" variant="elevated" rounded="lg" size="large" min-width="180" :loading="submitting"
          :disabled="serviceType === 'carga' && continueMode === 'propio' && !form.proposedPrice"
          @click="submit"
        >
          {{ submitLabel }}
        </VBtn>
      </VCardActions>
    </VCard>

    <VCard v-else>
      <VCardText class="text-center py-6">
        <VIcon icon="ri-checkbox-circle-line" color="success" size="48" class="mb-2" />
        <div class="text-h6">Solicitud {{ result.code }} publicada</div>
        <div v-if="soles(result.price?.amount)" class="text-h5 font-weight-bold my-2">{{ soles(result.price.amount) }}</div>
        <div v-else class="text-body-2 text-medium-emphasis my-2">
          Estamos buscando la mejor alternativa. Te avisaremos apenas tengamos precio, también por WhatsApp.
        </div>
        <div v-if="result.price?.daysEstimated" class="text-caption text-medium-emphasis">
          Llega en {{ result.price.daysEstimated }} días hábiles aprox.
        </div>
        <VBtn color="primary" class="mt-2" @click="router.push(`/portal/cliente/carga/${result.code}`)">Ver carga</VBtn>
      </VCardText>
    </VCard>
    </VCol>

    <VCol cols="12" md="5">
      <QuoteSummaryPanel
        :service-label="SERVICE_TYPES.find(s => s.value === serviceType)?.title"
        :origin="form.origin" :destination="form.destination" :stops="stops"
        :detail="form.cargo.detail" :date="form.date"
        :truck-label="chosenTruckLabel"
        :estimated-weight-kg="estimatedWeightKg" :estimated-volume-m3="estimatedVolumeM3"
        :price-estimate="step >= 3 ? priceEstimate : null"
        @edit-type="step = 1"
      />
    </VCol>
    </VRow>
  </div>
</template>

<style scoped>
.service-tile {
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
}
.service-tile:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(var(--v-theme-on-surface), 0.12);
}
/* Selección con acento de color + sombra en vez de rellenar toda la
   tarjeta de "tonal" (color plano) — más sobrio y menos repetitivo cuando
   se repite el mismo patrón en varios pasos del formulario. */
.service-tile--selected {
  border-color: rgb(var(--v-theme-primary)) !important;
  border-inline-start: 3px solid rgb(var(--v-theme-primary)) !important;
  box-shadow: 0 4px 14px rgba(var(--v-theme-primary), 0.22);
}

/* Timeline compacto, centrado en la página, sin caja/sombra/fondo propio —
   como en el mockup (no es una sección aparte, es parte del encabezado).
   bg-transparent no le gana al fondo del VSheet base de VStepper, por eso
   se fuerza acá con !important. */
.route-stepper {
  background: transparent !important;
  box-shadow: none !important;
}
.route-stepper :deep(.v-stepper-header) {
  box-shadow: none;
  overflow-x: visible;
  flex-wrap: wrap;
  row-gap: 4px;
  justify-content: center;
}
.route-stepper :deep(.v-stepper-item) {
  padding: 0 0.5rem;
}
/* Pantallas muy angostas: si ni envolviendo en línea alcanza, se sacan las
   líneas conectoras (no aportan info y compiten por espacio) — nunca debe
   aparecer una barra de scroll horizontal en el timeline. */
@media (max-width: 480px) {
  .route-stepper :deep(.v-divider) {
    display: none;
  }
}
.route-stepper :deep(.v-stepper-item__avatar) {
  width: 22px;
  height: 22px;
  font-size: 0.6875rem;
}
.route-stepper :deep(.v-stepper-item__title) {
  font-size: 0.8125rem;
}
.route-stepper :deep(.v-divider) {
  margin: 0 4px;
  min-width: 24px;
  opacity: 0.6;
  flex: 0 1 32px;
}

/* Radio "tipo Materio" en caja compartida — mismo tratamiento que
   ScheduleStepPicker.vue/ContinueModePicker.vue, en vez del VBtnToggle
   (pill plano) que se veía "poco profesional". */
.radio-pill-group :deep(.v-selection-control-group) {
  display: flex;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  overflow: hidden;
}
.radio-pill-group :deep(.v-radio) {
  flex: 1 1 0;
  min-width: 0;
  margin: 0 !important;
  padding: 10px 14px;
  cursor: pointer;
  transition: background-color 0.15s ease;
}
.radio-pill-group :deep(.v-radio:not(:last-child)) {
  border-inline-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.radio-pill-group :deep(.v-radio.v-selection-control--dirty) {
  background: rgba(var(--v-theme-primary), 0.06);
}
.radio-pill-group :deep(.v-label) {
  font-size: 0.875rem;
  white-space: nowrap;
}

/* Fixed (no sticky) a propósito — evita depender de que ningún ancestro
   tenga overflow:hidden (VCard sí lo tiene) para que el "pin" funcione. */
.price-float-badge {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-theme-primary), 0.35);
  border-radius: 20px;
  padding: 6px 14px;
  box-shadow: 0 2px 10px rgba(var(--v-theme-on-surface), 0.15);
}
@media (max-width: 600px) {
  .price-float-badge {
    top: auto;
    bottom: 16px;
    left: 16px;
    right: 16px;
    justify-content: center;
  }
}
</style>
