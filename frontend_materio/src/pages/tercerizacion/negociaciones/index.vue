<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import {
  negotiationClose, negotiationDetail, negotiationList, negotiationPause,
  negotiationPostMessage, negotiationRespond, negotiationResume,
} from '@/services/negotiationService'

const TYPE = {
  sale: { label: 'Venta', color: 'primary', icon: 'ri-user-line', other: 'Cliente' },
  purchase: { label: 'Compra', color: 'warning', icon: 'ri-truck-line', other: 'Transportista' },
}
const STATE = {
  open: { label: 'Abierta', color: 'info' },
  paused: { label: 'Pausada', color: 'warning' },
  agreement: { label: 'Con acuerdo', color: 'success' },
  no_agreement: { label: 'Sin acuerdo', color: 'error' },
  closed: { label: 'Cerrada', color: 'default' },
}
const SENDER = {
  client: { label: 'Cliente', side: 'in' },
  carrier: { label: 'Transportista', side: 'in' },
  taxicarga: { label: 'TaxiCarga', side: 'out' },
  system: { label: 'Sistema', side: 'mid' },
}
const PROP = {
  pending: { label: 'Esperando respuesta', color: 'info' },
  accepted: { label: 'Aceptada', color: 'success' },
  countered: { label: 'Contraofertada', color: 'warning' },
  rejected: { label: 'Rechazada', color: 'error' },
}

const soles = n => (n == null ? '—' : `S/ ${Math.round(n).toLocaleString('es-PE')}`)

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snackbar, { show: true, text: t, color: c })

// --- lista ---
const rows = ref([])
const loadingList = ref(true)
const typeFilter = ref('')
const search = ref('')
let searchTimer

const loadList = async () => {
  loadingList.value = true
  try {
    rows.value = (await negotiationList({
      type: typeFilter.value || undefined,
      search: search.value || undefined,
      active: 'true',
    })).results
  } catch (e) {
    notify(e.message || 'No se pudo cargar.', 'error')
  } finally {
    loadingList.value = false
  }
}
const onSearch = () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadList, 350) }
onMounted(loadList)

// --- detalle / chat ---
const detail = ref(null)
const selectedId = ref(null)
const busy = ref(false)

const open = async id => {
  selectedId.value = id
  detail.value = null
  try { detail.value = await negotiationDetail(id) } catch (e) { notify(e.message, 'error') }
}
const refresh = async () => {
  if (selectedId.value) detail.value = await negotiationDetail(selectedId.value)
  await loadList()
}

const composer = reactive({ sender: 'taxicarga', text: '', amount: '' })
const sendMessage = async () => {
  if (!composer.text.trim() && !composer.amount) return
  busy.value = true
  try {
    detail.value = await negotiationPostMessage(selectedId.value, {
      sender: composer.sender,
      text: composer.text.trim() || undefined,
      proposalAmount: composer.amount || undefined,
    })
    composer.text = ''
    composer.amount = ''
    await loadList()
  } catch (e) { notify(e.message || 'No se pudo enviar.', 'error') } finally { busy.value = false }
}

const counterForm = reactive({ open: false, messageId: null, amount: '', text: '' })
const respond = async (messageId, action, body = {}) => {
  busy.value = true
  try {
    detail.value = await negotiationRespond(messageId, { action, ...body })
    counterForm.open = false
    await loadList()
  } catch (e) { notify(e.message || 'No se pudo.', 'error') } finally { busy.value = false }
}
const openCounter = m => Object.assign(counterForm, { open: true, messageId: m.id, amount: '', text: '' })
const submitCounter = () => respond(counterForm.messageId, 'counter', { amount: counterForm.amount, text: counterForm.text.trim() || undefined })

const doPause = async () => {
  const reason = window.prompt('Motivo de la pausa (opcional):') ?? ''
  busy.value = true
  try { detail.value = await negotiationPause(selectedId.value, reason); await loadList() }
  catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}
const doResume = async () => {
  busy.value = true
  try { detail.value = await negotiationResume(selectedId.value); await loadList() }
  catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}
const doClose = async agreement => {
  if (!window.confirm(agreement ? '¿Cerrar con acuerdo?' : '¿Cerrar sin acuerdo?')) return
  busy.value = true
  try { detail.value = await negotiationClose(selectedId.value, agreement); await loadList() }
  catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}

const canWrite = computed(() => detail.value && !['closed'].includes(detail.value.state))
const margin = computed(() => detail.value?.margin || {})
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">Negociaciones</h1>
    <p class="text-body-2 text-medium-emphasis mb-4">
      Mesas de precio con el cliente (venta) y con transportistas (compra). El asesor lleva la conversación
      y puede pausarla para controlar lo que se ofrece.
    </p>

    <VRow>
      <!-- Lista -->
      <VCol cols="12" md="4">
        <VCard>
          <VCardText class="d-flex flex-column ga-2">
            <VTextField
              v-model="search" prepend-inner-icon="ri-search-line" placeholder="Buscar carga, ruta, contraparte"
              density="compact" hide-details clearable @update:model-value="onSearch"
            />
            <div class="d-flex ga-1">
              <VChip size="small" :variant="typeFilter === '' ? 'flat' : 'tonal'" :color="typeFilter === '' ? 'primary' : undefined" @click="typeFilter = ''; loadList()">Todas</VChip>
              <VChip size="small" :variant="typeFilter === 'sale' ? 'flat' : 'tonal'" :color="typeFilter === 'sale' ? 'primary' : undefined" @click="typeFilter = 'sale'; loadList()">Venta</VChip>
              <VChip size="small" :variant="typeFilter === 'purchase' ? 'flat' : 'tonal'" :color="typeFilter === 'purchase' ? 'warning' : undefined" @click="typeFilter = 'purchase'; loadList()">Compra</VChip>
            </div>
          </VCardText>
          <VDivider />
          <div style="max-height: 70vh; overflow-y: auto;">
            <VProgressLinear v-if="loadingList" indeterminate />
            <div v-else-if="!rows.length" class="text-center text-medium-emphasis py-8 text-body-2">Sin negociaciones activas.</div>
            <VList v-else density="compact" lines="two">
              <VListItem
                v-for="row in rows" :key="row.id"
                :active="row.id === selectedId" @click="open(row.id)"
              >
                <template #prepend>
                  <VIcon :icon="TYPE[row.type]?.icon" :color="TYPE[row.type]?.color" size="20" />
                </template>
                <VListItemTitle class="d-flex align-center ga-2">
                  <span class="font-weight-medium">{{ row.code }}</span>
                  <VChip size="x-small" :color="STATE[row.state]?.color">{{ STATE[row.state]?.label }}</VChip>
                </VListItemTitle>
                <VListItemSubtitle>
                  {{ row.counterpartyName }} · {{ row.route }}
                  <span v-if="row.currentAmount != null"> · {{ soles(row.currentAmount) }}</span>
                </VListItemSubtitle>
              </VListItem>
            </VList>
          </div>
        </VCard>
      </VCol>

      <!-- Chat -->
      <VCol cols="12" md="8">
        <VCard v-if="!detail" class="d-flex align-center justify-center" style="min-height: 60vh;">
          <span class="text-medium-emphasis">Elegí una negociación de la lista.</span>
        </VCard>

        <VCard v-else>
          <VCardText class="d-flex flex-wrap align-center ga-3 pb-2">
            <div>
              <div class="d-flex align-center ga-2">
                <span class="text-h6">{{ detail.code }}</span>
                <VChip size="small" :color="TYPE[detail.type]?.color" variant="tonal">{{ TYPE[detail.type]?.label }}</VChip>
                <VChip size="small" :color="STATE[detail.state]?.color">{{ STATE[detail.state]?.label }}</VChip>
              </div>
              <div class="text-body-2 text-medium-emphasis">
                {{ detail.counterpartyName }} · {{ detail.route }}
                <span v-if="detail.publicationCode"> · publicación {{ detail.publicationCode }}</span>
              </div>
            </div>
            <VSpacer />
            <div class="d-flex ga-1">
              <VBtn v-if="detail.state === 'paused'" size="small" color="success" variant="tonal" :loading="busy" @click="doResume">Reanudar</VBtn>
              <VBtn v-else-if="detail.state !== 'closed'" size="small" color="warning" variant="tonal" :loading="busy" @click="doPause">Pausar</VBtn>
              <VMenu v-if="detail.state !== 'closed'">
                <template #activator="{ props }"><VBtn v-bind="props" size="small" variant="text" icon="ri-more-2-line" /></template>
                <VList>
                  <VListItem @click="doClose(true)"><VListItemTitle>Cerrar con acuerdo</VListItemTitle></VListItem>
                  <VListItem @click="doClose(false)"><VListItemTitle>Cerrar sin acuerdo</VListItemTitle></VListItem>
                </VList>
              </VMenu>
            </div>
          </VCardText>

          <!-- Margen -->
          <VCardText class="py-2">
            <VSheet rounded class="pa-3 d-flex flex-wrap ga-6" color="rgba(var(--v-theme-on-surface), 0.04)">
              <div><div class="text-caption text-medium-emphasis">Venta al cliente</div><div class="font-weight-medium">{{ soles(margin.sale) }}</div></div>
              <div><div class="text-caption text-medium-emphasis">Costo tercerización</div><div class="font-weight-medium">{{ soles(margin.cost) }}</div></div>
              <div>
                <div class="text-caption text-medium-emphasis">Margen</div>
                <div class="font-weight-bold" :class="margin.amount == null ? '' : (margin.amount >= 0 ? 'text-success' : 'text-error')">
                  {{ soles(margin.amount) }}<span v-if="margin.pct != null" class="text-caption"> ({{ margin.pct }}%)</span>
                </div>
              </div>
              <div v-if="detail.targetAmount != null">
                <div class="text-caption text-medium-emphasis">Objetivo</div><div class="font-weight-medium">{{ soles(detail.targetAmount) }}</div>
              </div>
            </VSheet>
            <div v-if="detail.pauseReason" class="text-caption text-warning mt-2">
              <VIcon icon="ri-pause-circle-line" size="14" /> Pausada: {{ detail.pauseReason }}
            </div>
          </VCardText>

          <VDivider />

          <!-- Mensajes -->
          <VCardText style="max-height: 46vh; overflow-y: auto;" class="d-flex flex-column ga-3">
            <template v-for="m in detail.messages" :key="m.id">
              <div v-if="SENDER[m.sender]?.side === 'mid'" class="text-center text-caption text-medium-emphasis">
                {{ m.text }}
              </div>
              <div v-else class="d-flex" :class="SENDER[m.sender]?.side === 'out' ? 'justify-end' : 'justify-start'">
                <div style="max-width: 78%;">
                  <div class="text-caption text-medium-emphasis mb-1" :class="SENDER[m.sender]?.side === 'out' ? 'text-right' : ''">
                    {{ SENDER[m.sender]?.label }}<span v-if="m.authorName"> · {{ m.authorName }}</span>
                    <VChip v-if="m.channel !== 'crm'" size="x-small" class="ms-1" variant="tonal">{{ m.channel }}</VChip>
                  </div>
                  <VCard
                    :color="m.kind === 'propuesta' ? (TYPE[detail.type]?.color) : undefined"
                    :variant="m.kind === 'propuesta' ? 'tonal' : 'outlined'"
                    class="pa-3"
                  >
                    <div v-if="m.text" class="text-body-2" style="white-space: pre-wrap;">{{ m.text }}</div>
                    <div v-if="m.proposalAmount != null" class="mt-1">
                      <div class="text-h6">{{ soles(m.proposalAmount) }}</div>
                      <VChip size="x-small" :color="PROP[m.proposalState]?.color" class="mt-1">{{ PROP[m.proposalState]?.label }}</VChip>
                      <div v-if="m.proposalState === 'pending' && canWrite" class="d-flex ga-1 mt-2">
                        <VBtn size="x-small" color="success" :loading="busy" @click="respond(m.id, 'accept')">Aceptar</VBtn>
                        <VBtn size="x-small" color="warning" variant="tonal" @click="openCounter(m)">Contraofertar</VBtn>
                        <VBtn size="x-small" color="error" variant="tonal" :loading="busy" @click="respond(m.id, 'reject')">Rechazar</VBtn>
                      </div>
                    </div>
                    <div class="text-caption text-disabled mt-1">{{ new Date(m.createdAt).toLocaleString('es-PE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) }}</div>
                  </VCard>
                </div>
              </div>
            </template>
          </VCardText>

          <VDivider />

          <!-- Composer -->
          <VCardText v-if="canWrite">
            <div class="d-flex flex-wrap align-center ga-2 mb-2">
              <span class="text-caption text-medium-emphasis">Registrar como:</span>
              <VChip size="small" :variant="composer.sender === 'taxicarga' ? 'flat' : 'tonal'" :color="composer.sender === 'taxicarga' ? 'primary' : undefined" @click="composer.sender = 'taxicarga'">TaxiCarga (yo)</VChip>
              <VChip size="small" :variant="composer.sender === 'client' ? 'flat' : 'tonal'" :color="composer.sender === 'client' ? 'primary' : undefined" @click="composer.sender = 'client'">Cliente</VChip>
              <VChip v-if="detail.type === 'purchase'" size="small" :variant="composer.sender === 'carrier' ? 'flat' : 'tonal'" :color="composer.sender === 'carrier' ? 'warning' : undefined" @click="composer.sender = 'carrier'">Transportista</VChip>
            </div>
            <VTextarea v-model="composer.text" placeholder="Escribí el mensaje…" rows="2" auto-grow density="compact" hide-details class="mb-2" />
            <div class="d-flex align-center ga-2">
              <VTextField v-model="composer.amount" type="number" placeholder="Monto propuesta (opcional)" prefix="S/" density="compact" hide-details style="max-width: 220px;" />
              <VSpacer />
              <VBtn :loading="busy" :disabled="!composer.text.trim() && !composer.amount" @click="sendMessage">
                {{ composer.amount ? 'Enviar propuesta' : 'Enviar' }}
              </VBtn>
            </div>
          </VCardText>
          <VCardText v-else class="text-center text-medium-emphasis text-body-2">
            Negociación cerrada.
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

    <!-- Contraoferta -->
    <VDialog v-model="counterForm.open" max-width="420">
      <VCard>
        <VCardTitle>Contraofertar</VCardTitle>
        <VCardText>
          <VTextField v-model="counterForm.amount" label="Nuevo monto (S/)" type="number" class="mb-2" />
          <VTextarea v-model="counterForm.text" label="Nota (opcional)" rows="2" auto-grow />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="counterForm.open = false">Cancelar</VBtn>
          <VBtn color="warning" :loading="busy" :disabled="!counterForm.amount" @click="submitCounter">Enviar contraoferta</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
