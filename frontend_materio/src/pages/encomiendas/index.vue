<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { carriersService } from '@/services/carriersService'
import {
  shipmentAssign, shipmentCancel, shipmentCreate, shipmentDetail, shipmentEvent,
  shipmentList, shipmentQuote, shipmentZones,
} from '@/services/shipmentsService'

const STATE = {
  registrado: { label: 'Registrado', color: 'default' },
  asignado: { label: 'Asignado', color: 'info' },
  recogido: { label: 'Recogido', color: 'info' },
  en_ruta: { label: 'En ruta', color: 'warning' },
  entregado: { label: 'Entregado', color: 'success' },
  fallido: { label: 'No entregado', color: 'error' },
  devuelto: { label: 'Devuelto', color: 'default' },
  cancelado: { label: 'Cancelado', color: 'default' },
}
const NEXT = {
  asignado: ['recogido'], recogido: ['en_ruta', 'entregado', 'fallido'],
  en_ruta: ['entregado', 'fallido'], fallido: ['en_ruta', 'devuelto'],
}
const soles = n => (n == null ? '—' : `S/ ${Number(n).toLocaleString('es-PE', { minimumFractionDigits: 2 })}`)
const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snackbar, { show: true, text: t, color: c })

const rows = ref([])
const loading = ref(true)
const busy = ref(false)
const filters = reactive({ state: '', search: '' })
const zones = ref([])
const levels = ref([])
let searchTimer

const load = async () => {
  loading.value = true
  try {
    rows.value = (await shipmentList({ state: filters.state || undefined, search: filters.search || undefined })).results
  } catch (e) { notify(e.message || 'No se pudo cargar.', 'error') } finally { loading.value = false }
}
const onSearch = () => { clearTimeout(searchTimer); searchTimer = setTimeout(load, 350) }
onMounted(async () => {
  load()
  try { const z = await shipmentZones(); zones.value = z.zones; levels.value = z.levels } catch { /* noop */ }
})

// --- alta ---
const blank = () => ({
  senderName: '', senderPhone: '', originDistrict: '', originAddress: '', originReference: '',
  recipientName: '', recipientPhone: '', destDistrict: '', destAddress: '', destReference: '',
  content: '', weightKg: 1, level: 'express', cod: false, codAmount: '',
})
const form = reactive({ open: false, ...blank(), quote: null })
const openNew = () => { Object.assign(form, blank(), { open: true, quote: null }) }
const doQuote = async () => {
  if (!form.originDistrict || !form.destDistrict) return
  try {
    form.quote = await shipmentQuote({
      originDistrict: form.originDistrict, destDistrict: form.destDistrict,
      level: form.level, weightKg: form.weightKg,
    })
  } catch (e) { form.quote = null; notify(e.message || 'Sin tarifa para esa ruta.', 'error') }
}
const submitNew = async () => {
  busy.value = true
  try {
    const { open, quote, ...body } = form
    await shipmentCreate(body)
    form.open = false
    notify('Envío registrado.')
    await load()
  } catch (e) { notify(e.message || 'Revisá los datos.', 'error') } finally { busy.value = false }
}

// --- detalle ---
const detail = ref(null)
const openDetail = async code => { detail.value = null; try { detail.value = await shipmentDetail(code) } catch (e) { notify(e.message, 'error') } }

const carrierOpts = ref([])
const assignForm = reactive({ carrier: null })
const searchCarriers = async q => {
  carrierOpts.value = (await carriersService.list({ search: q || undefined, status: 'active', pageSize: 20 })).results
}
const doAssign = async () => {
  busy.value = true
  try {
    detail.value = await shipmentAssign(detail.value.code, { carrierId: assignForm.carrier.id })
    notify('Asignado.'); await load()
  } catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}
const doEvent = async (state, extra = {}) => {
  busy.value = true
  try {
    detail.value = await shipmentEvent(detail.value.code, { state, ...extra })
    notify('Estado actualizado.'); await load()
  } catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}
const markDelivered = async () => {
  const receivedBy = prompt('¿Quién recibió?')
  if (receivedBy == null) return
  await doEvent('entregado', { receivedBy })
}
const markFailed = async () => {
  const failReason = prompt('Motivo de la no entrega:')
  if (failReason == null) return
  await doEvent('fallido', { failReason })
}
const doCancel = async () => {
  const reason = prompt('Motivo de cancelación:')
  if (reason == null) return
  busy.value = true
  try { detail.value = await shipmentCancel(detail.value.code, reason); notify('Cancelado.'); await load() }
  catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}
const trackUrl = computed(() => (detail.value ? `${window.location.origin}/seguimiento/${detail.value.token}` : ''))
const copyTrack = () => { try { navigator.clipboard?.writeText(trackUrl.value); notify('Link copiado.') } catch { /* noop */ } }
</script>

<template>
  <section>
    <div class="d-flex align-center flex-wrap ga-2 mb-1">
      <h1 class="text-h4 font-weight-bold">Encomiendas</h1>
      <VSpacer />
      <VBtn color="primary" prepend-icon="ri-add-line" @click="openNew">Nuevo envío</VBtn>
    </div>
    <p class="text-body-2 text-medium-emphasis mb-4">
      Envíos door-to-door. Cotización por zona, asignación a un motorizado, seguimiento hasta la entrega.
    </p>

    <VRow>
      <VCol cols="12" md="7">
        <VCard>
          <VCardText class="d-flex flex-wrap ga-2">
            <VTextField
              v-model="filters.search" placeholder="Buscar código, destinatario, dirección"
              density="compact" hide-details clearable style="max-width: 300px;" prepend-inner-icon="ri-search-line"
              @update:model-value="onSearch"
            />
            <VSelect
              v-model="filters.state" label="Estado" density="compact" hide-details clearable style="max-width: 180px;"
              :items="Object.entries(STATE).map(([value, s]) => ({ title: s.label, value }))" @update:model-value="load"
            />
          </VCardText>
          <VDivider />
          <VProgressLinear v-if="loading" indeterminate />
          <div v-else-if="!rows.length" class="text-center text-medium-emphasis py-10 text-body-2">Sin envíos.</div>
          <VList v-else density="compact" lines="two">
            <VListItem v-for="r in rows" :key="r.code" :active="detail?.code === r.code" @click="openDetail(r.code)">
              <VListItemTitle class="d-flex align-center ga-2">
                <span class="font-weight-medium">{{ r.code }}</span>
                <VChip size="x-small" :color="STATE[r.state]?.color">{{ r.stateLabel }}</VChip>
                <VChip size="x-small" variant="tonal">{{ r.level }}</VChip>
                <span v-if="r.cod" class="text-caption text-warning">COD {{ soles(r.codAmount) }}</span>
              </VListItemTitle>
              <VListItemSubtitle>{{ r.route }} · {{ r.recipient }} · {{ soles(r.price) }}</VListItemSubtitle>
            </VListItem>
          </VList>
        </VCard>
      </VCol>

      <VCol cols="12" md="5">
        <VCard v-if="!detail" class="d-flex align-center justify-center" style="min-height: 40vh;">
          <span class="text-medium-emphasis">Elegí un envío.</span>
        </VCard>
        <VCard v-else>
          <VCardText class="d-flex flex-wrap align-center ga-2">
            <span class="text-h6">{{ detail.code }}</span>
            <VChip size="small" :color="STATE[detail.state]?.color">{{ detail.stateLabel }}</VChip>
            <VSpacer />
            <VBtn size="x-small" variant="text" icon="ri-file-copy-line" title="Copiar link de seguimiento" @click="copyTrack" />
          </VCardText>
          <VCardText class="pt-0">
            <VTable density="compact" class="text-body-2">
              <tbody>
                <tr><td>Recojo</td><td>{{ detail.sender.district }} · {{ detail.sender.address }}<br><span class="text-caption">{{ detail.sender.name }} {{ detail.sender.phone }}</span></td></tr>
                <tr><td>Entrega</td><td>{{ detail.recipientFull.district }} · {{ detail.recipientFull.address }}<br><span class="text-caption">{{ detail.recipientFull.name }} {{ detail.recipientFull.phone }}</span></td></tr>
                <tr><td>Paquete</td><td>{{ detail.package.content || '—' }} · {{ detail.package.weightKg }} kg</td></tr>
                <tr><td>Precio</td><td>{{ soles(detail.price) }}</td></tr>
                <tr v-if="detail.cod">
                  <td>Contra-entrega</td>
                  <td>
                    <span class="text-warning">{{ soles(detail.codAmount) }}</span>
                    <template v-if="detail.codCollected != null">
                      · cobrado {{ soles(detail.codCollected) }} ({{ detail.codMethod }})
                      · a remitir <strong>{{ soles(detail.codToRemit) }}</strong>
                      <VChip v-if="detail.codRemitted" size="x-small" color="success" class="ms-1">remitido</VChip>
                      <VChip v-else-if="detail.codHandedOver" size="x-small" color="info" class="ms-1">rendido</VChip>
                    </template>
                  </td>
                </tr>
                <tr><td>Motorizado</td><td>{{ detail.carrierName || '— sin asignar' }}<span v-if="detail.routeCode" class="text-caption text-medium-emphasis"> · {{ detail.routeCode }}</span></td></tr>
                <tr v-if="detail.receivedBy"><td>Recibió</td><td>{{ detail.receivedBy }}</td></tr>
                <tr v-if="detail.podPhoto"><td>Prueba de entrega</td><td><a :href="detail.podPhoto" target="_blank">ver foto</a></td></tr>
                <tr v-if="detail.failReason"><td>No entregado</td><td class="text-error">{{ detail.failReason }} <span v-if="detail.attempts">({{ detail.attempts }} intento/s)</span></td></tr>
              </tbody>
            </VTable>
          </VCardText>

          <VDivider />
          <VCardText v-if="['registrado', 'asignado'].includes(detail.state)">
            <VAutocomplete
              v-model="assignForm.carrier" label="Asignar a motorizado" density="compact" class="mb-2"
              :items="carrierOpts" item-title="name" return-object @update:search="searchCarriers"
            />
            <VBtn size="small" color="primary" :disabled="!assignForm.carrier" :loading="busy" @click="doAssign">
              {{ detail.carrierName ? 'Reasignar' : 'Asignar' }}
            </VBtn>
          </VCardText>

          <VCardText v-if="NEXT[detail.state]" class="d-flex flex-wrap ga-2">
            <template v-for="s in NEXT[detail.state]" :key="s">
              <VBtn v-if="s === 'entregado'" size="small" color="success" :loading="busy" @click="markDelivered">Entregado</VBtn>
              <VBtn v-else-if="s === 'fallido'" size="small" color="error" variant="tonal" :loading="busy" @click="markFailed">No entregado</VBtn>
              <VBtn v-else size="small" variant="tonal" :loading="busy" @click="doEvent(s)">{{ STATE[s]?.label }}</VBtn>
            </template>
          </VCardText>

          <VCardText>
            <div class="text-overline mb-1">Seguimiento</div>
            <VTimeline density="compact" side="end" truncate-line="both" class="ms-n2">
              <VTimelineItem v-for="(ev, i) in detail.events" :key="i" size="x-small" :dot-color="STATE[ev.state]?.color">
                <div class="text-body-2 font-weight-medium">{{ ev.label }}</div>
                <div class="text-caption text-medium-emphasis">{{ ev.detail }} · {{ new Date(ev.at).toLocaleString('es-PE') }}</div>
              </VTimelineItem>
            </VTimeline>
          </VCardText>

          <VCardActions v-if="['registrado', 'asignado'].includes(detail.state)" class="px-4 pb-3">
            <VBtn size="small" variant="text" color="error" @click="doCancel">Cancelar envío</VBtn>
          </VCardActions>
        </VCard>
      </VCol>
    </VRow>

    <VDialog v-model="form.open" max-width="640" scrollable>
      <VCard>
        <VCardTitle>Nuevo envío</VCardTitle>
        <VCardText>
          <div class="text-overline mb-1">Remitente / recojo</div>
          <VRow dense>
            <VCol cols="12" sm="6"><VTextField v-model="form.senderName" label="Nombre *" density="compact" /></VCol>
            <VCol cols="12" sm="6"><VTextField v-model="form.senderPhone" label="Teléfono" density="compact" /></VCol>
            <VCol cols="12" sm="5"><VCombobox v-model="form.originDistrict" label="Distrito *" density="compact"
              :items="zones.flatMap(z => z.districts)" @update:model-value="doQuote" /></VCol>
            <VCol cols="12" sm="7"><VTextField v-model="form.originAddress" label="Dirección *" density="compact" /></VCol>
            <VCol cols="12"><VTextField v-model="form.originReference" label="Referencia" density="compact" /></VCol>
          </VRow>
          <div class="text-overline mb-1 mt-2">Destinatario / entrega</div>
          <VRow dense>
            <VCol cols="12" sm="6"><VTextField v-model="form.recipientName" label="Nombre *" density="compact" /></VCol>
            <VCol cols="12" sm="6"><VTextField v-model="form.recipientPhone" label="Teléfono" density="compact" /></VCol>
            <VCol cols="12" sm="5"><VCombobox v-model="form.destDistrict" label="Distrito *" density="compact"
              :items="zones.flatMap(z => z.districts)" @update:model-value="doQuote" /></VCol>
            <VCol cols="12" sm="7"><VTextField v-model="form.destAddress" label="Dirección *" density="compact" /></VCol>
            <VCol cols="12"><VTextField v-model="form.destReference" label="Referencia" density="compact" /></VCol>
          </VRow>
          <div class="text-overline mb-1 mt-2">Paquete</div>
          <VRow dense>
            <VCol cols="12" sm="6"><VTextField v-model="form.content" label="Contenido" density="compact" /></VCol>
            <VCol cols="6" sm="3"><VTextField v-model.number="form.weightKg" label="Peso (kg)" type="number" density="compact" @update:model-value="doQuote" /></VCol>
            <VCol cols="6" sm="3"><VSelect v-model="form.level" label="Servicio" density="compact"
              :items="levels.map(l => ({ title: l.label, value: l.value }))" @update:model-value="doQuote" /></VCol>
            <VCol cols="6"><VCheckbox v-model="form.cod" label="Contra-entrega" density="compact" hide-details /></VCol>
            <VCol v-if="form.cod" cols="6"><VTextField v-model="form.codAmount" label="Monto a cobrar (S/)" type="number" density="compact" /></VCol>
          </VRow>
          <VAlert v-if="form.quote" type="info" variant="tonal" density="compact" class="mt-3">
            {{ form.quote.zoneFrom }} → {{ form.quote.zoneTo }} · <strong>{{ soles(form.quote.price) }}</strong>
            · llega en ~{{ form.quote.etaHours }} h
          </VAlert>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="form.open = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="busy" @click="submitNew">Registrar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3000">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
