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
import { guestQuote, guestQuotePreview, guestSignup } from '@/services/guestService'
import { useAuthStore } from '@/stores/authStore'

const router = useRouter()
const auth = useAuthStore()

// "¿Qué necesitas?" — de cara al cliente el negocio se presenta en 3 líneas
// (Carga / Mudanzas / Reparto); por dentro las 3 pasan por el mismo cotizador
// de invitado, solo cambia qué categoría de `cargo` mandamos.
const SERVICE_TYPES = [
  { value: 'carga', icon: 'ri-truck-line', title: 'Carga', subtitle: 'Paquetes, mercadería, pallets, maquinaria o carga nacional.' },
  { value: 'mudanza', icon: 'ri-home-4-line', title: 'Mudanzas', subtitle: 'Trasladar una casa, departamento, oficina o empresa.' },
  { value: 'reparto', icon: 'ri-e-bike-2-line', title: 'Reparto', subtitle: 'Entregar pedidos a clientes, tiendas o múltiples destinos.' },
]
const serviceType = ref('')

const CATEGORIES = [
  { title: 'Cajas, paquetes y bultos', value: 'cajas' },
  { title: 'Mercadería comercial', value: 'mercaderia' },
  { title: 'Maquinaria y equipos', value: 'maquinaria' },
  { title: 'Materiales de construcción', value: 'construccion' },
  { title: 'Otros', value: 'otros' },
]

// Elegir vehículo es opcional y no aplica a Mudanza/Reparto — por defecto
// "que TaxiCarga elija" (quoteMode 'por_carga', sin truckType). El picker
// trae sus propias opciones del catálogo real (apps/catalogo) y emite
// directamente el nombre de la unidad elegida (p. ej. "Camión 4 ton").
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
  cargo: { category: 'cajas', detail: '', weightKg: '' },
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
      origin: quote.origin, destination: quote.destination,
      cargo: { category: quote.cargo.category, weightKg: quote.cargo.weightKg },
    })
    quote.loadMode = pricePreview.value.consolidated ? 'parcial' : 'completa'
  } catch (e) { pricePreview.value = null } finally { previewLoading.value = false }
}

// Mismo timeline que las capturas: "Servicio y ruta" → "Detalles" → "Precio"
// (solo Carga) → "Reserva". El resumen/mapa de la derecha (QuoteSummaryPanel)
// hace de confirmación permanente — no hace falta un paso final de "revisar
// todo" aparte, por eso Reserva ya incluye los datos de contacto y termina
// en el botón de publicar.
const stepperItems = computed(() => serviceType.value === 'carga'
  ? ['Servicio y ruta', 'Detalles', 'Precio', 'Reserva']
  : ['Servicio y ruta', 'Detalles', 'Reserva'])
const maxStep = computed(() => serviceType.value === 'carga' ? 4 : 3)

const soles = n => (n == null ? null : `S/ ${Math.round(n).toLocaleString('es-PE')}`)
const step1ok = computed(() => !!(serviceType.value && quote.origin.district && quote.destination.district))
const formOk = computed(() => {
  if (!(step1ok.value && quote.contact.phone && quote.contact.name)) return false
  if (serviceType.value === 'carga' && continueMode.value === 'propio' && !quote.proposedPrice) return false

  return true
})
const goToStep3 = async () => {
  step.value = 3
  if (serviceType.value === 'carga') await fetchPricePreview()
}

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
        : { ...quote.cargo, truckType: chosenTruck.value || undefined }
    const quoteMode = serviceType.value === 'carga' && chosenTruck.value ? 'por_vehiculo' : 'por_carga'
    const validStops = serviceType.value === 'carga' ? stops.filter(s => s.district) : []
    const wantsOwnPrice = serviceType.value === 'carga' && continueMode.value === 'propio'
    const payload = {
      ...quote, cargo, quoteMode, stops: validStops,
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
      <VCard>
        <!-- Paso 1: formulario -->
        <VCardText v-if="phase === 'form'">
          <VStepper v-model="step" flat :items="stepperItems" hide-actions>
            <template #item.1>
              <div class="text-subtitle-2 mb-2">Elige un tipo de servicio</div>
              <VRow class="mb-3" dense>
                <VCol v-for="s in SERVICE_TYPES" :key="s.value" cols="12" sm="4">
                  <VCard
                    :variant="serviceType === s.value ? 'tonal' : 'outlined'"
                    :color="serviceType === s.value ? 'primary' : undefined"
                    class="pa-3 text-center h-100 position-relative" style="cursor: pointer;"
                    @click="serviceType = s.value"
                  >
                    <VIcon
                      v-if="serviceType === s.value" icon="ri-checkbox-circle-fill" color="primary" size="18"
                      style="position:absolute; top:6px; right:6px;"
                    />
                    <VIcon :icon="s.icon" size="28" class="mb-1" />
                    <div class="text-subtitle-2 font-weight-bold">{{ s.title }}</div>
                    <div class="text-caption text-medium-emphasis">{{ s.subtitle }}</div>
                  </VCard>
                </VCol>
              </VRow>

              <template v-if="serviceType">
                <VDivider class="mb-3" />
                <div class="text-subtitle-2 mb-2">Ingresa la ruta de tu {{ serviceType === 'mudanza' ? 'mudanza' : serviceType === 'reparto' ? 'reparto' : 'carga' }}</div>
                <template v-if="serviceType === 'reparto'">
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
                  <VRow dense>
                    <VCol cols="12" sm="6">
                      <DistrictAutocomplete v-model="quote.origin" label="Origen" />
                    </VCol>
                    <VCol cols="12" sm="6">
                      <DistrictAutocomplete v-model="quote.destination" label="Destino" />
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

                  <p class="text-caption text-medium-emphasis mb-0">
                    La dirección exacta te la pedimos recién al reservar — para cotizar alcanza con el distrito.
                  </p>
                </template>
              </template>
            </template>

            <template #item.2>
              <template v-if="serviceType === 'carga'">
                <div class="text-subtitle-2 mb-2">¿Qué vas a transportar?</div>
                <VSelect v-model="quote.cargo.category" :items="CATEGORIES" label="Tipo de carga" density="comfortable" class="mb-2" />
                <VTextarea v-model="quote.cargo.detail" label="Detalle (opcional)" rows="2" auto-grow density="comfortable" class="mb-2" />
                <VTextField v-model="quote.cargo.weightKg" label="Peso aprox. (kg, opcional)" type="number" density="comfortable" class="mb-4" />
              </template>
              <template v-else-if="serviceType === 'mudanza'">
                <div class="text-subtitle-2 mb-2">¿Qué vas a mudar?</div>
                <VTextarea
                  v-model="quote.cargo.detail" rows="2" auto-grow density="comfortable" class="mb-2"
                  label="Ambientes, pisos, ascensor, muebles grandes (opcional)"
                />
              </template>
              <template v-else>
                <div class="text-subtitle-2 mb-2">Contanos tu operación de reparto</div>
                <VTextarea
                  v-model="quote.cargo.detail" rows="2" auto-grow density="comfortable" class="mb-2"
                  label="Cuántos pedidos, frecuencia, si es ecommerce o contra-entrega (opcional)"
                />
              </template>

              <CargoPhotosPicker v-model="photos" class="mb-2" />

              <template v-if="serviceType === 'carga'">
                <VDivider class="my-3" />
                <div class="d-flex align-center ga-2 mb-2 flex-wrap">
                  <span class="text-body-2 text-medium-emphasis">¿Ya sabés qué vehículo necesitás?</span>
                  <VChip v-if="chosenTruck" closable size="small" color="primary" variant="tonal" @click:close="chosenTruck = null">
                    {{ chosenTruckLabel }}
                  </VChip>
                  <VBtn v-else size="small" variant="tonal" @click="showVehiclePicker = true">Elegir vehículo</VBtn>
                  <span class="text-caption text-medium-emphasis">(opcional — si no elegís, TaxiCarga te asigna la mejor opción)</span>
                </div>
                <VehiclePickerDialog
                  v-model="showVehiclePicker"
                  @select="v => chosenTruck = v" @clear="chosenTruck = null"
                />
              </template>
            </template>

            <template #item.3>
              <template v-if="serviceType === 'carga'">
                <div class="text-subtitle-2 mb-2">Elige cómo quieres cotizar tu carga</div>
                <template v-if="hasStops">
                  <VAlert type="info" variant="tonal">
                    Con paradas intermedias, un asesor te confirma el precio — no aplica Consolidada/Express.
                  </VAlert>
                </template>
                <PriceModePicker
                  v-else v-model="quote.loadMode" :loading="previewLoading"
                  :express="pricePreview?.express" :consolidated="pricePreview?.consolidated"
                />

                <VDivider class="my-4" />
                <ContinueModePicker
                  :mode="continueMode" :price="quote.proposedPrice" :negotiable="quote.priceNegotiable"
                  @update:mode="v => continueMode = v" @update:price="v => quote.proposedPrice = v"
                  @update:negotiable="v => quote.priceNegotiable = v"
                />
              </template>
              <template v-else>
                <ScheduleStepPicker
                  :date="quote.date" :schedule="quote.schedule"
                  @update:date="v => quote.date = v" @update:schedule="v => quote.schedule = v"
                />
                <VDivider class="my-4" />
                <div class="text-subtitle-2 mb-2">¿Cómo te contactamos?</div>
                <VTextField v-model="quote.contact.name" label="Tu nombre" density="comfortable" class="mb-2" />
                <VTextField v-model="quote.contact.phone" label="Teléfono / WhatsApp" density="comfortable" class="mb-2" />
                <VTextField v-model="quote.contact.email" label="Correo (opcional)" type="email" density="comfortable" />
                <VAlert v-if="error" type="error" variant="tonal" class="mt-3">{{ error }}</VAlert>
              </template>
            </template>

            <template #item.4>
              <ScheduleStepPicker
                :date="quote.date" :schedule="quote.schedule"
                @update:date="v => quote.date = v" @update:schedule="v => quote.schedule = v"
              />
              <VDivider class="my-4" />
              <div class="text-subtitle-2 mb-2">¿Cómo te contactamos?</div>
              <VTextField v-model="quote.contact.name" label="Tu nombre" density="comfortable" class="mb-2" />
              <VTextField v-model="quote.contact.phone" label="Teléfono / WhatsApp" density="comfortable" class="mb-2" />
              <VTextField v-model="quote.contact.email" label="Correo (opcional)" type="email" density="comfortable" />
              <VAlert v-if="error" type="error" variant="tonal" class="mt-3">{{ error }}</VAlert>
            </template>
          </VStepper>

          <input v-model="quote.website" type="text" tabindex="-1" autocomplete="off" style="position:absolute; left:-9999px;" aria-hidden="true">
        </VCardText>
        <VCardActions v-if="phase === 'form'" class="px-4 pb-4">
          <VBtn v-if="step > 1" variant="text" @click="step--">Atrás</VBtn>
          <VBtn v-else variant="text" to="/login">Ya tengo cuenta</VBtn>
          <VSpacer />
          <VBtn v-if="step === 1" color="primary" :disabled="!step1ok" @click="step = 2">Siguiente</VBtn>
          <VBtn v-else-if="step === 2" color="primary" @click="goToStep3">Siguiente</VBtn>
          <VBtn v-else-if="step < maxStep" color="primary" @click="step++">Siguiente</VBtn>
          <VBtn v-else color="primary" :loading="busy" :disabled="!formOk" @click="submitQuote">Cotizar</VBtn>
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
        />
      </VCol>
      </VRow>
    </div>
  </div>
</template>
