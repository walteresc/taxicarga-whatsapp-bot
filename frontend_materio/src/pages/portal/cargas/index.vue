<script setup>
import { onMounted, reactive, ref } from 'vue'

import { carrierLoads, carrierMe, carrierOffer } from '@/services/portalService'
import { carrierVehiclesService } from '@/services/carriersService'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()

const PRICE_MODE = {
  fixed: { label: 'Precio fijo', hint: 'Solo podés aceptarlo.' },
  reference: { label: 'Precio referencial', hint: 'Podés ofertar tu monto.' },
  open: { label: 'A proponer', hint: 'Indicá tu precio.' },
}
const OFFER_STATE = {
  pending: { label: 'Enviada', color: 'info' },
  countered_us: { label: 'Contraoferta de Lima Express', color: 'warning' },
  countered_you: { label: 'Contraofertaste', color: 'warning' },
  accepted: { label: 'Adjudicada a vos', color: 'success' },
  rejected: { label: 'No seleccionada', color: 'error' },
}
const soles = n => (n == null ? '—' : `S/ ${Math.round(n).toLocaleString('es-PE')}`)

const rows = ref([])
const vehicles = ref([])
const loading = ref(true)
const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snackbar, { show: true, text: t, color: c })

const load = async () => {
  loading.value = true
  try { rows.value = (await carrierLoads()).results }
  catch (e) { notify(e.message || 'No se pudo cargar.', 'error') }
  finally { loading.value = false }
}
onMounted(async () => {
  vehicles.value = (await carrierVehiclesService.list({ carrierId: auth.carrierId, status: 'active', pageSize: 50 })).results
  await load()
})

const lightbox = ref('')   // url de la foto ampliada, '' = cerrado

// Modalidad (Consolidada/Express) — solo tiene sentido en carga
// interprovincial. El transportista es quien sabe si dedica el camión o va
// con carga propia compartida, no el cliente ni el asesor.
const MODALIDAD_OPTIONS = [
  { title: 'Consolidada — comparto camión con otra carga mía', value: 'parcial' },
  { title: 'Express — camión dedicado solo a esta carga', value: 'completa' },
]

const form = reactive({ open: false, load: null, amount: '', vehicleId: null, note: '', modalidad: null })
const busy = ref(false)
const openOffer = l => {
  Object.assign(form, {
    open: true, load: l,
    amount: l.priceMode === 'fixed' ? String(l.targetPrice ?? '') : (l.myOfferAmount ? String(l.myOfferAmount) : ''),
    vehicleId: vehicles.value.length === 1 ? vehicles.value[0].id : null,
    note: '',
    modalidad: l.myOfferModality || null,
  })
}
const submit = async () => {
  busy.value = true
  try {
    await carrierOffer(form.load.code, {
      amount: form.amount || undefined,
      vehicleId: form.vehicleId || undefined,
      note: form.note || undefined,
      modalidad: form.load.isInterprovincial ? (form.modalidad || undefined) : undefined,
    })
    form.open = false
    notify('Oferta enviada.')
    await load()
  } catch (e) { notify(e.message || 'No se pudo enviar.', 'error') } finally { busy.value = false }
}
</script>

<template>
  <div>
    <h1 class="text-h5 font-weight-bold mb-1">Cargas disponibles</h1>
    <p class="text-body-2 text-medium-emphasis mb-4">
      Servicios que Lima Express está tercerizando. Ofertá y seguí la negociación desde acá.
    </p>

    <VProgressLinear v-if="loading" indeterminate />
    <div v-else-if="!rows.length" class="text-center text-medium-emphasis py-10">
      No hay cargas disponibles ahora mismo.
    </div>

    <VRow v-else>
      <VCol v-for="l in rows" :key="l.code" cols="12" md="6">
        <VCard>
          <VCardText>
            <div class="d-flex align-center ga-2 mb-2">
              <span class="text-subtitle-1 font-weight-bold">{{ l.code }}</span>
              <VChip size="x-small" variant="tonal">{{ PRICE_MODE[l.priceMode]?.label }}</VChip>
              <VChip v-if="l.myOfferState" size="x-small" :color="OFFER_STATE[l.myOfferState]?.color">
                {{ OFFER_STATE[l.myOfferState]?.label }}
              </VChip>
            </div>
            <div class="text-body-2 mb-2">
              <VIcon icon="ri-map-pin-line" size="14" /> {{ l.origin }} → {{ l.destination }}
              <span v-if="l.date"> · {{ new Date(l.date).toLocaleDateString('es-PE') }}</span>
            </div>
            <ul class="text-caption text-medium-emphasis mb-2" style="padding-left: 1rem;">
              <li v-for="(line, i) in l.lines" :key="i">{{ line }}</li>
            </ul>
            <div v-if="l.photos?.length" class="d-flex ga-2 mb-3">
              <VImg
                v-for="(url, i) in l.photos" :key="i" :src="url" width="56" height="56" cover
                class="rounded" style="cursor: pointer;" @click="lightbox = url"
              />
            </div>
            <div class="d-flex align-center justify-space-between">
              <span class="text-body-2">
                <span class="text-medium-emphasis">Precio guía:</span> <strong>{{ soles(l.targetPrice) }}</strong>
              </span>
              <VBtn size="small" color="primary" @click="openOffer(l)">
                {{ l.myOfferId ? 'Actualizar oferta' : (l.priceMode === 'fixed' ? 'Aceptar' : 'Ofertar') }}
              </VBtn>
            </div>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

    <VDialog v-model="form.open" max-width="440">
      <VCard v-if="form.load">
        <VCardTitle>{{ form.load.code }} · {{ form.load.priceMode === 'fixed' ? 'Aceptar precio' : 'Tu oferta' }}</VCardTitle>
        <VCardText>
          <p class="text-caption text-medium-emphasis mb-3">{{ PRICE_MODE[form.load.priceMode]?.hint }}</p>
          <VTextField
            v-model="form.amount" label="Monto (S/)" type="number" class="mb-2"
            :disabled="form.load.priceMode === 'fixed'"
          />
          <VSelect
            v-if="vehicles.length > 1" v-model="form.vehicleId" label="Vehículo" class="mb-2" clearable
            :items="vehicles.map(v => ({ title: v.plate, value: v.id }))"
          />
          <VSelect
            v-if="form.load.isInterprovincial" v-model="form.modalidad" label="¿Cómo la vas a llevar?"
            class="mb-2" :items="MODALIDAD_OPTIONS"
            hint="Vos sabés si dedicás el camión o vas con carga propia compartida — el cliente no elige esto."
            persistent-hint
          />
          <VTextarea v-model="form.note" label="Nota para Lima Express (opcional)" rows="2" auto-grow />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="form.open = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="busy" @click="submit">Enviar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog :model-value="!!lightbox" max-width="640" @update:model-value="lightbox = ''">
      <VImg :src="lightbox" style="cursor: pointer;" @click="lightbox = ''" />
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </div>
</template>
