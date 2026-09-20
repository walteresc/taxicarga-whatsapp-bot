<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import AddressAutocomplete from '@/components/AddressAutocomplete.vue'
import CargoPhotosPicker from '@/components/CargoPhotosPicker.vue'
import ContinueModePicker from '@/components/ContinueModePicker.vue'
import DistrictAutocomplete from '@/components/DistrictAutocomplete.vue'
import QuoteSummaryPanel from '@/components/QuoteSummaryPanel.vue'
import ScheduleStepPicker from '@/components/ScheduleStepPicker.vue'
import VehiclePickerDialog from '@/components/VehiclePickerDialog.vue'
import { guestCargoEstimate, guestQuote, guestQuotePreview, guestSignup } from '@/services/guestService'
import { useAuthStore } from '@/stores/authStore'
import { extractVolumeM3, extractWeightKg, recomendarModalidad } from '@/utils/cargoText'

const router = useRouter()
const auth = useAuthStore()

// "¿Qué necesitas?" — de cara al cliente el negocio se presenta en 3 líneas
// (Carga / Mudanzas / Reparto); por dentro las 3 pasan por el mismo cotizador
// de invitado, solo cambia qué categoría de `cargo` mandamos.
const SERVICE_TYPES = [
  { value: 'carga', icon: 'ri-truck-line', title: 'Carga', subtitle: 'Encomiendas, paquetes o carga nacional.' },
  { value: 'mudanza', icon: 'ri-home-4-line', title: 'Mudanzas', subtitle: 'Casa, oficina o empresa.' },
  { value: 'reparto', icon: 'ri-e-bike-2-line', title: 'Entregas', subtitle: 'Reparto, distribución y última milla.' },
]
const serviceType = ref('')

// Elegir vehículo es opcional y no aplica a Mudanza/Reparto — por defecto
// "que TaxiCarga elija" (quoteMode 'por_carga', sin truckType). El picker
// trae sus propias opciones del catálogo real (apps/catalogo) y emite
// directamente el nombre de la unidad elegida (p. ej. "Camión 4 ton").
//
// Elegir vehículo solo tiene sentido si la carga es "Exclusiva" (camión
// dedicado) — en "Compartida" no hay vehículo puntual que pedir, va con
// carga propia del transportista. Por eso el picker está ANIDADO bajo el
// toggle de modalidad, no es un control aparte: así el cliente que quiere
// exclusividad pero no sabe qué camión pedir no tiene que "elegir un
// vehículo" para conseguirlo (le alcanza con el toggle solo), y el que
// necesita un tamaño puntual pero no le importa compartir nunca ve la
// pregunta (si comparte, no elige camión).
const showVehiclePicker = ref(false)
const chosenTruck = ref(null)
const chosenTruckLabel = computed(() => chosenTruck.value || '')

const phase = ref('form')   // form | result | signup
const step = ref(1)
const busy = ref(false)
const error = ref('')

const quote = reactive({
  origin: { district: '', address: '', province: '', region: '', lat: null, lng: null },
  destination: { district: '', address: '', province: '', region: '', lat: null, lng: null },
  cargo: { category: 'otros', detail: '' },
  loadMode: 'completa',   // completa|parcial — solo importa si la ruta es nacional
  date: '',
  schedule: '',
  proposedPrice: '',      // solo si continueMode === 'propio'
  priceNegotiable: true,
  contact: { name: '', phone: '', email: '' },
  website: '',   // honeypot
})
const continueMode = ref('ofertas')   // 'ofertas' | 'propio' — solo Carga
const result = ref(null)

// Paradas intermedias (multipunto) — solo Carga. El motor de precios no las
// contempla en el cálculo (ver apps/cotizador/services.py::cotizar_lead), así
// que una solicitud con paradas siempre pasa a modo asesor, a propósito.
const photos = ref([])
const stops = reactive([])
const addStop = () => stops.push({ district: '', province: '', region: '', lat: null, lng: null })
const removeStop = index => stops.splice(index, 1)
const hasStops = computed(() => stops.some(s => s.district))
const step1ok = computed(() => !!(serviceType.value && quote.origin.district && quote.destination.district))

// Peso/volumen: primero regex sobre el texto (instantáneo); si no encuentra
// nada y hay texto o fotos, se le pide a la IA que estime (la mayoría de las
// descripciones reales no traen números — "un juego de sala", no "500 kg").
// Con fotos, la IA las usa como evidencia principal para el volumen. Ver
// apps/cotizador/services_estimacion.py — nunca "otro agente", es una
// extracción de un solo turno, misma pieza base que ya usa el proyecto.
const estimatedWeightKg = ref(null)
const estimatedVolumeM3 = ref(null)
const estimatingCargo = ref(false)
// true en cuanto cambia texto/fotos y todavía no corrió un intento real
// (esperando el debounce o la llamada a la IA) — evita que el aviso o la
// pregunta de aclaración parpadeen apenas se empieza a escribir.
const estimatePending = ref(false)
// Pregunta de aclaración en lenguaje simple que arma la propia IA cuando ni
// el texto ni las fotos alcanzan (nunca pide kg/m3 directos — ver
// services_estimacion.py). Un solo reintento: se contesta una vez o se
// ignora, nunca se vuelve a preguntar de nuevo.
const suggestedQuestion = ref(null)
const questionAnswer = ref(null)
const answeringQuestion = ref(false)
const cargoEstimateFailed = computed(() =>
  serviceType.value === 'carga' && !estimatingCargo.value && !estimatePending.value &&
  !suggestedQuestion.value && quote.cargo.detail.trim() &&
  estimatedWeightKg.value == null && estimatedVolumeM3.value == null)
const hasSuggestedQuestion = computed(() =>
  serviceType.value === 'carga' && !estimatingCargo.value && !estimatePending.value &&
  !answeringQuestion.value && !!suggestedQuestion.value)

let estimateDebounce = null
const estimateCargo = async () => {
  estimatePending.value = false
  const text = quote.cargo.detail
  const w = extractWeightKg(text)
  const v = extractVolumeM3(text)
  if (w != null || v != null) {
    estimatedWeightKg.value = w; estimatedVolumeM3.value = v; suggestedQuestion.value = null
    return
  }
  if (!text.trim() && !photos.value.length) {
    estimatedWeightKg.value = null; estimatedVolumeM3.value = null; suggestedQuestion.value = null
    return
  }
  estimatingCargo.value = true
  try {
    const r = await guestCargoEstimate({ detail: text }, photos.value)
    estimatedWeightKg.value = r.weightKg
    estimatedVolumeM3.value = r.volumeM3
    suggestedQuestion.value = r.suggestedQuestion || null
  } catch (e) {
    estimatedWeightKg.value = null; estimatedVolumeM3.value = null; suggestedQuestion.value = null
  } finally { estimatingCargo.value = false }
}
watch([() => quote.cargo.detail, photos], () => {
  questionAnswer.value = null
  estimatePending.value = true
  clearTimeout(estimateDebounce)
  estimateDebounce = setTimeout(estimateCargo, 600)
})

const answerSuggestedQuestion = async () => {
  if (questionAnswer.value == null || questionAnswer.value === '') return
  const question = suggestedQuestion.value
  answeringQuestion.value = true
  try {
    const augmented = `${quote.cargo.detail}\n${question.text}: ${questionAnswer.value} ${question.unit}`
    const r = await guestCargoEstimate({ detail: augmented }, photos.value)
    estimatedWeightKg.value = r.weightKg
    estimatedVolumeM3.value = r.volumeM3
  } catch (e) { /* seguí sin precio, ver aviso de abajo */ }
  finally { suggestedQuestion.value = null; answeringQuestion.value = false }
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
let previewDebounce = null
const fetchPricePreview = async () => {
  if (serviceType.value !== 'carga' || hasStops.value || !step1ok.value) { pricePreview.value = null; return }
  previewLoading.value = true
  try {
    pricePreview.value = await guestQuotePreview({
      origin: quote.origin, destination: quote.destination, serviceType: serviceType.value,
      cargo: { category: quote.cargo.category, weightKg: estimatedWeightKg.value },
    })
  } catch (e) { pricePreview.value = null } finally { previewLoading.value = false }
}
watch([() => serviceType.value, () => quote.origin.district, () => quote.destination.district,
  estimatedWeightKg, hasStops], () => {
  clearTimeout(previewDebounce)
  previewDebounce = setTimeout(fetchPricePreview, 400)
})

// Modalidad Compartido/Exclusivo: el cliente NUNCA elige Consolidada/Express
// directamente — eso lo declara el transportista al ofertar (ver
// apps/tercerizacion, campo OfertaTransportista.modalidad). Acá solo se
// recomienda una modalidad premarcada según el tamaño de la carga, con
// opción de cambiarla; deja de seguir la recomendación en cuanto el
// cliente toca el toggle a mano. Solo tiene sentido en ruta interprovincial
// (ver isInterprovincial arriba) — en una ruta local nunca se toca
// quote.loadMode, queda en 'completa' (Express), que es lo único que existe.
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
  quote.loadMode = mode === 'exclusivo' ? 'completa' : 'parcial'
})
const setLoadMode = mode => { modalityTouched.value = true; quote.loadMode = mode }
watch(() => quote.loadMode, mode => { if (mode === 'parcial') chosenTruck.value = null })

const soles = n => (n == null ? null : `S/ ${Math.round(n).toLocaleString('es-PE')}`)
const priceEstimate = computed(() => {
  if (serviceType.value !== 'carga') return null
  if (hasStops.value) return { mode: 'advisor', text: 'Un asesor te confirma el precio (hay paradas intermedias).' }
  if (previewLoading.value) return { mode: 'loading' }
  if (!pricePreview.value) return null
  const { express, consolidated } = pricePreview.value
  // Sin tocar el toggle y en la franja ambigua: un rango, no dos tarjetas.
  if (!modalityTouched.value && recommendedMode.value === 'rango' && express?.amount != null && consolidated?.amount != null) {
    return { mode: 'rango', text: `Desde ${soles(consolidated.amount)} hasta ${soles(express.amount)} aprox.`, sub: 'según el transportista' }
  }
  const chosen = quote.loadMode === 'parcial' ? consolidated : express
  if (!chosen || chosen.amount == null) return { mode: 'advisor', text: 'Un asesor te confirma el precio.' }

  return {
    mode: 'unico', text: soles(chosen.amount),
    sub: chosen.range && chosen.range[0] !== chosen.range[1] ? `Rango ${soles(chosen.range[0])} – ${soles(chosen.range[1])}` : null,
  }
})

// 3 pasos siempre: "Servicio y ruta" → "Detalles" → "Reserva". El precio
// (Carga) vive en el panel lateral, no en un paso propio; "¿cómo quieres
// continuar?" se sumó al paso Reserva. El resumen/mapa de la derecha
// (QuoteSummaryPanel) hace de confirmación permanente.
const stepperItems = ['Servicio y ruta', 'Detalles', 'Reserva']
const maxStep = 3

// Al pasar de "Detalles" a "Reserva" (única transición donde importa la
// estimación de carga): si hay un intento pendiente, se resuelve antes de
// decidir — si no, "Siguiente" podría avanzar sin haber corrido nunca la
// estimación (o con una desactualizada). Si la IA recién ahí propone una
// pregunta de aclaración, se queda una vez para mostrarla; el segundo clic
// (la haya contestado o no) avanza igual — nunca bloquea.
const goingToStep3 = ref(false)
const goToStep3 = async () => {
  if (serviceType.value !== 'carga') { step.value++; return }
  if (estimatePending.value) {
    goingToStep3.value = true
    clearTimeout(estimateDebounce)
    await estimateCargo()
    goingToStep3.value = false
  }
  if (hasSuggestedQuestion.value) return
  step.value++
}

const formOk = computed(() => {
  if (!(step1ok.value && quote.contact.phone && quote.contact.name)) return false
  if (serviceType.value === 'carga' && continueMode.value === 'propio' && !quote.proposedPrice) return false

  return true
})

const submitQuote = async () => {
  busy.value = true
  error.value = ''
  try {
    // El cotizador solo conoce categorías de carga — Reparto usa 'otros' y
    // queda marcado en el detalle para que el asesor lo vea de una en "Por
    // cotizar" (no hay tarifario propio de reparto todavía, por eso siempre
    // pasa a modo asesor).
    const cargo = serviceType.value === 'mudanza'
      ? { ...quote.cargo, category: 'mudanza' }
      : serviceType.value === 'reparto'
        ? { ...quote.cargo, category: 'otros', detail: `[REPARTO] ${quote.cargo.detail}`.trim() }
        : {
            ...quote.cargo, truckType: chosenTruck.value || undefined,
            weightKg: estimatedWeightKg.value, volumeM3: estimatedVolumeM3.value,
          }
    const quoteMode = serviceType.value === 'carga' && chosenTruck.value ? 'por_vehiculo' : 'por_carga'
    const validStops = serviceType.value === 'carga' ? stops.filter(s => s.district) : []
    const wantsOwnPrice = serviceType.value === 'carga' && continueMode.value === 'propio'
    const payload = {
      ...quote, cargo, quoteMode, stops: validStops, serviceType: serviceType.value,
      proposedPrice: wantsOwnPrice ? quote.proposedPrice : null,
      priceNegotiable: wantsOwnPrice ? quote.priceNegotiable : true,
    }
    result.value = await guestQuote(payload, photos.value)
    phase.value = 'result'
  } catch (e) { error.value = e.message } finally { busy.value = false }
}

const signup = reactive({ password: '', isCompany: false, ruc: '', razonSocial: '', website: '' })
const showPwd = ref(false)
const signupOk = computed(() => signup.password.length >= 8)
const submitSignup = async () => {
  busy.value = true
  error.value = ''
  try {
    await guestSignup({
      quoteCode: result.value?.quoteCode,
      phone: quote.contact.phone,
      name: quote.contact.name,
      email: quote.contact.email || undefined,
      password: signup.password,
      isCompany: signup.isCompany,
      ruc: signup.ruc || undefined,
      razonSocial: signup.razonSocial || undefined,
      website: signup.website,
    })
    await auth.reload()
    router.push('/portal/cliente/mis-cargas')
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
</script>

<template>
  <div class="d-flex justify-center pa-4" style="min-height: 100vh; background: rgb(var(--v-theme-background));">
    <div style="width: 100%; max-width: 960px;">
      <div class="text-center my-6">
        <div class="text-h5 font-weight-bold">Lima Express</div>
        <div class="text-body-2 text-medium-emphasis">Cotización rápida</div>
      </div>

      <VRow>
      <VCol cols="12" md="7">
      <VStepper v-if="phase === 'form'" v-model="step" flat class="bg-transparent route-stepper mb-4" hide-actions>
        <VStepperHeader>
          <template v-for="(label, i) in stepperItems" :key="i">
            <VStepperItem :title="label" :value="i + 1" :complete="step > i + 1" color="primary" />
            <VDivider v-if="i < stepperItems.length - 1" />
          </template>
        </VStepperHeader>
      </VStepper>

      <VCard>
        <!-- Paso 1: formulario -->
        <VCardText v-if="phase === 'form'">
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
                    @click="serviceType = s.value"
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

              <template v-if="serviceType">
                <VDivider class="mb-3" />
                <template v-if="serviceType === 'reparto'">
                  <div class="d-flex align-center ga-2 mb-3">
                    <VAvatar size="28" color="primary" variant="tonal"><VIcon icon="ri-map-pin-line" size="16" /></VAvatar>
                    <span class="text-subtitle-2 font-weight-bold">Ingresa la ruta de tu reparto</span>
                  </div>
                  <VRow dense>
                    <VCol cols="12" sm="6">
                      <AddressAutocomplete v-model="quote.origin" label="Punto de recojo / almacén" />
                    </VCol>
                    <VCol cols="12" sm="6">
                      <AddressAutocomplete v-model="quote.destination" label="Zona de reparto (referencia)" />
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
                      <DistrictAutocomplete v-model="quote.origin" label="Origen" hide-icons class="mb-4" />

                      <template v-if="serviceType === 'carga'">
                        <div v-for="(stop, i) in stops" :key="i" class="d-flex align-center ga-2 mb-4">
                          <DistrictAutocomplete v-model="stops[i]" :label="`Parada ${i + 1}`" hide-icons class="flex-grow-1" />
                          <VBtn icon variant="text" size="small" @click="removeStop(i)">
                            <VIcon icon="ri-close-line" />
                          </VBtn>
                        </div>
                      </template>

                      <DistrictAutocomplete v-model="quote.destination" label="Destino" hide-icons />
                    </div>
                  </div>

                  <template v-if="serviceType === 'carga'">
                    <VBtn variant="text" size="small" prepend-icon="ri-add-line" class="mt-3" @click="addStop">
                      Agregar parada
                    </VBtn>
                    <p class="text-caption text-medium-emphasis mt-1 mb-0">Puedes añadir paradas intermedias (opcional).</p>
                  </template>
                </template>
              </template>
            </VWindowItem>

            <VWindowItem :value="2">
              <template v-if="serviceType === 'carga'">
                <div class="text-h6 font-weight-bold mb-1">¿Qué vas a transportar?</div>
                <p class="text-caption text-medium-emphasis mb-4">
                  Describe tu carga con el mayor detalle posible para recibir mejores cotizaciones. Indica peso aprox. y volumen aprox.
                </p>
                <VTextarea
                  v-model="quote.cargo.detail" rows="4" auto-grow density="comfortable" class="mb-4"
                  counter maxlength="500" placeholder="Ej: 40 cajas de repuestos automotrices, peso total 500 kg y volumen aprox. 2 m³"
                />
              </template>
              <template v-else-if="serviceType === 'mudanza'">
                <div class="text-h6 font-weight-bold mb-4">¿Qué vas a mudar?</div>
                <VTextarea
                  v-model="quote.cargo.detail" rows="2" auto-grow density="comfortable" class="mb-2"
                  label="Ambientes, pisos, ascensor, muebles grandes (opcional)"
                />
              </template>
              <template v-else>
                <div class="text-h6 font-weight-bold mb-4">Contanos tu operación de reparto</div>
                <VTextarea
                  v-model="quote.cargo.detail" rows="2" auto-grow density="comfortable" class="mb-2"
                  label="Cuántos pedidos, frecuencia, si es ecommerce o contra-entrega (opcional)"
                />
              </template>

              <CargoPhotosPicker v-model="photos" class="mb-2" />

              <VAlert v-if="hasSuggestedQuestion" type="info" variant="tonal" density="comfortable" class="mt-2">
                <div class="mb-2">{{ suggestedQuestion.text }}</div>
                <div class="d-flex align-center ga-2 flex-wrap">
                  <VTextField
                    v-model="questionAnswer" type="number" density="compact" hide-details style="max-width: 140px;"
                    :suffix="suggestedQuestion.unit" @keyup.enter="answerSuggestedQuestion"
                  />
                  <VBtn size="small" color="primary" variant="tonal" :loading="answeringQuestion" @click="answerSuggestedQuestion">
                    Estimar precio
                  </VBtn>
                  <VBtn size="small" variant="text" @click="suggestedQuestion = null">Continuar sin precio</VBtn>
                </div>
              </VAlert>

              <VAlert v-else-if="cargoEstimateFailed" type="info" variant="tonal" density="comfortable" class="mt-2">
                No pudimos calcular el precio estimado por falta de detalle de carga (peso, cantidad, volumen, etc.).
                Podés editar la descripción, agregar fotos, o continuar así sin precio, no hay problema.
              </VAlert>

              <template v-if="serviceType === 'carga'">
                <VDivider class="my-3" />
                <!-- Compartido/Exclusivo solo existe en rutas interprovinciales —
                     Consolidada nunca es una opción real dentro de una misma
                     ciudad, así que ni se pregunta ahí. -->
                <template v-if="isInterprovincial">
                  <div class="text-subtitle-2 font-weight-bold mb-2">¿Cómo querés tu carga?</div>
                  <VBtnToggle
                    :model-value="quote.loadMode" color="primary" variant="outlined" divided
                    density="comfortable" mandatory class="load-mode-toggle mb-2"
                    @update:model-value="setLoadMode"
                  >
                    <VBtn value="parcial" class="px-6">
                      Compartido
                      <VChip v-if="recommendedMode === 'compartido' && !modalityTouched" size="x-small" color="primary" variant="flat" class="ml-2">Recomendado</VChip>
                    </VBtn>
                    <VBtn value="completa" class="px-6">
                      Exclusivo
                      <VChip v-if="recommendedMode === 'exclusivo' && !modalityTouched" size="x-small" color="primary" variant="flat" class="ml-2">Recomendado</VChip>
                    </VBtn>
                  </VBtnToggle>
                  <p class="text-caption text-medium-emphasis mb-3">
                    {{ quote.loadMode === 'parcial'
                      ? 'Tu carga viaja junto con otra — más económico.'
                      : 'Un camión solo para tu carga — más rápido.' }}
                  </p>
                </template>

                <template v-if="!isInterprovincial || quote.loadMode === 'completa'">
                  <div class="d-flex align-start ga-3">
                    <VAvatar size="40" color="primary" variant="tonal"><VIcon icon="ri-truck-line" /></VAvatar>
                    <div class="flex-grow-1">
                      <div class="text-subtitle-2 font-weight-bold">¿Quieres elegir vehículo?</div>
                      <div class="text-caption text-medium-emphasis mb-2">
                        Opcional — si no elegís, te asignamos la mejor opción disponible.
                      </div>
                      <VChip v-if="chosenTruck" closable color="primary" variant="tonal" @click:close="chosenTruck = null">
                        {{ chosenTruckLabel }}
                      </VChip>
                      <VBtn v-else variant="outlined" size="small" @click="showVehiclePicker = true">Elegir vehículo</VBtn>
                    </div>
                  </div>
                  <VehiclePickerDialog
                    v-model="showVehiclePicker"
                    :estimated-weight-kg="estimatedWeightKg" :estimated-volume-m3="estimatedVolumeM3"
                    @select="v => chosenTruck = v" @clear="chosenTruck = null"
                  />
                </template>
              </template>
            </VWindowItem>

            <VWindowItem :value="3">
              <template v-if="serviceType === 'carga'">
                <VAlert v-if="hasStops" type="info" variant="tonal" class="mb-4">
                  Con paradas intermedias, un asesor te confirma el precio.
                </VAlert>
                <ContinueModePicker
                  :mode="continueMode" :price="quote.proposedPrice" :negotiable="quote.priceNegotiable"
                  @update:mode="v => continueMode = v" @update:price="v => quote.proposedPrice = v"
                  @update:negotiable="v => quote.priceNegotiable = v"
                />
                <VDivider class="my-4" />
              </template>
              <ScheduleStepPicker
                :date="quote.date" :schedule="quote.schedule"
                @update:date="v => quote.date = v" @update:schedule="v => quote.schedule = v"
              />
              <VDivider class="my-4" />
              <div class="text-subtitle-2 mb-2">¿Cómo te contactamos?</div>
              <VTextField v-model="quote.contact.name" label="Tu nombre" density="comfortable" class="mb-2" />
              <VTextField v-model="quote.contact.phone" label="Teléfono / WhatsApp" density="comfortable" class="mb-2" />
              <VTextField v-model="quote.contact.email" label="Correo (opcional)" type="email" density="comfortable" />
              <p v-if="serviceType !== 'carga'" class="text-caption text-medium-emphasis mt-1 mb-0">
                La dirección exacta de recojo y entrega se confirma al reservar.
              </p>
              <VAlert v-if="error" type="error" variant="tonal" class="mt-3">{{ error }}</VAlert>
            </VWindowItem>
          </VWindow>

          <input v-model="quote.website" type="text" tabindex="-1" autocomplete="off" style="position:absolute; left:-9999px;" aria-hidden="true">
        </VCardText>
        <VCardActions v-if="phase === 'form'" class="px-4 pb-4">
          <VBtn v-if="step > 1" variant="text" @click="step--">Atrás</VBtn>
          <VBtn v-else variant="text" to="/login">Ya tengo cuenta</VBtn>
          <VSpacer />
          <VBtn v-if="step === 1" color="primary" variant="elevated" rounded="lg" size="large" min-width="180" :disabled="!step1ok" @click="step = 2">Siguiente</VBtn>
          <VBtn
            v-else-if="step < maxStep" color="primary" variant="elevated" rounded="lg" size="large" min-width="180"
            :loading="goingToStep3" @click="goToStep3"
          >
            Siguiente
          </VBtn>
          <VBtn v-else color="primary" variant="elevated" rounded="lg" size="large" min-width="180" :loading="busy" :disabled="!formOk" @click="submitQuote">Cotizar</VBtn>
        </VCardActions>

        <!-- Paso 2: resultado -->
        <VCardText v-else-if="phase === 'result'" class="text-center py-6">
          <template v-if="result.price.amount != null">
            <div class="text-body-2 text-medium-emphasis">{{ result.route }}</div>
            <div class="text-h3 font-weight-bold my-3">{{ soles(result.price.amount) }}</div>
            <div v-if="result.price.range" class="text-caption text-medium-emphasis">
              Rango estimado {{ soles(result.price.range[0]) }} – {{ soles(result.price.range[1]) }}
            </div>
            <div v-if="result.price.daysEstimated" class="text-caption text-medium-emphasis">
              Llega en {{ result.price.daysEstimated }} días hábiles aprox.
            </div>
          </template>
          <template v-else>
            <VIcon icon="ri-checkbox-circle-line" color="success" size="40" class="mb-2" />
            <div class="text-h6">Solicitud recibida</div>
            <div class="text-body-2 font-weight-medium mt-1">{{ result.quoteCode }} · {{ result.route }}</div>
            <div class="text-body-2 text-medium-emphasis mt-2">Estamos buscando la mejor alternativa para vos.</div>
            <div class="text-body-2 text-medium-emphasis">Te avisaremos apenas tengamos precio, también por WhatsApp.</div>
          </template>
          <VDivider class="my-4" />
          <p class="text-body-2 mb-3">
            Creá tu cuenta para publicar la solicitud, negociar el precio y seguir el servicio.
          </p>
          <VBtn color="primary" block @click="phase = 'signup'">Crear cuenta y continuar</VBtn>
          <VBtn variant="text" block class="mt-2" to="/login">Ya tengo cuenta</VBtn>
        </VCardText>

        <!-- Paso 3: alta -->
        <template v-else>
          <VCardText>
            <div class="text-subtitle-1 font-weight-medium mb-3">Creá tu cuenta</div>
            <VTextField :model-value="quote.contact.name" label="Nombre" readonly variant="filled" density="comfortable" class="mb-2" />
            <VTextField :model-value="quote.contact.phone" label="Teléfono" readonly variant="filled" density="comfortable" class="mb-2" />
            <VTextField
              v-model="signup.password" label="Contraseña (mín. 8 caracteres)" density="comfortable" class="mb-3"
              :type="showPwd ? 'text' : 'password'" autocomplete="new-password"
              :append-inner-icon="showPwd ? 'ri-eye-off-line' : 'ri-eye-line'"
              @click:append-inner="showPwd = !showPwd"
            />
            <VCheckbox v-model="signup.isCompany" label="Es una empresa" density="compact" hide-details />
            <template v-if="signup.isCompany">
              <VTextField v-model="signup.razonSocial" label="Razón social" density="comfortable" class="mt-2 mb-2" />
              <VTextField v-model="signup.ruc" label="RUC" density="comfortable" />
            </template>
            <input v-model="signup.website" type="text" tabindex="-1" autocomplete="off" style="position:absolute; left:-9999px;" aria-hidden="true">
            <VAlert v-if="error" type="error" variant="tonal" class="mt-3">{{ error }}</VAlert>
          </VCardText>
          <VCardActions class="px-4 pb-4">
            <VBtn variant="text" @click="phase = 'result'">Atrás</VBtn>
            <VSpacer />
            <VBtn color="primary" :loading="busy" :disabled="!signupOk" @click="submitSignup">Crear cuenta</VBtn>
          </VCardActions>
        </template>
      </VCard>
      </VCol>

      <VCol cols="12" md="5">
        <QuoteSummaryPanel
          :service-label="SERVICE_TYPES.find(s => s.value === serviceType)?.title"
          :origin="quote.origin" :destination="quote.destination" :stops="stops"
          :detail="quote.cargo.detail" :date="quote.date"
          :truck-label="chosenTruckLabel"
          :estimated-weight-kg="estimatedWeightKg" :estimated-volume-m3="estimatedVolumeM3"
          :price-estimate="priceEstimate"
          @edit-type="step = 1"
        />
      </VCol>
      </VRow>
    </div>
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

/* Timeline compacto, sin caja/sombra/fondo propio — ver mismo criterio en
   portal/cliente/publicar/index.vue. bg-transparent no le gana al fondo
   del VSheet base de VStepper, por eso se fuerza acá con !important. */
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

/* El tema (Materio) fuerza en .v-btn-toggle un ancho fijo de 44/52px por
   botón (pensado para toggles de solo ícono) — con texto ("Compartido"/
   "Exclusivo") eso los aplasta. Mismo fix que ContinueModePicker.vue. */
:deep(.load-mode-toggle.v-btn-toggle .v-btn) {
  inline-size: auto !important;
  block-size: 40px !important;
}
</style>
