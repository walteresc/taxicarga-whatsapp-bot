<script setup>
import { onMounted, reactive, ref } from 'vue'

import { useRouter } from 'vue-router'

import {
  leadServiceData, quoteClosePrice, quoteDetail, quoteList, quoteNegotiate,
  quoteRevise, quoteSetState, quoteToOutsourcing,
} from '@/services/commercialService'
import { usePipelineStore } from '@/stores/pipelineStore'
import ServiceViewDialog from '@/pages/atencion/bandeja-entrada/components/ServiceViewDialog.vue'
import QuickQuoteDialog from '@/pages/atencion/bandeja-entrada/components/QuickQuoteDialog.vue'
import QuickBookingDialog from '@/pages/atencion/bandeja-entrada/components/QuickBookingDialog.vue'

const router = useRouter()
const pipeline = usePipelineStore()

const STATE = {
  sent: { label: 'Enviada', color: 'info' },
  delivered: { label: 'Entregada', color: 'info' },
  negotiating: { label: 'En negociación', color: 'warning' },
  accepted: { label: 'Aceptada', color: 'success' },
  rejected: { label: 'Rechazada', color: 'error' },
  expired: { label: 'Vencida', color: 'default' },
}
const TRANSITIONS = {
  sent: ['delivered', 'negotiating', 'rejected', 'expired'],
  delivered: ['negotiating', 'rejected', 'expired'],
  negotiating: ['rejected', 'expired'],
}

const rows = ref([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const stateFilter = ref('')
let searchTimer

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snackbar, { show: true, text: t, color: c })
const soles = n => `S/ ${Math.round(n || 0).toLocaleString('es-PE')}`

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    rows.value = (await quoteList({ search: search.value, state: stateFilter.value })).results
  } catch (e) {
    error.value = e.message || 'No se pudo cargar.'
  } finally {
    loading.value = false
  }
}
const onSearch = () => { clearTimeout(searchTimer); searchTimer = setTimeout(load, 350) }
onMounted(load)

// detalle
const detail = ref(null)
const detailOpen = ref(false)
const openDetail = async row => {
  detail.value = null
  detailOpen.value = true
  try { detail.value = await quoteDetail(row.id) } catch (e) { notify(e.message, 'error') }
}

// --- Ver servicio (modal compartido con la bandeja) ---
const viewOpen = ref(false)
const viewLeadId = ref(null)
const viewServiceData = ref({})
const viewInterprovincial = ref(false)
const quoteOpen = ref(false)
const bookingOpen = ref(false)

const openServiceView = async row => {
  if (!row.leadId) { notify('Esta cotización no tiene lead asociado.', 'warning'); return }
  viewLeadId.value = row.leadId
  viewInterprovincial.value = !!row.isInterprovincial
  viewServiceData.value = {}
  viewOpen.value = true
  try { viewServiceData.value = (await leadServiceData(row.leadId)).serviceData || {} } catch { /* precios vienen de /stage */ }
}

const afterServiceAction = async () => {
  quoteOpen.value = false
  bookingOpen.value = false
  viewOpen.value = false
  pipeline.bump()
  await load()
}

const markRowSeen = () => {
  const r = rows.value.find(x => x.leadId === viewLeadId.value)
  if (r) r.seen = true
}

const openConversation = row => {
  if (row.conversationId) router.push(`/atencion/bandeja-entrada?conversation=${row.conversationId}`)
}

const busy = ref(false)
const changeState = async target => {
  busy.value = true
  try {
    await quoteSetState(detail.value.id, target)
    notify('Estado actualizado.')
    await openDetail(detail.value)
    await load()
  } catch (e) { notify(e.message || 'No se pudo cambiar el estado.', 'error') } finally { busy.value = false }
}

// nueva revisión
const reviseForm = reactive({ open: false, price: '', conditions: '', validityDays: 7, whatsappMessage: '' })
const submitRevise = async () => {
  busy.value = true
  try {
    detail.value = await quoteRevise(detail.value.id, { ...reviseForm })
    notify('Nueva revisión enviada al cliente.')
    reviseForm.open = false
    await load()
  } catch (e) { notify(e.message || 'No se pudo revisar.', 'error') } finally { busy.value = false }
}

// --- F1: negociación ---
const negForm = reactive({ open: false, clientPrice: '', note: '' })
const submitNegotiate = async () => {
  busy.value = true
  try {
    detail.value = await quoteNegotiate(detail.value.id, {
      clientPrice: negForm.clientPrice || undefined,
      note: negForm.note || undefined,
    })
    notify('Cotización en negociación.')
    negForm.open = false
    await load(); pipeline.bump()
  } catch (e) { notify(e.message || 'No se pudo.', 'error') } finally { busy.value = false }
}

const outForm = reactive({ open: false, priceMode: 'referencial', referencePrice: '' })
const submitOutsourcing = async () => {
  busy.value = true
  try {
    const res = await quoteToOutsourcing(detail.value.id, {
      priceMode: outForm.priceMode,
      referencePrice: outForm.referencePrice || undefined,
    })
    notify(`Derivada a tercerización · publicación ${res.publicationCode} (borrador).`)
    outForm.open = false
    await openDetail(detail.value); await load(); pipeline.bump()
  } catch (e) { notify(e.message || 'No se pudo derivar.', 'error') } finally { busy.value = false }
}

const closeForm = reactive({ open: false, price: '', note: '' })
const submitClosePrice = async () => {
  busy.value = true
  try {
    const res = await quoteClosePrice(detail.value.id, {
      price: closeForm.price, note: closeForm.note || undefined,
    })
    notify(`Precio cerrado. Reserva ${res.bookingCode} creada.`)
    closeForm.open = false
    detailOpen.value = false
    await load(); pipeline.bump()
  } catch (e) { notify(e.message || 'No se pudo cerrar.', 'error') } finally { busy.value = false }
}
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">
      Cotizados
    </h1>
    <p class="text-body-2 text-medium-emphasis mb-4">
      Precios enviados al cliente. Cuando acepte (por WhatsApp), márcala aceptada aquí para crear la reserva.
    </p>

    <VCard>
      <VCardText class="d-flex flex-wrap ga-3">
        <VTextField v-model="search" prepend-inner-icon="ri-search-line" label="Buscar código, cliente o ruta" density="compact" hide-details clearable style="max-width: 340px;" @update:model-value="onSearch" />
        <VSelect
          v-model="stateFilter" label="Estado" density="compact" hide-details clearable style="max-width: 200px;"
          :items="Object.entries(STATE).map(([value, s]) => ({ title: s.label, value }))"
          @update:model-value="load"
        />
      </VCardText>

      <VAlert v-if="error" type="error" variant="tonal" class="ma-4">{{ error }}</VAlert>

      <VDivider />

      <VTable>
        <thead>
          <tr><th>Código</th><th>Cliente</th><th>Ruta</th><th>Estado</th><th class="text-right">Precio</th><th>Origen</th><th class="text-right">Acciones</th></tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="7" class="text-center py-8"><VProgressCircular indeterminate /></td></tr>
          <tr v-else-if="!rows.length"><td colspan="7" class="text-center text-medium-emphasis py-10">Sin cotizaciones.</td></tr>
          <tr v-for="row in rows" v-else :key="row.id">
            <td class="font-weight-medium text-primary" style="cursor: pointer;" title="Ver detalle" @click="openServiceView(row)">
              <VBadge v-if="!row.seen" dot inline color="primary" class="me-1" title="Sin abrir" />{{ row.code }}
            </td>
            <td>{{ row.customerName }}</td>
            <td>{{ row.route }}</td>
            <td>
              <VChip size="small" :color="STATE[row.state]?.color">{{ STATE[row.state]?.label || row.state }}</VChip>
              <div v-if="row.outsourced" class="text-caption text-medium-emphasis mt-1">
                <VIcon icon="ri-truck-line" size="12" /> tercerizada · {{ row.outsourced.code }}
              </div>
            </td>
            <td class="text-right">
              {{ soles(row.currentPrice) }}
              <div v-if="row.clientPrice != null" class="text-caption text-warning">cliente: {{ soles(row.clientPrice) }}</div>
              <div v-if="row.agreedPrice != null" class="text-caption text-success">acordado: {{ soles(row.agreedPrice) }}</div>
            </td>
            <td class="text-capitalize">{{ row.origin }}</td>
            <td class="text-right text-no-wrap">
              <VBtn size="small" variant="text" icon="ri-eye-line" title="Ver detalle del servicio" :disabled="!row.leadId" @click="openServiceView(row)" />
              <VBtn size="small" variant="text" icon="ri-chat-3-line" title="Abrir conversación" :disabled="!row.conversationId" @click="openConversation(row)" />
              <VBtn size="small" variant="tonal" class="ms-1" @click="openDetail(row)">Revisiones</VBtn>
            </td>
          </tr>
        </tbody>
      </VTable>
    </VCard>

    <!-- Detalle -->
    <VDialog v-model="detailOpen" max-width="680">
      <VCard>
        <VCardTitle class="d-flex align-center ga-2">
          {{ detail?.code || 'Cotización' }}
          <VChip v-if="detail" size="small" :color="STATE[detail.state]?.color">{{ STATE[detail.state]?.label || detail.state }}</VChip>
        </VCardTitle>
        <VCardText v-if="!detail" class="text-center py-8"><VProgressCircular indeterminate /></VCardText>
        <VCardText v-else>
          <VTable density="compact" class="text-body-2 mb-4">
            <tbody>
              <tr><td>Cliente</td><td>{{ detail.service.customer.name }}</td></tr>
              <tr><td>Ruta</td><td>{{ detail.service.origin }} → {{ detail.service.destination }}</td></tr>
              <tr><td>Precio actual (nuestra oferta)</td><td class="font-weight-bold">{{ soles(detail.currentPrice) }}</td></tr>
              <tr v-if="detail.clientPrice != null"><td>Contraoferta del cliente</td><td class="text-warning font-weight-medium">{{ soles(detail.clientPrice) }}</td></tr>
              <tr v-if="detail.agreedPrice != null"><td>Precio acordado</td><td class="text-success font-weight-bold">{{ soles(detail.agreedPrice) }}</td></tr>
              <tr v-if="detail.outsourced"><td>Tercerización</td><td><VChip size="x-small" color="secondary" variant="tonal">{{ detail.outsourced.code }} · {{ detail.outsourced.state }} · {{ detail.outsourced.priceMode }}</VChip></td></tr>
            </tbody>
          </VTable>

          <div class="text-overline mb-1">Revisiones</div>
          <VTable density="compact">
            <thead><tr><th>#</th><th class="text-right">Precio</th><th>Enviada</th><th>Condiciones</th></tr></thead>
            <tbody>
              <tr v-for="r in detail.revisions" :key="r.number">
                <td>v{{ r.number }}</td>
                <td class="text-right">{{ soles(r.price) }}</td>
                <td>{{ r.sent ? (r.sentAt || 'sí').slice(0, 10) : '—' }}</td>
                <td class="text-caption">{{ r.conditions || '—' }}</td>
              </tr>
            </tbody>
          </VTable>
        </VCardText>

        <VDivider v-if="detail && !detail.hasBooking" />
        <div v-if="detail && !detail.hasBooking" class="px-4 py-3 d-flex flex-wrap ga-2">
          <span class="text-overline text-medium-emphasis w-100">Negociación</span>
          <VBtn
            size="small" variant="tonal" prepend-icon="ri-discuss-line"
            :disabled="busy"
            @click="Object.assign(negForm, { open: true, clientPrice: detail.clientPrice != null ? String(detail.clientPrice) : '', note: '' })"
          >
            Negociar con el cliente
          </VBtn>
          <VBtn
            size="small" variant="tonal" prepend-icon="ri-truck-line"
            :disabled="busy || !!detail.outsourced"
            @click="Object.assign(outForm, { open: true, priceMode: 'referencial', referencePrice: '' })"
          >
            {{ detail.outsourced ? 'Ya derivada a tercerización' : 'Derivar a tercerización' }}
          </VBtn>
          <VBtn
            size="small" color="success" prepend-icon="ri-check-double-line"
            :disabled="busy"
            @click="Object.assign(closeForm, { open: true, price: String(detail.agreedPrice ?? detail.clientPrice ?? detail.currentPrice ?? ''), note: '' })"
          >
            Cerrar precio
          </VBtn>
        </div>

        <VCardActions v-if="detail" class="flex-wrap px-4 pb-4 ga-2">
          <VMenu v-if="TRANSITIONS[detail.state]?.length">
            <template #activator="{ props }">
              <VBtn v-bind="props" variant="text" size="small" :disabled="busy">Cambiar estado</VBtn>
            </template>
            <VList>
              <VListItem v-for="t in TRANSITIONS[detail.state]" :key="t" @click="changeState(t)">
                <VListItemTitle>{{ STATE[t]?.label }}</VListItemTitle>
              </VListItem>
            </VList>
          </VMenu>
          <VBtn variant="text" size="small" :disabled="busy || detail.state === 'accepted'" @click="Object.assign(reviseForm, { open: true, price: String(detail.currentPrice || ''), conditions: '', validityDays: 7, whatsappMessage: '' })">
            Nueva revisión
          </VBtn>
          <VSpacer />
          <VBtn variant="text" @click="detailOpen = false">Cerrar</VBtn>
          <VChip v-if="detail.hasBooking" color="success" size="small">Reserva creada</VChip>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Nueva revisión -->
    <VDialog v-model="reviseForm.open" max-width="480">
      <VCard>
        <VCardTitle>Nueva revisión</VCardTitle>
        <VCardText>
          <VTextField v-model="reviseForm.price" label="Nuevo precio (S/)" type="number" class="mb-2" />
          <VTextField v-model.number="reviseForm.validityDays" label="Vigencia (días)" type="number" class="mb-2" />
          <VTextarea v-model="reviseForm.conditions" label="Condiciones" rows="2" auto-grow class="mb-2" />
          <VTextarea v-model="reviseForm.whatsappMessage" label="Mensaje WhatsApp (autogenerado si vacío)" rows="2" auto-grow />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="reviseForm.open = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="busy" :disabled="!reviseForm.price" @click="submitRevise">Enviar revisión</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Negociar con el cliente -->
    <VDialog v-model="negForm.open" max-width="460">
      <VCard>
        <VCardTitle>Negociar con el cliente</VCardTitle>
        <VCardText>
          <p class="text-body-2 text-medium-emphasis mb-3">
            Pasa la cotización a "En negociación". El chat de negociación llega en la próxima fase;
            por ahora registrá la contraoferta del cliente y una nota.
          </p>
          <VTextField v-model="negForm.clientPrice" label="Contraoferta del cliente (S/)" type="number" class="mb-2" clearable />
          <VTextarea v-model="negForm.note" label="Nota (queda en el historial del lead)" rows="2" auto-grow />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="negForm.open = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="busy" @click="submitNegotiate">Poner en negociación</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Derivar a tercerización -->
    <VDialog v-model="outForm.open" max-width="480">
      <VCard>
        <VCardTitle>Derivar a tercerización</VCardTitle>
        <VCardText>
          <p class="text-body-2 text-medium-emphasis mb-3">
            Se crea la reserva (si faltan datos, completalos primero) marcada como
            <strong>tercerizada</strong>, y una publicación en <strong>borrador</strong>.
            El Despacho la publica a los transportistas.
          </p>
          <VSelect
            v-model="outForm.priceMode" label="Modo de precio" class="mb-2"
            :items="[
              { title: 'Referencial (hay un precio guía, se puede ofertar)', value: 'referencial' },
              { title: 'Abierto (el transportista propone)', value: 'abierto' },
              { title: 'Fijo (precio cerrado, solo aceptan)', value: 'fijo' },
            ]"
          />
          <VTextField
            v-if="outForm.priceMode !== 'abierto'"
            v-model="outForm.referencePrice" type="number"
            label="Precio hacia el transportista (S/) — costo, no venta"
          />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="outForm.open = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="busy" @click="submitOutsourcing">Derivar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Cerrar precio -->
    <VDialog v-model="closeForm.open" max-width="460">
      <VCard>
        <VCardTitle>Cerrar precio con el cliente</VCardTitle>
        <VCardText>
          <p class="text-body-2 text-medium-emphasis mb-3">
            Confirmás el <strong>acuerdo</strong>. Si el precio difiere de la última oferta,
            se envía una revisión a ese precio. Se crea la <strong>reserva</strong>.
          </p>
          <VTextField v-model="closeForm.price" label="Precio acordado (S/)" type="number" class="mb-2" />
          <VTextarea v-model="closeForm.note" label="Nota / condiciones" rows="2" auto-grow />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="closeForm.open = false">Cancelar</VBtn>
          <VBtn color="success" :loading="busy" :disabled="!closeForm.price" @click="submitClosePrice">Cerrar y crear reserva</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Ver servicio: modal compartido con la bandeja -->
    <ServiceViewDialog
      v-if="viewOpen && viewLeadId"
      :lead-id="viewLeadId"
      :service-data="viewServiceData"
      context="quotes"
      @close="viewOpen = false"
      @quote="quoteOpen = true"
      @book="bookingOpen = true"
      @changed="afterServiceAction"
      @seen="markRowSeen"
    />
    <QuickQuoteDialog
      v-if="quoteOpen && viewLeadId"
      :lead-id="viewLeadId"
      :service-data="viewServiceData"
      :interprovincial="viewInterprovincial"
      draggable
      @close="quoteOpen = false"
      @done="afterServiceAction"
    />
    <QuickBookingDialog
      v-if="bookingOpen && viewLeadId"
      :lead-id="viewLeadId"
      :service-data="viewServiceData"
      draggable
      @close="bookingOpen = false"
      @done="afterServiceAction"
    />

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
