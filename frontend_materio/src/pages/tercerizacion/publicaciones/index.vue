<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { carriersService, carrierVehiclesService } from '@/services/carriersService'
import {
  outsourcingSettings, outsourcingSettingsUpdate,
  publicationAddOffer, publicationAward, publicationDetail, publicationList, publicationPublish,
} from '@/services/publicationService'
import { useAuthStore } from '@/stores/authStore'

const router = useRouter()
const auth = useAuthStore()
const canManageSettings = computed(() => auth.hasAnyRole('Administrador', 'Gerencia', 'Supervisor', 'Despacho'))

const STATE = {
  draft: { label: 'Borrador', color: 'default' },
  open: { label: 'Abierta', color: 'info' },
  with_offers: { label: 'Con ofertas', color: 'primary' },
  awarded: { label: 'Adjudicada', color: 'success' },
  cancelled: { label: 'Cancelada', color: 'error' },
  expired: { label: 'Vencida', color: 'warning' },
}
const PRICE_MODE = {
  fixed: 'Precio fijo (solo aceptan)',
  reference: 'Referencial (pueden ofertar)',
  open: 'Abierto (proponen)',
}
const OFFER_STATE = {
  pending: { label: 'Pendiente', color: 'info' },
  countered_us: { label: 'Contraoferta nuestra', color: 'warning' },
  countered_carrier: { label: 'Contraoferta transportista', color: 'warning' },
  accepted: { label: 'Adjudicada', color: 'success' },
  rejected: { label: 'Rechazada', color: 'error' },
  withdrawn: { label: 'Retirada', color: 'default' },
  expired: { label: 'Vencida', color: 'default' },
}

const soles = n => (n == null ? '—' : `S/ ${Math.round(n).toLocaleString('es-PE')}`)

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snackbar, { show: true, text: t, color: c })

const rows = ref([])
const loadingList = ref(true)
const stateFilter = ref('')
const search = ref('')
let searchTimer

const loadList = async () => {
  loadingList.value = true
  try {
    rows.value = (await publicationList({
      state: stateFilter.value || undefined,
      search: search.value || undefined,
    })).results
  } catch (e) { notify(e.message || 'No se pudo cargar.', 'error') } finally { loadingList.value = false }
}
const onSearch = () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadList, 350) }

const autoDerive = ref(false)
const autoDeriveBusy = ref(false)
const loadAutoDerive = async () => {
  try { autoDerive.value = (await outsourcingSettings()).autoDeriveInterprovincial } catch { /* sin permiso: se oculta */ }
}
const toggleAutoDerive = async val => {
  autoDeriveBusy.value = true
  try {
    autoDerive.value = (await outsourcingSettingsUpdate({ autoDeriveInterprovincial: val })).autoDeriveInterprovincial
    notify(autoDerive.value
      ? 'Las cargas interprovinciales completas se publicarán solas a los transportistas.'
      : 'Derivación automática desactivada. El asesor cotiza o deriva a mano.')
  } catch (e) {
    autoDerive.value = !val
    notify(e.message || 'No se pudo cambiar.', 'error')
  } finally { autoDeriveBusy.value = false }
}

onMounted(() => { loadList(); if (canManageSettings.value) loadAutoDerive() })

const detail = ref(null)
const selectedId = ref(null)
const busy = ref(false)

const open = async id => {
  selectedId.value = id
  detail.value = null
  try { detail.value = await publicationDetail(id) } catch (e) { notify(e.message, 'error') }
}

const doPublish = async () => {
  busy.value = true
  try {
    const groups = (groupsInput.value || '').split(',').map(s => s.trim()).filter(Boolean)
    detail.value = await publicationPublish(selectedId.value, groups)
    notify('Publicación abierta. Ya podés registrar ofertas.')
    await loadList()
  } catch (e) { notify(e.message || 'No se pudo publicar.', 'error') } finally { busy.value = false }
}
const groupsInput = ref('')

// --- registrar oferta ---
const offerForm = reactive({ open: false, carrier: null, vehicleId: null, amount: '', note: '' })
const carrierOptions = ref([])
const carrierVehicles = ref([])
const searchCarriers = async q => {
  carrierOptions.value = (await carriersService.list({ search: q || undefined, status: 'active', pageSize: 20 })).results
}
const onCarrierPick = async () => {
  offerForm.vehicleId = null
  carrierVehicles.value = []
  if (!offerForm.carrier) return
  carrierVehicles.value = (await carrierVehiclesService.list({ carrierId: offerForm.carrier.id, status: 'active', pageSize: 50 })).results
  if (carrierVehicles.value.length === 1) offerForm.vehicleId = carrierVehicles.value[0].id
}
const openOfferForm = () => {
  Object.assign(offerForm, { open: true, carrier: null, vehicleId: null, amount: '', note: '' })
  carrierVehicles.value = []
  searchCarriers('')
}
const submitOffer = async () => {
  busy.value = true
  try {
    detail.value = await publicationAddOffer(selectedId.value, {
      carrierId: offerForm.carrier.id,
      vehicleId: offerForm.vehicleId || undefined,
      amount: offerForm.amount,
      note: offerForm.note || undefined,
    })
    offerForm.open = false
    notify('Oferta registrada.')
    await loadList()
  } catch (e) { notify(e.message || 'No se pudo registrar la oferta.', 'error') } finally { busy.value = false }
}

// --- adjudicar ---
const awardForm = reactive({ open: false, offer: null, vehicleId: null })
const awardVehicles = ref([])
const openAward = async offer => {
  Object.assign(awardForm, { open: true, offer, vehicleId: offer.vehicleId })
  awardVehicles.value = []
  if (offer.carrierId) {
    awardVehicles.value = (await carrierVehiclesService.list({ carrierId: offer.carrierId, status: 'active', pageSize: 50 })).results
    if (!awardForm.vehicleId && awardVehicles.value.length === 1) awardForm.vehicleId = awardVehicles.value[0].id
  }
}
const submitAward = async () => {
  busy.value = true
  try {
    const res = await publicationAward(selectedId.value, {
      offerId: awardForm.offer.id,
      vehicleId: awardForm.vehicleId || undefined,
    })
    detail.value = res.publication
    awardForm.open = false
    notify('Adjudicada. Programación tercerizada creada.')
    await loadList()
  } catch (e) { notify(e.message || 'No se pudo adjudicar.', 'error') } finally { busy.value = false }
}

const canPublish = computed(() => detail.value?.state === 'draft')
const canOffer = computed(() => ['open', 'with_offers'].includes(detail.value?.state))
const awarded = computed(() => detail.value?.state === 'awarded')
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">Publicaciones</h1>
    <p class="text-body-2 text-medium-emphasis mb-4">
      Cargas derivadas a tercerización. El Despacho las publica a los transportistas, registra las ofertas
      y adjudica — al adjudicar se crea la programación con el transportista.
    </p>

    <VCard v-if="canManageSettings" variant="tonal" class="mb-4">
      <VCardText class="d-flex align-center flex-wrap ga-2 py-2">
        <VSwitch
          v-model="autoDerive" :loading="autoDeriveBusy" color="primary" density="compact" hide-details
          label="Derivar interprovinciales automáticamente"
          @update:model-value="toggleAutoDerive"
        />
        <span class="text-caption text-medium-emphasis">
          Con esto activo, una carga interprovincial con datos completos se publica sola a los transportistas
          (precio abierto: ellos proponen), sin que el asesor la cotice. Si está apagado, el asesor la cotiza
          o la deriva a mano.
        </span>
      </VCardText>
    </VCard>

    <VRow>
      <VCol cols="12" md="5">
        <VCard>
          <VCardText class="d-flex flex-column ga-2">
            <VTextField
              v-model="search" prepend-inner-icon="ri-search-line" placeholder="Buscar código, ruta"
              density="compact" hide-details clearable @update:model-value="onSearch"
            />
            <VSelect
              v-model="stateFilter" label="Estado" density="compact" hide-details clearable
              :items="Object.entries(STATE).map(([value, s]) => ({ title: s.label, value }))"
              @update:model-value="loadList"
            />
          </VCardText>
          <VDivider />
          <div style="max-height: 70vh; overflow-y: auto;">
            <VProgressLinear v-if="loadingList" indeterminate />
            <div v-else-if="!rows.length" class="text-center text-medium-emphasis py-8 text-body-2">Sin publicaciones.</div>
            <VList v-else density="compact" lines="two">
              <VListItem v-for="row in rows" :key="row.id" :active="row.id === selectedId" @click="open(row.id)">
                <VListItemTitle class="d-flex align-center ga-2">
                  <span class="font-weight-medium">{{ row.code }}</span>
                  <span class="text-caption text-medium-emphasis">{{ row.bookingCode }}</span>
                  <VChip size="x-small" :color="STATE[row.state]?.color">{{ STATE[row.state]?.label }}</VChip>
                </VListItemTitle>
                <VListItemSubtitle>
                  {{ row.route }}
                  <span v-if="row.date"> · {{ new Date(row.date).toLocaleDateString('es-PE') }}</span>
                  · {{ row.offerCount }} oferta(s)
                </VListItemSubtitle>
              </VListItem>
            </VList>
          </div>
        </VCard>
      </VCol>

      <VCol cols="12" md="7">
        <VCard v-if="!detail" class="d-flex align-center justify-center" style="min-height: 50vh;">
          <span class="text-medium-emphasis">Elegí una publicación.</span>
        </VCard>

        <VCard v-else>
          <VCardText class="d-flex flex-wrap align-center ga-2">
            <span class="text-h6">{{ detail.code }}</span>
            <VChip size="small" :color="STATE[detail.state]?.color">{{ STATE[detail.state]?.label }}</VChip>
            <VChip size="small" variant="tonal">{{ PRICE_MODE[detail.priceMode] }}</VChip>
            <VSpacer />
            <VBtn size="small" variant="text" prepend-icon="ri-file-text-line" @click="router.push(`/comercial/cotizaciones`)">Ver cotización</VBtn>
          </VCardText>

          <VCardText class="pt-0">
            <VTable density="compact" class="text-body-2">
              <tbody>
                <tr><td>Reserva</td><td>{{ detail.service.code }}</td></tr>
                <tr><td>Ruta</td><td>{{ detail.service.origin }} → {{ detail.service.destination }}</td></tr>
                <tr><td>Fecha</td><td>{{ detail.service.date ? new Date(detail.service.date).toLocaleDateString('es-PE') : '—' }} {{ detail.service.schedule }}</td></tr>
                <tr v-if="detail.service.cargo"><td>Carga</td><td>{{ detail.service.cargo }}</td></tr>
                <tr><td>Precio de venta</td><td>{{ soles(detail.service.salePrice) }}</td></tr>
                <tr><td>Costo objetivo (publicado)</td><td>{{ soles(detail.publishedPrice) }}</td></tr>
              </tbody>
            </VTable>
          </VCardText>

          <template v-if="canPublish">
            <VDivider />
            <VCardText>
              <VTextField v-model="groupsInput" label="Grupos donde se pegó (opcional, separá con comas)" density="compact" class="mb-2" />
              <VBtn color="primary" :loading="busy" prepend-icon="ri-megaphone-line" @click="doPublish">Publicar a transportistas</VBtn>
            </VCardText>
          </template>

          <VDivider />
          <VCardText>
            <div class="d-flex align-center mb-2">
              <span class="text-overline">Ofertas</span>
              <VSpacer />
              <VBtn v-if="canOffer" size="small" variant="tonal" prepend-icon="ri-add-line" @click="openOfferForm">Registrar oferta</VBtn>
            </div>
            <div v-if="!detail.offers.length" class="text-body-2 text-medium-emphasis">Sin ofertas todavía.</div>
            <VTable v-else density="compact" class="text-body-2">
              <thead><tr><th>Transportista</th><th>Vehículo</th><th class="text-right">Monto</th><th>Estado</th><th></th></tr></thead>
              <tbody>
                <tr v-for="o in detail.offers" :key="o.id" :class="o.id === detail.winningOfferId ? 'bg-success-lighten-5' : ''">
                  <td>
                    {{ o.carrierName }}
                    <VIcon v-if="!o.affiliated" icon="ri-error-warning-line" color="warning" size="14" title="Contacto de WhatsApp sin afiliar" />
                  </td>
                  <td>{{ o.vehiclePlate || '—' }}</td>
                  <td class="text-right font-weight-medium">{{ soles(o.currentAmount) }}</td>
                  <td><VChip size="x-small" :color="OFFER_STATE[o.state]?.color">{{ OFFER_STATE[o.state]?.label }}</VChip></td>
                  <td class="text-right">
                    <VBtn v-if="!awarded && o.state !== 'rejected'" size="x-small" color="success" :loading="busy" @click="openAward(o)">Adjudicar</VBtn>
                  </td>
                </tr>
              </tbody>
            </VTable>
          </VCardText>

          <VExpansionPanels v-if="detail.publishedText" class="px-4 pb-4">
            <VExpansionPanel title="Texto publicado">
              <template #text><pre class="text-caption" style="white-space: pre-wrap;">{{ detail.publishedText }}</pre></template>
            </VExpansionPanel>
          </VExpansionPanels>
        </VCard>
      </VCol>
    </VRow>

    <!-- Registrar oferta -->
    <VDialog v-model="offerForm.open" max-width="460">
      <VCard>
        <VCardTitle>Registrar oferta</VCardTitle>
        <VCardText>
          <VAutocomplete
            v-model="offerForm.carrier" label="Transportista afiliado" class="mb-2"
            :items="carrierOptions" item-title="name" return-object
            @update:search="searchCarriers" @update:model-value="onCarrierPick"
          />
          <VSelect
            v-if="carrierVehicles.length" v-model="offerForm.vehicleId" label="Vehículo" class="mb-2"
            :items="carrierVehicles.map(v => ({ title: `${v.plate}${v.categoryName ? ' · ' + v.categoryName : ''}`, value: v.id }))"
            clearable
          />
          <VTextField v-model="offerForm.amount" label="Monto ofertado (S/)" type="number" class="mb-2" />
          <VTextarea v-model="offerForm.note" label="Nota (opcional)" rows="2" auto-grow />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="offerForm.open = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="busy" :disabled="!offerForm.carrier || !offerForm.amount" @click="submitOffer">Guardar oferta</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Adjudicar -->
    <VDialog v-model="awardForm.open" max-width="440">
      <VCard>
        <VCardTitle>Adjudicar</VCardTitle>
        <VCardText>
          <p class="text-body-2 text-medium-emphasis mb-3">
            Se crea la programación con <strong>{{ awardForm.offer?.carrierName }}</strong> por
            <strong>{{ soles(awardForm.offer?.currentAmount) }}</strong> y el servicio queda tercerizado.
          </p>
          <VSelect
            v-if="awardVehicles.length" v-model="awardForm.vehicleId" label="Vehículo"
            :items="awardVehicles.map(v => ({ title: v.plate, value: v.id }))"
          />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="awardForm.open = false">Cancelar</VBtn>
          <VBtn color="success" :loading="busy" @click="submitAward">Adjudicar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
