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
import { guestCargoEstimate, guestQuotePreview } from '@/services/guestService'
import { extractVolumeM3, extractWeightKg, recomendarModalidad } from '@/utils/cargoText'

const router = useRouter()

// "¿Qué necesitas?" — mismo criterio que /cotizar (invitado): de cara al
// cliente el negocio se presenta en 3 líneas (Carga/Mudanzas/Reparto), por
// dentro las 3 siguen siendo una "carga" con distinta categoría/detalle.
const SERVICE_TYPES = [
  { value: 'carga', icon: 'ri-truck-line', title: 'Carga', subtitle: 'Encomiendas, paquetes o carga nacional.' },
  { value: 'mudanza', icon: 'ri-home-4-line', title: 'Mudanzas', subtitle: 'Casa, oficina o empresa.' },
  { value: 'reparto', icon: 'ri-e-bike-2-line', title: 'Entregas', subtitle: 'Reparto, distribución y última milla.' },
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
  priceNegotiable: true,
})
const continueMode = ref('ofertas')   // 'ofertas' | 'propio' — solo Carga

const showVehiclePicker = ref(false)
const chosenTruckLabel = computed(() => form.cargo.truckType || '')

const selectService = value => {
  serviceType.value = value
  form.quoteMode = 'por_carga'   // "elegir vehículo" solo aplica a Carga
  form.cargo.truckType = null
  if (value === 'mudanza') form.cargo.category = 'mudanza'
  else form.cargo.category = 'otros'
}
const pickTruck = value => { form.cargo.truckType = value; form.quoteMode = 'por_vehiculo' }
const clearTruck = () => { form.cargo.truckType = null; form.quoteMode = 'por_carga' }

// Paradas intermedias (multipunto) — solo Carga. Ver cotizar.vue: el motor de
// precios no las contempla, así que una solicitud con paradas siempre pasa a
// modo asesor, a propósito.
const photos = ref([])
const stops = reactive([])
const addStop = () => stops.push({ district: '', province: '', region: '', lat: null, lng: null })
const removeStop = index => stops.splice(index, 1)
const hasStops = computed(() => stops.some(s => s.district))
const step1ok = computed(() => !!(serviceType.value && form.origin.district && form.destination.district))

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
  !suggestedQuestion.value && form.cargo.detail.trim() &&
  estimatedWeightKg.value == null && estimatedVolumeM3.value == null)
const hasSuggestedQuestion = computed(() =>
  serviceType.value === 'carga' && !estimatingCargo.value && !estimatePending.value &&
  !answeringQuestion.value && !!suggestedQuestion.value)

let estimateDebounce = null
const estimateCargo = async () => {
  estimatePending.value = false
  const text = form.cargo.detail
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
watch([() => form.cargo.detail, photos], () => {
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
    const augmented = `${form.cargo.detail}\n${question.text}: ${questionAnswer.value} ${question.unit}`
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
      origin: form.origin, destination: form.destination, serviceType: serviceType.value,
      cargo: { category: form.cargo.category, weightKg: estimatedWeightKg.value },
    })
  } catch (e) { pricePreview.value = null } finally { previewLoading.value = false }
}
watch([() => serviceType.value, () => form.origin.district, () => form.destination.district,
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
  if (serviceType.value !== 'carga') return null
  if (hasStops.value) return { mode: 'advisor', text: 'Un asesor te confirma el precio (hay paradas intermedias).' }
  if (previewLoading.value) return { mode: 'loading' }
  if (!pricePreview.value) return null
  const { express, consolidated } = pricePreview.value
  if (!modalityTouched.value && recommendedMode.value === 'rango' && express?.amount != null && consolidated?.amount != null) {
    return { mode: 'rango', text: `Desde ${soles(consolidated.amount)} hasta ${soles(express.amount)} aprox.`, sub: 'según el transportista' }
  }
  const chosen = form.loadMode === 'parcial' ? consolidated : express
  if (!chosen || chosen.amount == null) return { mode: 'advisor', text: 'Un asesor te confirma el precio.' }

  return {
    mode: 'unico', text: soles(chosen.amount),
    sub: chosen.range && chosen.range[0] !== chosen.range[1] ? `Rango ${soles(chosen.range[0])} – ${soles(chosen.range[1])}` : null,
  }
})

// 3 pasos siempre: "Servicio y ruta" → "Detalles" → "Reserva". El precio
// (Carga) vive en el panel lateral, no en un paso propio; "¿cómo quieres
// continuar?" se sumó al paso Reserva.
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
      priceNegotiable: wantsOwnPrice ? form.priceNegotiable : true,
    }
    result.value = await customerPublish(payload, photos.value)
    submitted.value = true
  } catch (e) { error.value = e.message || 'No se pudo publicar.' } finally { submitting.value = false }
}
</script>

<template>
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
                Describe tu carga con el mayor detalle posible para recibir mejores cotizaciones. Indica peso aprox. y volumen aprox.
              </p>
              <VTextarea
                v-model="form.cargo.detail" rows="4" auto-grow class="mb-4"
                counter maxlength="500" placeholder="Ej: 40 cajas de repuestos automotrices, peso total 500 kg y volumen aprox. 2 m³"
              />
            </template>
            <template v-else-if="serviceType === 'mudanza'">
              <div class="text-h6 font-weight-bold mb-4">¿Qué vas a mudar?</div>
              <VTextarea
                v-model="form.cargo.detail" rows="2" auto-grow class="mb-2"
                label="Ambientes, pisos, ascensor, muebles grandes (opcional)"
              />
              <VTextField v-model.number="form.cargo.operators" label="¿Necesitás operarios para la mudanza? ¿Cuántos?" type="number" />
            </template>
            <template v-else-if="serviceType === 'reparto'">
              <div class="text-h6 font-weight-bold mb-4">Contanos tu operación de reparto</div>
              <VTextarea
                v-model="form.cargo.detail" rows="2" auto-grow class="mb-2"
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
                  :model-value="form.loadMode" color="primary" variant="outlined" divided
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
                  {{ form.loadMode === 'parcial'
                    ? 'Tu carga viaja junto con otra — más económico.'
                    : 'Un camión solo para tu carga — más rápido.' }}
                </p>
              </template>

              <template v-if="!isInterprovincial || form.loadMode === 'completa'">
                <div class="d-flex align-start ga-3">
                  <VAvatar size="40" color="primary" variant="tonal"><VIcon icon="ri-truck-line" /></VAvatar>
                  <div class="flex-grow-1">
                    <div class="text-subtitle-2 font-weight-bold">¿Quieres elegir vehículo?</div>
                    <div class="text-caption text-medium-emphasis mb-2">
                      Opcional — si no elegís, te asignamos la mejor opción disponible.
                    </div>
                    <VChip v-if="form.cargo.truckType" closable color="primary" variant="tonal" @click:close="clearTruck">
                      {{ chosenTruckLabel }}
                    </VChip>
                    <VBtn v-else variant="outlined" size="small" @click="showVehiclePicker = true">Elegir vehículo</VBtn>
                  </div>
                </div>
                <VehiclePickerDialog
                  v-model="showVehiclePicker"
                  :estimated-weight-kg="estimatedWeightKg" :estimated-volume-m3="estimatedVolumeM3"
                  @select="pickTruck" @clear="clearTruck"
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
                :mode="continueMode" :price="form.proposedPrice" :negotiable="form.priceNegotiable"
                @update:mode="v => continueMode = v" @update:price="v => form.proposedPrice = v"
                @update:negotiable="v => form.priceNegotiable = v"
              />
              <VDivider class="my-4" />
            </template>
            <ScheduleStepPicker
              :date="form.date" :schedule="form.schedule"
              @update:date="v => form.date = v" @update:schedule="v => form.schedule = v"
            />
            <VAlert v-if="serviceType === 'carga'" type="info" variant="tonal" density="comfortable" class="mt-4">
              <div class="text-body-2 font-weight-medium mb-1">Dirección y datos de contacto</div>
              <div class="text-caption">
                La dirección exacta de recogida y entrega, así como tus datos de contacto, se confirmarán en el siguiente paso.
              </div>
            </VAlert>
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
          :loading="goingToStep3" @click="goToStep3"
        >
          Siguiente
        </VBtn>
        <VBtn
          v-else color="primary" variant="elevated" rounded="lg" size="large" min-width="180" :loading="submitting"
          :disabled="serviceType === 'carga' && continueMode === 'propio' && !form.proposedPrice"
          @click="submit"
        >
          Publicar y cotizar
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
        :price-estimate="priceEstimate"
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

/* El tema (Materio) fuerza en .v-btn-toggle un ancho fijo de 44/52px por
   botón (pensado para toggles de solo ícono) — con texto ("Compartido"/
   "Exclusivo") eso los aplasta. Mismo fix que ContinueModePicker.vue. */
:deep(.load-mode-toggle.v-btn-toggle .v-btn) {
  inline-size: auto !important;
  block-size: 40px !important;
}
</style>
