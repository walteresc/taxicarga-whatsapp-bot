<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  customerAccept, customerLoad, customerNegotiate, customerNegotiation,
  customerNegotiationRespond, customerNegotiationSend, customerPay, customerRequestAdvisor,
} from '@/services/customerPortalService'

const route = useRoute()
const code = route.params.code

const STATUS = {
  draft: 'Borrador', quoted: 'Precio listo', negotiating: 'En negociación',
  booked: 'Reservado', scheduled: 'Programado', in_progress: 'En curso', completed: 'Finalizado',
}
const OP_STATE = {
  pendiente: 'Pendiente de asignar', programado: 'Programado', en_ruta: 'En ruta',
  en_servicio: 'En servicio', finalizado: 'Finalizado',
}
const soles = n => (n == null ? '—' : `S/ ${Math.round(n).toLocaleString('es-PE')}`)

const load = ref(null)
const neg = ref(null)
const loading = ref(true)
const busy = ref(false)
const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snackbar, { show: true, text: t, color: c })

const refresh = async () => {
  load.value = await customerLoad(code)
  if (load.value.negotiating) {
    try { neg.value = await customerNegotiation(code) } catch { neg.value = null }
  }
}
onMounted(async () => { try { await refresh() } finally { loading.value = false } })

const doAccept = async () => {
  busy.value = true
  try { await customerAccept(code, {}); await refresh(); notify('¡Precio aceptado! Un asesor coordina la reserva.') }
  catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}
const doRequestAdvisor = async () => {
  busy.value = true
  try { await customerRequestAdvisor(code); await refresh(); notify('Listo, un asesor te va a contactar.') }
  catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}

const billing = computed(() => load.value?.billing || null)
const doPay = async installmentId => {
  busy.value = true
  try {
    const r = await customerPay(code, { installmentId })
    window.location.assign(r.url)
  } catch (e) { notify(e.message, 'error'); busy.value = false }
}

const negForm = reactive({ open: false, counterOffer: '', note: '' })
const startNegotiation = async () => {
  busy.value = true
  try {
    await customerNegotiate(code, { counterOffer: negForm.counterOffer || undefined, note: negForm.note || undefined })
    negForm.open = false
    await refresh()
    notify('Abrimos la negociación. Vas a ver las respuestas acá.')
  } catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}

const chat = reactive({ text: '', amount: '' })
const send = async () => {
  if (!chat.text.trim() && !chat.amount) return
  busy.value = true
  try {
    neg.value = await customerNegotiationSend(code, {
      text: chat.text.trim() || undefined, proposalAmount: chat.amount || undefined,
    })
    chat.text = ''; chat.amount = ''
    await refresh()
  } catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}
const respond = async (messageId, action, amount) => {
  busy.value = true
  try { neg.value = await customerNegotiationRespond(code, messageId, { action, amount }); await refresh() }
  catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}
const counter = reactive({ open: false, messageId: null, amount: '' })

const canDecide = computed(() => load.value && ['quoted'].includes(load.value.status))
const price = computed(() => load.value?.price || {})
</script>

<template>
  <div>
    <VProgressLinear v-if="loading" indeterminate />
    <template v-else-if="load">
      <div class="d-flex align-center ga-2 mb-1">
        <h1 class="text-h5 font-weight-bold">{{ load.code }}</h1>
        <VChip size="small" color="primary">{{ STATUS[load.status] || load.status }}</VChip>
      </div>
      <p class="text-body-2 text-medium-emphasis mb-4">
        {{ load.origin }} → {{ load.destination }}
        · {{ load.date ? new Date(load.date).toLocaleDateString('es-PE') : 'fecha por confirmar' }}
        <span v-if="load.schedule"> · {{ load.schedule }}</span>
      </p>

      <VRow>
        <VCol cols="12" md="7">
          <!-- Precio + decisión -->
          <VCard class="mb-4">
            <VCardText>
              <div class="text-overline mb-1">Precio</div>
              <template v-if="price.mode === 'advisor' || price.mode === 'pending'">
                <p class="text-body-2 text-medium-emphasis mb-3">
                  Esta carga necesita que un asesor confirme el precio.
                </p>
                <VBtn v-if="canDecide || load.status === 'quoted'" color="primary" :loading="busy" @click="doRequestAdvisor">
                  Que me contacte un asesor
                </VBtn>
              </template>
              <template v-else>
                <div class="text-h4 font-weight-bold mb-1">{{ soles(price.amount) }}</div>
                <div v-if="price.range" class="text-caption text-medium-emphasis mb-1">
                  Rango estimado {{ soles(price.range[0]) }} – {{ soles(price.range[1]) }}
                </div>
                <div v-if="price.daysEstimated" class="text-caption text-medium-emphasis mb-3">
                  Llega en {{ price.daysEstimated }} días hábiles aprox.
                </div>
                <div v-if="canDecide" class="d-flex flex-wrap ga-2 mt-3">
                  <VBtn color="success" :loading="busy" @click="doAccept">Aceptar este precio</VBtn>
                  <VBtn variant="tonal" @click="Object.assign(negForm, { open: true, counterOffer: '', note: '' })">
                    Esperar mejores ofertas
                  </VBtn>
                </div>
              </template>
            </VCardText>
          </VCard>

          <!-- Pagos -->
          <VCard v-if="billing" class="mb-4">
            <VCardText>
              <div class="d-flex align-center mb-2">
                <span class="text-overline">Pagos</span>
                <VSpacer />
                <span class="text-body-2">Saldo: <strong>{{ soles(billing.balance) }}</strong></span>
              </div>
              <VTable density="compact" class="text-body-2">
                <tbody>
                  <tr v-for="i in billing.installments" :key="i.id">
                    <td>{{ i.label }}<span v-if="i.dueDate" class="text-caption text-medium-emphasis"> · vence {{ i.dueDate }}</span></td>
                    <td class="text-right">{{ soles(i.amount) }}</td>
                    <td class="text-right" style="width: 120px;">
                      <VChip v-if="i.state === 'pagada'" size="x-small" color="success">Pagada</VChip>
                      <VBtn v-else size="x-small" color="primary" :loading="busy" @click="doPay(i.id)">
                        Pagar {{ soles(i.amount - i.paid) }}
                      </VBtn>
                    </td>
                  </tr>
                </tbody>
              </VTable>
            </VCardText>
          </VCard>

          <!-- Negociación -->
          <VCard v-if="load.negotiating && neg">
            <VCardText>
              <div class="text-overline mb-2">Negociación</div>
              <div v-if="neg.paused" class="text-caption text-warning mb-2">
                Lima Express pausó la negociación por un momento.
              </div>
              <div class="d-flex flex-column ga-3" style="max-height: 44vh; overflow-y: auto;">
                <template v-for="m in neg.messages" :key="m.id">
                  <div v-if="m.sender === 'system'" class="text-center text-caption text-medium-emphasis">{{ m.text }}</div>
                  <div v-else class="d-flex" :class="m.sender === 'you' ? 'justify-end' : 'justify-start'">
                    <div style="max-width: 80%;">
                      <div class="text-caption text-medium-emphasis mb-1" :class="m.sender === 'you' ? 'text-right' : ''">
                        {{ m.sender === 'you' ? 'Vos' : 'Lima Express' }}
                      </div>
                      <VCard :variant="m.proposalAmount != null ? 'tonal' : 'outlined'" :color="m.proposalAmount != null ? 'primary' : undefined" class="pa-3">
                        <div v-if="m.text" class="text-body-2" style="white-space: pre-wrap;">{{ m.text }}</div>
                        <div v-if="m.proposalAmount != null" class="mt-1">
                          <div class="text-h6">{{ soles(m.proposalAmount) }}</div>
                          <div v-if="m.proposalState === 'pending' && m.proposalFromTaxicarga && !neg.paused" class="d-flex ga-1 mt-2">
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
              </div>
              <VDivider class="my-3" />
              <VTextarea v-model="chat.text" placeholder="Escribí un mensaje…" rows="2" auto-grow density="compact" hide-details class="mb-2" />
              <div class="d-flex align-center ga-2">
                <VTextField v-model="chat.amount" type="number" placeholder="Proponer monto" prefix="S/" density="compact" hide-details style="max-width: 200px;" />
                <VSpacer />
                <VBtn :loading="busy" :disabled="!chat.text.trim() && !chat.amount" @click="send">Enviar</VBtn>
              </div>
            </VCardText>
          </VCard>
        </VCol>

        <VCol cols="12" md="5">
          <VCard>
            <VCardText>
              <div class="text-overline mb-2">Detalle de la carga</div>
              <VTable density="compact" class="text-body-2">
                <tbody>
                  <tr><td>Origen</td><td>{{ load.addressOrigin || load.origin }}</td></tr>
                  <tr><td>Destino</td><td>{{ load.addressDestination || load.destination }}</td></tr>
                  <tr v-if="load.cargoDetail"><td>Carga</td><td>{{ load.cargoDetail }}</td></tr>
                  <tr v-if="load.weightKg"><td>Peso</td><td>{{ load.weightKg }} kg</td></tr>
                  <tr v-if="load.operators"><td>Operarios</td><td>{{ load.operators }}</td></tr>
                  <tr v-if="load.truckType"><td>Vehículo</td><td>{{ load.truckType }}</td></tr>
                </tbody>
              </VTable>
            </VCardText>
          </VCard>

          <VCard v-if="load.tracking" class="mt-4">
            <VCardText>
              <div class="text-overline mb-2">Seguimiento</div>
              <div class="text-body-2 mb-1">Estado: <strong>{{ OP_STATE[load.tracking.operationalState] || load.tracking.operationalState }}</strong></div>
              <div class="text-body-2 mb-1">
                {{ load.tracking.date ? new Date(load.tracking.date).toLocaleDateString('es-PE') : '—' }}
                <span v-if="load.tracking.schedule"> · {{ load.tracking.schedule }}</span>
              </div>
              <template v-if="load.tracking.assignee">
                <VDivider class="my-2" />
                <div class="text-body-2"><strong>{{ load.tracking.assignee.name }}</strong></div>
                <div class="text-body-2 text-medium-emphasis">
                  {{ load.tracking.assignee.plate }}
                  <span v-if="load.tracking.assignee.driver"> · {{ load.tracking.assignee.driver }}</span>
                </div>
              </template>
            </VCardText>
          </VCard>
        </VCol>
      </VRow>
    </template>

    <!-- Iniciar negociación -->
    <VDialog v-model="negForm.open" max-width="420">
      <VCard>
        <VCardTitle>Esperar mejores ofertas</VCardTitle>
        <VCardText>
          <p class="text-body-2 text-medium-emphasis mb-3">
            Abrimos una negociación con vos. Podés indicar cuánto te gustaría pagar.
          </p>
          <VTextField v-model="negForm.counterOffer" label="Tu propuesta (S/, opcional)" type="number" class="mb-2" />
          <VTextarea v-model="negForm.note" label="Nota (opcional)" rows="2" auto-grow />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="negForm.open = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="busy" @click="startNegotiation">Empezar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="counter.open" max-width="380">
      <VCard>
        <VCardTitle>Contraofertar</VCardTitle>
        <VCardText><VTextField v-model="counter.amount" label="Tu monto (S/)" type="number" /></VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="counter.open = false">Cancelar</VBtn>
          <VBtn color="warning" :loading="busy" :disabled="!counter.amount" @click="respond(counter.messageId, 'counter', counter.amount); counter.open = false">Enviar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </div>
</template>
