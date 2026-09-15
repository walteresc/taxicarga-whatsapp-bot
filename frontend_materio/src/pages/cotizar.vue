<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import AddressAutocomplete from '@/components/AddressAutocomplete.vue'
import DistrictAutocomplete from '@/components/DistrictAutocomplete.vue'
import QuoteSummaryPanel from '@/components/QuoteSummaryPanel.vue'
import VehiclePickerDialog from '@/components/VehiclePickerDialog.vue'
import { guestQuote, guestSignup } from '@/services/guestService'
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
// "que TaxiCarga elija" (quoteMode 'por_carga', sin truckType).
const TRUCKS = [
  { title: 'Furgón pequeño (hasta 1 ton)', value: 'furgon_1t', icon: 'ri-taxi-line' },
  { title: 'Camión 2 ton', value: 'camion_2t' },
  { title: 'Camión 4 ton', value: 'camion_4t' },
  { title: 'Camión 8 ton', value: 'camion_8t' },
]
const showVehiclePicker = ref(false)
const chosenTruck = ref(null)
const chosenTruckLabel = computed(() => TRUCKS.find(t => t.value === chosenTruck.value)?.title || '')

const phase = ref('form')   // form | result | signup
const busy = ref(false)
const error = ref('')

const quote = reactive({
  origin: { district: '', address: '', province: '', region: '', lat: null, lng: null },
  destination: { district: '', address: '', province: '', region: '', lat: null, lng: null },
  cargo: { category: 'cajas', detail: '', weightKg: '' },
  loadMode: 'completa',   // completa|parcial — solo importa si la ruta es nacional
  date: '',
  contact: { name: '', phone: '', email: '' },
  website: '',   // honeypot
})
const result = ref(null)

// Paradas intermedias (multipunto) — solo Carga. El motor de precios no las
// contempla en el cálculo (ver apps/cotizador/services.py::cotizar_lead), así
// que una solicitud con paradas siempre pasa a modo asesor, a propósito.
const stops = reactive([])
const addStop = () => stops.push({ district: '', province: '', region: '', lat: null, lng: null })
const removeStop = index => stops.splice(index, 1)

const soles = n => (n == null ? null : `S/ ${Math.round(n).toLocaleString('es-PE')}`)
const formOk = computed(() =>
  serviceType.value && quote.origin.district && quote.destination.district && quote.contact.phone && quote.contact.name)

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
    result.value = await guestQuote({ ...quote, cargo, quoteMode, stops: validStops })
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
          <div class="text-subtitle-2 mb-2">¿Qué necesitas?</div>
          <VRow class="mb-2" dense>
            <VCol v-for="s in SERVICE_TYPES" :key="s.value" cols="12" sm="4">
              <VCard
                :variant="serviceType === s.value ? 'tonal' : 'outlined'"
                :color="serviceType === s.value ? 'primary' : undefined"
                class="pa-3 text-center h-100" style="cursor: pointer;"
                @click="serviceType = s.value"
              >
                <VIcon :icon="s.icon" size="28" class="mb-1" />
                <div class="text-subtitle-2 font-weight-bold">{{ s.title }}</div>
                <div class="text-caption text-medium-emphasis">{{ s.subtitle }}</div>
              </VCard>
            </VCol>
          </VRow>

          <template v-if="serviceType">
            <div class="text-subtitle-2 mb-2">¿De dónde a dónde?</div>
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

              <p class="text-caption text-medium-emphasis mb-2">
                La dirección exacta te la pedimos recién al reservar — para cotizar alcanza con el distrito.
              </p>
            </template>

            <template v-if="serviceType === 'carga'">
              <div class="text-subtitle-2 mb-2">¿Qué vas a mover?</div>
              <VSelect v-model="quote.cargo.category" :items="CATEGORIES" label="Tipo de carga" density="comfortable" class="mb-2" />
              <VTextarea v-model="quote.cargo.detail" label="Detalle (opcional)" rows="2" auto-grow density="comfortable" class="mb-2" />
              <VTextField v-model="quote.cargo.weightKg" label="Peso aprox. (kg, opcional)" type="number" density="comfortable" class="mb-4" />

              <div class="d-flex align-center ga-2 mb-2 flex-wrap">
                <span class="text-body-2 text-medium-emphasis">¿Ya sabés qué vehículo necesitás?</span>
                <VChip v-if="chosenTruck" closable size="small" color="primary" variant="tonal" @click:close="chosenTruck = null">
                  {{ chosenTruckLabel }}
                </VChip>
                <VBtn v-else size="small" variant="tonal" @click="showVehiclePicker = true">Elegir vehículo</VBtn>
                <span class="text-caption text-medium-emphasis">(opcional)</span>
              </div>
              <VehiclePickerDialog
                v-model="showVehiclePicker" :trucks="TRUCKS"
                @select="v => chosenTruck = v" @clear="chosenTruck = null"
              />
            </template>
            <template v-else-if="serviceType === 'mudanza'">
              <div class="text-subtitle-2 mb-2">Contanos de tu mudanza</div>
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

            <VTextField v-model="quote.date" label="Fecha (opcional)" type="date" density="comfortable" class="mb-2" />

            <template v-if="quote.origin.district && quote.destination.district">
              <div class="text-caption text-medium-emphasis mb-1">
                Si tu carga es a otra ciudad, elegí cómo la enviamos (si es dentro de Lima, no aplica):
              </div>
              <VBtnToggle v-model="quote.loadMode" mandatory density="comfortable" class="mb-4" divided>
                <VBtn value="completa" size="small">Completa (camión dedicado, más rápido)</VBtn>
                <VBtn value="parcial" size="small">Parcial (comparte camión, más económico)</VBtn>
              </VBtnToggle>
            </template>

            <div class="text-subtitle-2 mb-2">¿Cómo te contactamos?</div>
            <VTextField v-model="quote.contact.name" label="Tu nombre" density="comfortable" class="mb-2" />
            <VTextField v-model="quote.contact.phone" label="Teléfono / WhatsApp" density="comfortable" class="mb-2" />
            <VTextField v-model="quote.contact.email" label="Correo (opcional)" type="email" density="comfortable" />
          </template>

          <input v-model="quote.website" type="text" tabindex="-1" autocomplete="off" style="position:absolute; left:-9999px;" aria-hidden="true">

          <VAlert v-if="error" type="error" variant="tonal" class="mt-3">{{ error }}</VAlert>
        </VCardText>
        <VCardActions v-if="phase === 'form'" class="px-4 pb-4">
          <VBtn variant="text" to="/login">Ya tengo cuenta</VBtn>
          <VSpacer />
          <VBtn color="primary" :loading="busy" :disabled="!formOk" @click="submitQuote">Cotizar</VBtn>
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
