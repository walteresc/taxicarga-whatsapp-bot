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

const CATEGORIES = [
  { title: 'Cajas, paquetes y bultos', value: 'cajas' },
  { title: 'Mercadería comercial', value: 'mercaderia' },
  { title: 'Maquinaria y equipos', value: 'maquinaria' },
  { title: 'Materiales de construcción', value: 'construccion' },
  { title: 'Pallets / parihuelas', value: 'pallets' },
  { title: 'Otros', value: 'otros' },
]
const step = ref(1)
const form = reactive({
  origin: { district: '', address: '', floor: null, province: '', region: '', lat: null, lng: null },
  destination: { district: '', address: '', floor: null, province: '', region: '', lat: null, lng: null },
  cargo: { category: 'cajas', detail: '', weightKg: '', volumeM3: '', operators: null, truckType: null },
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
  else if (value === 'reparto') form.cargo.category = 'otros'
  else if (form.cargo.category === 'mudanza') form.cargo.category = 'cajas'
  step.value = 2   // avanza directo — ver los campos no debería depender de otro clic
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
      cargo: { category: form.cargo.category, weightKg: form.cargo.weightKg },
    })
    form.loadMode = pricePreview.value.consolidated ? 'parcial' : 'completa'
  } catch (e) { pricePreview.value = null } finally { previewLoading.value = false }
}

const stepperItems = computed(() => serviceType.value === 'carga'
  ? ['Servicio', 'Carga', 'Precio', 'Confirmar']
  : ['Servicio', 'Carga', 'Confirmar'])
const maxStep = computed(() => serviceType.value === 'carga' ? 4 : 3)
const loadModeLabel = computed(() => (form.loadMode === 'parcial' ? 'Carga consolidada' : 'Carga express'))

const goToStep3 = async () => {
  step.value = 3
  if (serviceType.value === 'carga') await fetchPricePreview()
}

const submitting = ref(false)
const result = ref(null)
const error = ref('')

const step1ok = computed(() => !!serviceType.value)
const step2ok = computed(() => {
  if (!(form.origin.district && form.destination.district)) return false

  return form.quoteMode === 'por_vehiculo' ? !!form.cargo.truckType : !!form.cargo.category
})
const submitted = ref(false)

const submit = async () => {
  submitting.value = true
  error.value = ''
  try {
    // El cotizador solo conoce categorías de carga — Reparto se manda como
    // 'otros' marcado en el detalle (ver mismo criterio en /cotizar).
    const cargo = serviceType.value === 'reparto'
      ? { ...form.cargo, detail: `[REPARTO] ${form.cargo.detail}`.trim() }
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
const categoryLabel = computed(() => {
  if (form.quoteMode === 'por_vehiculo') return form.cargo.truckType
  if (serviceType.value === 'mudanza') return 'Mudanza'
  if (serviceType.value === 'reparto') return 'Reparto'

  return CATEGORIES.find(c => c.value === form.cargo.category)?.title
})
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
            <div class="text-subtitle-2 mb-2">¿Qué necesitas?</div>
            <VRow class="mb-2" dense>
              <VCol v-for="s in SERVICE_TYPES" :key="s.value" cols="12" sm="4">
                <VCard
                  :variant="serviceType === s.value ? 'tonal' : 'outlined'"
                  :color="serviceType === s.value ? 'primary' : undefined"
                  class="pa-3 text-center h-100" style="cursor: pointer;"
                  @click="selectService(s.value)"
                >
                  <VIcon :icon="s.icon" size="24" class="mb-1" />
                  <div class="text-body-2 font-weight-bold">{{ s.title }}</div>
                  <div class="text-caption text-medium-emphasis">{{ s.subtitle }}</div>
                </VCard>
              </VCol>
            </VRow>
          </template>

          <template #item.2>
            <template v-if="serviceType === 'reparto'">
              <VRow dense>
                <VCol cols="12" sm="6">
                  <div class="text-subtitle-2 mb-2">Origen</div>
                  <AddressAutocomplete v-model="form.origin" label="Punto de recojo / almacén" />
                </VCol>
                <VCol cols="12" sm="6">
                  <div class="text-subtitle-2 mb-2">Destino</div>
                  <AddressAutocomplete v-model="form.destination" label="Zona de reparto (referencia)" />
                </VCol>
              </VRow>
            </template>
            <template v-else>
              <VRow dense>
                <VCol cols="12" sm="6">
                  <div class="text-subtitle-2 mb-2">Origen</div>
                  <DistrictAutocomplete v-model="form.origin" label="Distrito de origen" />
                  <VTextField v-model.number="form.origin.floor" label="Piso (opcional)" type="number" />
                </VCol>
                <VCol cols="12" sm="6">
                  <div class="text-subtitle-2 mb-2">Destino</div>
                  <DistrictAutocomplete v-model="form.destination" label="Distrito de destino" />
                  <VTextField v-model.number="form.destination.floor" label="Piso (opcional)" type="number" />
                </VCol>
              </VRow>

              <template v-if="serviceType === 'carga'">
                <VRow v-for="(stop, i) in stops" :key="i" dense>
                  <VCol cols="10" sm="11">
                    <DistrictAutocomplete v-model="stops[i]" :label="`Parada ${i + 1}`" />
                  </VCol>
                  <VCol cols="2" sm="1" class="d-flex align-center">
                    <VBtn icon variant="text" size="small" @click="removeStop(i)">
                      <VIcon icon="ri-close-line" />
                    </VBtn>
                  </VCol>
                </VRow>
                <VBtn variant="text" size="small" prepend-icon="ri-add-line" class="mb-2" @click="addStop">
                  Agregar parada (opcional)
                </VBtn>
              </template>

              <p class="text-caption text-medium-emphasis">
                La dirección exacta te la pedimos recién al reservar — para cotizar alcanza con el distrito.
              </p>
            </template>

            <VDivider class="my-3" />

            <template v-if="serviceType === 'carga'">
              <VSelect v-model="form.cargo.category" :items="CATEGORIES" label="Tipo de carga" class="mb-2" />
              <VTextarea v-model="form.cargo.detail" label="¿Qué vas a mover? (detalle)" rows="2" auto-grow class="mb-2" />
              <div class="d-flex ga-2 mb-2">
                <VTextField v-model="form.cargo.weightKg" label="Peso aprox. (kg)" type="number" />
                <VTextField v-model="form.cargo.volumeM3" label="Volumen aprox. (m³)" type="number" />
              </div>
              <VTextField v-model.number="form.cargo.operators" label="¿Necesitás operarios de carga? ¿Cuántos?" type="number" class="mb-2" />

              <div class="d-flex align-center ga-2 mb-2 flex-wrap">
                <span class="text-body-2 text-medium-emphasis">¿Ya sabés qué vehículo necesitás?</span>
                <VChip v-if="form.cargo.truckType" closable size="small" color="primary" variant="tonal" @click:close="clearTruck">
                  {{ chosenTruckLabel }}
                </VChip>
                <VBtn v-else size="small" variant="tonal" @click="showVehiclePicker = true">Elegir vehículo</VBtn>
                <span class="text-caption text-medium-emphasis">(opcional)</span>
              </div>
              <VehiclePickerDialog v-model="showVehiclePicker" @select="pickTruck" @clear="clearTruck" />
            </template>
            <template v-else-if="serviceType === 'mudanza'">
              <VTextarea
                v-model="form.cargo.detail" rows="2" auto-grow class="mb-2"
                label="Ambientes, pisos, ascensor, muebles grandes (opcional)"
              />
              <VTextField v-model.number="form.cargo.operators" label="¿Necesitás operarios para la mudanza? ¿Cuántos?" type="number" />
            </template>
            <template v-else-if="serviceType === 'reparto'">
              <VTextarea
                v-model="form.cargo.detail" rows="2" auto-grow class="mb-2"
                label="Cuántos pedidos, frecuencia, si es ecommerce o contra-entrega (opcional)"
              />
            </template>

            <VDivider class="my-3" />
            <CargoPhotosPicker v-model="photos" class="mb-2" />

            <VDivider class="my-3" />
            <ScheduleStepPicker
              :date="form.date" :schedule="form.schedule"
              @update:date="v => form.date = v" @update:schedule="v => form.schedule = v"
            />
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
              <VList density="compact">
                <VListItem
                  prepend-icon="ri-map-pin-line" :title="`${form.origin.district} → ${form.destination.district}`"
                  :subtitle="form.origin.address ? `${form.origin.address} → ${form.destination.address}` : 'La dirección exacta se confirma al reservar'"
                />
                <VListItem prepend-icon="ri-archive-line" :title="categoryLabel" :subtitle="form.cargo.detail || '—'" />
                <VListItem prepend-icon="ri-calendar-line" :title="form.date || 'Fecha por confirmar'" :subtitle="form.schedule || 'Horario por confirmar'" />
              </VList>
              <VAlert v-if="error" type="error" variant="tonal" class="mt-3">{{ error }}</VAlert>
            </template>
          </template>

          <template #item.4>
            <VList density="compact">
              <VListItem
                prepend-icon="ri-map-pin-line" :title="`${form.origin.district} → ${form.destination.district}`"
                :subtitle="form.origin.address ? `${form.origin.address} → ${form.destination.address}` : 'La dirección exacta se confirma al reservar'"
              />
              <VListItem prepend-icon="ri-archive-line" :title="categoryLabel" :subtitle="form.cargo.detail || '—'" />
              <VListItem v-if="!hasStops" prepend-icon="ri-scales-3-line" :title="loadModeLabel" />
              <VListItem
                v-if="continueMode === 'propio' && form.proposedPrice"
                prepend-icon="ri-price-tag-3-line" :title="`Tu precio: S/ ${form.proposedPrice}`"
                :subtitle="form.priceNegotiable ? 'Negociable' : 'Fijo'"
              />
              <VListItem prepend-icon="ri-calendar-line" :title="form.date || 'Fecha por confirmar'" :subtitle="form.schedule || 'Horario por confirmar'" />
            </VList>
            <VAlert v-if="error" type="error" variant="tonal" class="mt-3">{{ error }}</VAlert>
          </template>

        </VStepper>
      </VCardText>

      <VCardActions class="px-4 pb-4">
        <VBtn v-if="step > 1" variant="text" @click="step--">Atrás</VBtn>
        <VSpacer />
        <VBtn v-if="step === 1" color="primary" :disabled="!step1ok" @click="step = 2">Siguiente</VBtn>
        <VBtn v-else-if="step === 2" color="primary" :disabled="!step2ok" @click="goToStep3">Siguiente</VBtn>
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
