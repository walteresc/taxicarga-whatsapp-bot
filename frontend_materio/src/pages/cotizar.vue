<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { guestQuote, guestSignup } from '@/services/guestService'
import { useAuthStore } from '@/stores/authStore'

const router = useRouter()
const auth = useAuthStore()

const CATEGORIES = [
  { title: 'Mudanza, muebles y electrodomésticos', value: 'mudanza' },
  { title: 'Cajas, paquetes y bultos', value: 'cajas' },
  { title: 'Mercadería comercial', value: 'mercaderia' },
  { title: 'Maquinaria y equipos', value: 'maquinaria' },
  { title: 'Materiales de construcción', value: 'construccion' },
  { title: 'Otros', value: 'otros' },
]

const phase = ref('form')   // form | result | signup
const busy = ref(false)
const error = ref('')

const quote = reactive({
  origin: { district: '', address: '' },
  destination: { district: '', address: '' },
  cargo: { category: 'mudanza', detail: '' },
  date: '',
  contact: { name: '', phone: '', email: '' },
  website: '',   // honeypot
})
const result = ref(null)

const soles = n => (n == null ? null : `S/ ${Math.round(n).toLocaleString('es-PE')}`)
const formOk = computed(() =>
  quote.origin.district && quote.destination.district && quote.contact.phone && quote.contact.name)

const submitQuote = async () => {
  busy.value = true
  error.value = ''
  try {
    result.value = await guestQuote({ ...quote, quoteMode: 'por_carga' })
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
    <div style="width: 100%; max-width: 560px;">
      <div class="text-center my-6">
        <div class="text-h5 font-weight-bold">Lima Express</div>
        <div class="text-body-2 text-medium-emphasis">Cotización rápida de carga</div>
      </div>

      <VCard>
        <!-- Paso 1: formulario -->
        <VCardText v-if="phase === 'form'">
          <div class="text-subtitle-2 mb-2">¿De dónde a dónde?</div>
          <div class="d-flex ga-2 mb-2">
            <VTextField v-model="quote.origin.district" label="Distrito origen" density="comfortable" />
            <VTextField v-model="quote.destination.district" label="Distrito destino" density="comfortable" />
          </div>
          <VTextField v-model="quote.origin.address" label="Dirección de origen (opcional)" density="comfortable" class="mb-2" />
          <VTextField v-model="quote.destination.address" label="Dirección de destino (opcional)" density="comfortable" class="mb-4" />

          <div class="text-subtitle-2 mb-2">¿Qué vas a mover?</div>
          <VSelect v-model="quote.cargo.category" :items="CATEGORIES" label="Tipo de carga" density="comfortable" class="mb-2" />
          <VTextarea v-model="quote.cargo.detail" label="Detalle (opcional)" rows="2" auto-grow density="comfortable" class="mb-2" />
          <VTextField v-model="quote.date" label="Fecha (opcional)" type="date" density="comfortable" class="mb-4" />

          <div class="text-subtitle-2 mb-2">¿Cómo te contactamos?</div>
          <VTextField v-model="quote.contact.name" label="Tu nombre" density="comfortable" class="mb-2" />
          <VTextField v-model="quote.contact.phone" label="Teléfono / WhatsApp" density="comfortable" class="mb-2" />
          <VTextField v-model="quote.contact.email" label="Correo (opcional)" type="email" density="comfortable" />

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
          <div class="text-body-2 text-medium-emphasis">{{ result.route }}</div>
          <template v-if="result.price.amount != null">
            <div class="text-h3 font-weight-bold my-3">{{ soles(result.price.amount) }}</div>
            <div v-if="result.price.range" class="text-caption text-medium-emphasis">
              Rango estimado {{ soles(result.price.range[0]) }} – {{ soles(result.price.range[1]) }}
            </div>
          </template>
          <template v-else>
            <div class="text-h6 my-3">Un asesor te confirmará el precio</div>
            <div class="text-body-2 text-medium-emphasis">Tu carga tiene detalles que preferimos revisar con vos.</div>
          </template>
          <VDivider class="my-4" />
          <p class="text-body-2 mb-3">
            Creá tu cuenta para publicar la carga, negociar el precio y seguir el servicio.
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
    </div>
  </div>
</template>
