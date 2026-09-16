<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import AddressAutocomplete from '@/components/AddressAutocomplete.vue'
import CargoPhotosPicker from '@/components/CargoPhotosPicker.vue'
import ContinueModePicker from '@/components/ContinueModePicker.vue'
import DistrictAutocomplete from '@/components/DistrictAutocomplete.vue'
import PriceModePicker from '@/components/PriceModePicker.vue'
import QuoteSummaryPanel from '@/components/QuoteSummaryPanel.vue'
import ScheduleStepPicker from '@/components/ScheduleStepPicker.vue'
import VehiclePickerDialog from '@/components/VehiclePickerDialog.vue'
import { customerPublish } from '@/services/customerPortalService'
import { guestQuotePreview } from '@/services/guestService'

const router = useRouter()

// "¿Qué necesitas?" — mismo criterio que /cotizar (invitado): de cara al
// cliente el negocio se presenta en 3 líneas (Carga/Mudanzas/Reparto), por
// dentro las 3 siguen siendo una "carga" con distinta categoría/detalle.
const SERVICE_TYPES = [
  { value: 'carga', icon: 'ri-truck-line', title: 'Carga', subtitle: 'Paquetes, mercadería, pallets, maquinaria o carga nacional.' },
  { value: 'mudanza', icon: 'ri-home-4-line', title: 'Mudanzas', subtitle: 'Casa, departamento, oficina o empresa.' },
  { value: 'reparto', icon: 'ri-e-bike-2-line', title: 'Reparto', subtitle: 'Entregas a clientes, tiendas o múltiples destinos.' },
]
const serviceType = ref('carga')

// El mockup no tiene campos separados de categoría/peso/volumen para Carga —
// el cliente describe todo en un solo texto libre ("40 cajas..., peso total
// 500 kg..."). El motor de precios de Consolidada sí necesita un peso
// estructurado (ver apps/tercerizacion/services.py::resolver_tarifa_parcial),
// así que lo extraemos con una regex best-effort; si no lo encuentra, cae al
// modo "asesor confirma" — el mismo fallback que ya existía. Mismo criterio
// que /cotizar.vue.
const extractWeightKg = text => {
  if (!text) return null
  const t = text.toLowerCase()
  let m = t.match(/(\d+(?:[.,]\d+)?)\s*(?:kg|kilos?)\b/)
  if (m) return parseFloat(m[1].replace(',', '.'))
  m = t.match(/(\d+(?:[.,]\d+)?)\s*(?:ton(?:elada)?s?)\b/)
  if (m) return parseFloat(m[1].replace(',', '.')) * 1000

  return null
}
const extractVolumeM3 = text => {
  if (!text) return null
  const m = text.toLowerCase().match(/(\d+(?:[.,]\d+)?)\s*m\s*(?:3|³|cubicos?|cúbicos?)/)

  return m ? parseFloat(m[1].replace(',', '.')) : null
}

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

// Paso "Precio" (solo Carga, sin paradas): compara Consolidada vs. Express
// ANTES de publicar — no crea nada, es solo un precio de referencia (ver
// apps/cotizador/api/guest_views.py::PreviewQuoteView).
const pricePreview = ref(null)
const previewLoading = ref(false)
const fetchPricePreview = async () => {
  if (hasStops.value) { pricePreview.value = null; return }
  previewLoading.value = true
  try {
    pricePreview.value = await guestQuotePreview({
      origin: form.origin, destination: form.destination,
      cargo: { category: form.cargo.category, weightKg: extractWeightKg(form.cargo.detail) },
    })
    form.loadMode = pricePreview.value.consolidated ? 'parcial' : 'completa'
  } catch (e) { pricePreview.value = null } finally { previewLoading.value = false }
}

// Mismo timeline que las capturas: "Servicio y ruta" → "Detalles" → "Precio"
// (solo Carga) → "Reserva". Ver mismo criterio en /cotizar.vue.
const stepperItems = computed(() => serviceType.value === 'carga'
  ? ['Servicio y ruta', 'Detalles', 'Precio', 'Reserva']
  : ['Servicio y ruta', 'Detalles', 'Reserva'])
const maxStep = computed(() => serviceType.value === 'carga' ? 4 : 3)

const goToStep3 = async () => {
  step.value = 3
  if (serviceType.value === 'carga') await fetchPricePreview()
}

const submitting = ref(false)
const result = ref(null)
const error = ref('')

const step1ok = computed(() => !!(serviceType.value && form.origin.district && form.destination.district))
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
        ? { ...form.cargo, weightKg: extractWeightKg(form.cargo.detail), volumeM3: extractVolumeM3(form.cargo.detail) }
        : form.cargo
    const validStops = serviceType.value === 'carga' ? stops.filter(s => s.district) : []
    const wantsOwnPrice = serviceType.value === 'carga' && continueMode.value === 'propio'
    const payload = {
      ...form, cargo, stops: validStops,
      proposedPrice: wantsOwnPrice ? form.proposedPrice : null,
      priceNegotiable: wantsOwnPrice ? form.priceNegotiable : true,
    }
    result.value = await customerPublish(payload, photos.value)
    submitted.value = true
  } catch (e) { error.value = e.message || 'No se pudo publicar.' } finally { submitting.value = false }
}
const soles = n => (n == null ? null : `S/ ${Math.round(n).toLocaleString('es-PE')}`)
</script>

<template>
  <div>
    <h1 class="text-h5 font-weight-bold mb-4">Publicar solicitud</h1>

    <VRow>
    <VCol cols="12" md="7">
    <VCard v-if="!submitted">
      <VCardText>
        <VStepper v-model="step" flat :items="stepperItems" hide-actions>
          <template #item.1>
            <div class="text-subtitle-2 mb-1">Elige un tipo de servicio</div>
            <p class="text-caption text-medium-emphasis mb-3">Selecciona el tipo de servicio que mejor se adapte a tu necesidad.</p>
            <VRow class="mb-3" dense>
              <VCol v-for="s in SERVICE_TYPES" :key="s.value" cols="12" sm="4">
                <VCard
                  :variant="serviceType === s.value ? 'tonal' : 'outlined'"
                  :color="serviceType === s.value ? 'primary' : undefined"
                  class="pa-3 text-center h-100 position-relative" style="cursor: pointer;"
                  @click="selectService(s.value)"
                >
                  <VIcon
                    v-if="serviceType === s.value" icon="ri-checkbox-circle-fill" color="primary" size="18"
                    style="position:absolute; top:6px; right:6px;"
                  />
                  <VIcon :icon="s.icon" size="24" class="mb-1" />
                  <div class="text-body-2 font-weight-bold">{{ s.title }}</div>
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
              <p class="text-caption text-medium-emphasis mb-3">Indica los puntos de origen y destino para cotizar tu servicio.</p>

              <div class="d-flex align-center ga-2 mb-1">
                <VIcon icon="ri-record-circle-line" color="success" size="14" />
                <span class="text-caption text-medium-emphasis">Origen</span>
              </div>
              <DistrictAutocomplete v-model="form.origin" label="Distrito de origen" class="mb-1" />
              <VTextField v-if="serviceType === 'mudanza'" v-model.number="form.origin.floor" label="Piso (opcional)" type="number" class="mb-2" />

              <div class="d-flex align-center ga-2 mb-1" :class="serviceType === 'carga' ? 'mt-2' : ''">
                <VIcon icon="ri-map-pin-fill" color="primary" size="14" />
                <span class="text-caption text-medium-emphasis">Destino</span>
              </div>
              <DistrictAutocomplete v-model="form.destination" label="Distrito de destino" />
              <VTextField v-if="serviceType === 'mudanza'" v-model.number="form.destination.floor" label="Piso (opcional)" type="number" />

              <template v-if="serviceType === 'carga'">
                <VRow v-for="(stop, i) in stops" :key="i" dense class="mt-1">
                  <VCol cols="10" sm="11">
                    <DistrictAutocomplete v-model="stops[i]" :label="`Parada ${i + 1}`" />
                  </VCol>
                  <VCol cols="2" sm="1" class="d-flex align-center">
                    <VBtn icon variant="text" size="small" @click="removeStop(i)">
                      <VIcon icon="ri-close-line" />
                    </VBtn>
                  </VCol>
                </VRow>
                <VBtn variant="text" size="small" prepend-icon="ri-add-line" class="mt-2" @click="addStop">
                  Agregar parada
                </VBtn>
                <p class="text-caption text-medium-emphasis mt-1 mb-0">Puedes añadir paradas intermedias (opcional).</p>
              </template>
            </template>
          </template>

          <template #item.2>
            <template v-if="serviceType === 'carga'">
              <div class="text-subtitle-2 mb-1">¿Qué vas a transportar?</div>
              <p class="text-caption text-medium-emphasis mb-2">
                Describe tu carga con el mayor detalle posible para recibir mejores cotizaciones. Indica peso aprox. y volumen aprox.
              </p>
              <VTextarea
                v-model="form.cargo.detail" rows="4" auto-grow class="mb-4"
                counter maxlength="500" placeholder="Ej: 40 cajas de repuestos automotrices, peso total 500 kg y volumen aprox. 2 m³"
              />
            </template>
            <template v-else-if="serviceType === 'mudanza'">
              <div class="text-subtitle-2 mb-2">¿Qué vas a mudar?</div>
              <VTextarea
                v-model="form.cargo.detail" rows="2" auto-grow class="mb-2"
                label="Ambientes, pisos, ascensor, muebles grandes (opcional)"
              />
              <VTextField v-model.number="form.cargo.operators" label="¿Necesitás operarios para la mudanza? ¿Cuántos?" type="number" />
            </template>
            <template v-else-if="serviceType === 'reparto'">
              <div class="text-subtitle-2 mb-2">Contanos tu operación de reparto</div>
              <VTextarea
                v-model="form.cargo.detail" rows="2" auto-grow class="mb-2"
                label="Cuántos pedidos, frecuencia, si es ecommerce o contra-entrega (opcional)"
              />
            </template>

            <CargoPhotosPicker v-model="photos" class="mb-2" />

            <template v-if="serviceType === 'carga'">
              <VDivider class="my-3" />
              <div class="d-flex align-start ga-3">
                <VAvatar size="40" color="primary" variant="tonal"><VIcon icon="ri-truck-line" /></VAvatar>
                <div class="flex-grow-1">
                  <div class="text-subtitle-2 font-weight-bold">¿Quieres elegir vehículo?</div>
                  <div class="text-caption text-medium-emphasis mb-2">
                    Puedes elegir un tipo de vehículo para tu carga o continuar sin seleccionar uno. TaxiCarga te asignará la mejor opción disponible.
                  </div>
                  <VChip v-if="form.cargo.truckType" closable color="primary" variant="tonal" @click:close="clearTruck">
                    {{ chosenTruckLabel }}
                  </VChip>
                  <VBtn v-else variant="tonal" size="small" @click="showVehiclePicker = true">Elegir vehículo</VBtn>
                </div>
              </div>
              <VehiclePickerDialog v-model="showVehiclePicker" @select="pickTruck" @clear="clearTruck" />
            </template>
          </template>

          <template #item.3>
            <template v-if="serviceType === 'carga'">
              <div class="text-subtitle-2 mb-2">Elegí cómo cotizar tu carga</div>
              <template v-if="hasStops">
                <VAlert type="info" variant="tonal">
                  Con paradas intermedias, un asesor te confirma el precio — no aplica Consolidada/Express.
                </VAlert>
              </template>
              <PriceModePicker
                v-else v-model="form.loadMode" :loading="previewLoading"
                :express="pricePreview?.express" :consolidated="pricePreview?.consolidated"
              />

              <VDivider class="my-4" />
              <ContinueModePicker
                :mode="continueMode" :price="form.proposedPrice" :negotiable="form.priceNegotiable"
                @update:mode="v => continueMode = v" @update:price="v => form.proposedPrice = v"
                @update:negotiable="v => form.priceNegotiable = v"
              />
            </template>
            <template v-else>
              <ScheduleStepPicker
                :date="form.date" :schedule="form.schedule"
                @update:date="v => form.date = v" @update:schedule="v => form.schedule = v"
              />
              <VAlert v-if="error" type="error" variant="tonal" class="mt-3">{{ error }}</VAlert>
            </template>
          </template>

          <template #item.4>
            <ScheduleStepPicker
              :date="form.date" :schedule="form.schedule"
              @update:date="v => form.date = v" @update:schedule="v => form.schedule = v"
            />
            <VAlert type="info" variant="tonal" density="comfortable" class="mt-4">
              <div class="text-body-2 font-weight-medium mb-1">Dirección y datos de contacto</div>
              <div class="text-caption">
                La dirección exacta de recogida y entrega, así como tus datos de contacto, se confirmarán en el siguiente paso.
              </div>
            </VAlert>
            <VAlert v-if="error" type="error" variant="tonal" class="mt-3">{{ error }}</VAlert>
          </template>

        </VStepper>
      </VCardText>

      <VCardActions class="px-4 pb-4">
        <VBtn v-if="step > 1" variant="text" @click="step--">Atrás</VBtn>
        <VSpacer />
        <VBtn v-if="step === 1" color="primary" :disabled="!step1ok" @click="step = 2">Siguiente</VBtn>
        <VBtn v-else-if="step === 2" color="primary" @click="goToStep3">Siguiente</VBtn>
        <VBtn v-else-if="step < maxStep" color="primary" @click="step++">Siguiente</VBtn>
        <VBtn
          v-else color="primary" :loading="submitting"
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
      />
    </VCol>
    </VRow>
  </div>
</template>
