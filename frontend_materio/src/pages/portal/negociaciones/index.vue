<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import {
  carrierNegotiationDetail, carrierNegotiationRespond, carrierNegotiations, carrierNegotiationSend,
} from '@/services/portalService'

const STATE = {
  open: { label: 'Abierta', color: 'info' },
  paused: { label: 'En pausa (Lima Express)', color: 'warning' },
  agreement: { label: 'Con acuerdo', color: 'success' },
  no_agreement: { label: 'Sin acuerdo', color: 'error' },
  closed: { label: 'Cerrada', color: 'default' },
}
const soles = n => (n == null ? '—' : `S/ ${Math.round(n).toLocaleString('es-PE')}`)

const rows = ref([])
const detail = ref(null)
const selectedId = ref(null)
const loading = ref(true)
const busy = ref(false)
const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snackbar, { show: true, text: t, color: c })

const loadList = async () => {
  try { rows.value = (await carrierNegotiations()).results } finally { loading.value = false }
}
onMounted(loadList)

const open = async id => {
  selectedId.value = id
  detail.value = null
  try { detail.value = await carrierNegotiationDetail(id) } catch (e) { notify(e.message, 'error') }
}

const composer = reactive({ text: '', amount: '' })
const send = async () => {
  if (!composer.text.trim() && !composer.amount) return
  busy.value = true
  try {
    detail.value = await carrierNegotiationSend(selectedId.value, {
      text: composer.text.trim() || undefined,
      proposalAmount: composer.amount || undefined,
    })
    composer.text = ''
    composer.amount = ''
    await loadList()
  } catch (e) { notify(e.message || 'No se pudo enviar.', 'error') } finally { busy.value = false }
}

const counter = reactive({ open: false, messageId: null, amount: '' })
const respond = async (messageId, action, amount) => {
  busy.value = true
  try {
    detail.value = await carrierNegotiationRespond(messageId, { action, amount })
    counter.open = false
    await loadList()
  } catch (e) { notify(e.message || 'No se pudo.', 'error') } finally { busy.value = false }
}

const canWrite = computed(() => detail.value && !['closed', 'paused'].includes(detail.value.state))
</script>

<template>
  <div>
    <h1 class="text-h5 font-weight-bold mb-4">Negociaciones</h1>
    <VRow>
      <VCol cols="12" md="4">
        <VCard>
          <VProgressLinear v-if="loading" indeterminate />
          <div v-else-if="!rows.length" class="text-center text-medium-emphasis py-8 text-body-2">Sin negociaciones.</div>
          <VList v-else density="compact" lines="two">
            <VListItem
              v-for="row in rows" :key="row.id" :active="row.id === selectedId" @click="open(row.id)"
            >
              <VListItemTitle class="d-flex align-center ga-2">
                <span class="font-weight-medium">{{ row.publicationCode }}</span>
                <VChip size="x-small" :color="STATE[row.state]?.color">{{ STATE[row.state]?.label }}</VChip>
              </VListItemTitle>
              <VListItemSubtitle>
                Sobre la mesa: {{ soles(row.currentAmount) }}
              </VListItemSubtitle>
            </VListItem>
          </VList>
        </VCard>
      </VCol>

      <VCol cols="12" md="8">
        <VCard v-if="!detail" class="d-flex align-center justify-center" style="min-height: 40vh;">
          <span class="text-medium-emphasis">Elegí una negociación.</span>
        </VCard>
        <VCard v-else>
          <VCardText class="d-flex align-center ga-2">
            <span class="text-h6">{{ detail.publicationCode }}</span>
            <VChip size="small" :color="STATE[detail.state]?.color">{{ STATE[detail.state]?.label }}</VChip>
            <VSpacer />
            <span class="text-body-2">Guía: {{ soles(detail.targetPrice) }}</span>
          </VCardText>
          <VDivider />
          <VCardText style="max-height: 48vh; overflow-y: auto;" class="d-flex flex-column ga-3">
            <template v-for="m in detail.messages" :key="m.id">
              <div v-if="m.sender === 'system'" class="text-center text-caption text-medium-emphasis">{{ m.text }}</div>
              <div v-else class="d-flex" :class="m.sender === 'you' ? 'justify-end' : 'justify-start'">
                <div style="max-width: 78%;">
                  <div class="text-caption text-medium-emphasis mb-1" :class="m.sender === 'you' ? 'text-right' : ''">
                    {{ m.sender === 'you' ? 'Vos' : 'Lima Express' }}
                  </div>
                  <VCard :variant="m.proposalAmount != null ? 'tonal' : 'outlined'" :color="m.proposalAmount != null ? 'primary' : undefined" class="pa-3">
                    <div v-if="m.text" class="text-body-2" style="white-space: pre-wrap;">{{ m.text }}</div>
                    <div v-if="m.proposalAmount != null" class="mt-1">
                      <div class="text-h6">{{ soles(m.proposalAmount) }}</div>
                      <div v-if="m.proposalState === 'pending' && m.proposalFromTaxicarga && canWrite" class="d-flex ga-1 mt-2">
                        <VBtn size="x-small" color="success" :loading="busy" @click="respond(m.id, 'accept')">Aceptar</VBtn>
                        <VBtn size="x-small" color="warning" variant="tonal" @click="Object.assign(counter, { open: true, messageId: m.id, amount: '' })">Contraofertar</VBtn>
                        <VBtn size="x-small" color="error" variant="tonal" :loading="busy" @click="respond(m.id, 'reject')">Rechazar</VBtn>
                      </div>
                      <div v-else class="text-caption text-medium-emphasis mt-1">{{ m.proposalState }}</div>
                    </div>
                  </VCard>
                </div>
              </div>
            </template>
          </VCardText>
          <VDivider />
          <VCardText v-if="canWrite">
            <VTextarea v-model="composer.text" placeholder="Escribí un mensaje…" rows="2" auto-grow density="compact" hide-details class="mb-2" />
            <div class="d-flex align-center ga-2">
              <VTextField v-model="composer.amount" type="number" placeholder="Proponer monto (opcional)" prefix="S/" density="compact" hide-details style="max-width: 220px;" />
              <VSpacer />
              <VBtn :loading="busy" :disabled="!composer.text.trim() && !composer.amount" @click="send">
                {{ composer.amount ? 'Enviar propuesta' : 'Enviar' }}
              </VBtn>
            </div>
          </VCardText>
          <VCardText v-else class="text-center text-medium-emphasis text-body-2">
            {{ detail.state === 'paused' ? 'Lima Express pausó esta negociación.' : 'Negociación cerrada.' }}
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

    <VDialog v-model="counter.open" max-width="400">
      <VCard>
        <VCardTitle>Contraofertar</VCardTitle>
        <VCardText>
          <VTextField v-model="counter.amount" label="Tu monto (S/)" type="number" />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="counter.open = false">Cancelar</VBtn>
          <VBtn color="warning" :loading="busy" :disabled="!counter.amount" @click="respond(counter.messageId, 'counter', counter.amount)">Enviar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </div>
</template>
