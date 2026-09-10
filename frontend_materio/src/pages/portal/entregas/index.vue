<script setup>
import { onMounted, reactive, ref } from 'vue'

import { carrierDeliveries, carrierDeliveryEvent } from '@/services/shipmentsService'

const NEXT = {
  asignado: [['recogido', 'Recogí el paquete', 'primary']],
  recogido: [['en_ruta', 'Salí a entregar', 'primary']],
  en_ruta: [['entregado', 'Entregado', 'success'], ['fallido', 'No pude entregar', 'error']],
}
const STATE = { asignado: 'Por recoger', recogido: 'Recogido', en_ruta: 'En ruta', entregado: 'Entregado', fallido: 'No entregado' }
const soles = n => `S/ ${Number(n || 0).toLocaleString('es-PE')}`

const rows = ref([])
const loading = ref(true)
const busy = ref(false)
const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snackbar, { show: true, text: t, color: c })

const load = async () => {
  loading.value = true
  try { rows.value = (await carrierDeliveries()).results }
  catch (e) { notify(e.message || 'No se pudo cargar.', 'error') } finally { loading.value = false }
}
onMounted(load)

const mark = async (row, state) => {
  let body = { state }
  if (state === 'entregado') {
    const receivedBy = prompt('¿Quién recibió el paquete?')
    if (receivedBy == null) return
    body.receivedBy = receivedBy
  }
  if (state === 'fallido') {
    const failReason = prompt('¿Por qué no se pudo entregar?')
    if (failReason == null) return
    body.failReason = failReason
  }
  busy.value = true
  try { await carrierDeliveryEvent(row.code, body); notify('Listo.'); await load() }
  catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}
const wa = phone => `https://wa.me/${(phone || '').replace(/\D/g, '')}`
</script>

<template>
  <section>
    <h1 class="text-h5 font-weight-bold mb-1">Mis entregas</h1>
    <p class="text-body-2 text-medium-emphasis mb-4">Paquetes asignados a vos. Marcá cada paso a medida que avanzás.</p>

    <VProgressLinear v-if="loading" indeterminate />
    <div v-else-if="!rows.length" class="text-center text-medium-emphasis py-10 text-body-2">No tenés entregas asignadas.</div>

    <VCard v-for="r in rows" :key="r.code" class="mb-3">
      <VCardText>
        <div class="d-flex align-center ga-2 mb-2">
          <span class="font-weight-medium">{{ r.code }}</span>
          <VChip size="x-small">{{ STATE[r.state] || r.state }}</VChip>
          <VChip v-if="r.cod" size="x-small" color="warning">Cobrar {{ soles(r.codAmount) }}</VChip>
        </div>
        <VRow dense class="text-body-2">
          <VCol cols="12" sm="6">
            <div class="text-overline">Recojo</div>
            <div>{{ r.pickup.district }} · {{ r.pickup.address }}</div>
            <div v-if="r.pickup.reference" class="text-caption text-medium-emphasis">{{ r.pickup.reference }}</div>
            <div class="text-caption">{{ r.pickup.contact }} <a v-if="r.pickup.phone" :href="wa(r.pickup.phone)" target="_blank">{{ r.pickup.phone }}</a></div>
          </VCol>
          <VCol cols="12" sm="6">
            <div class="text-overline">Entrega</div>
            <div>{{ r.dropoff.district }} · {{ r.dropoff.address }}</div>
            <div v-if="r.dropoff.reference" class="text-caption text-medium-emphasis">{{ r.dropoff.reference }}</div>
            <div class="text-caption">{{ r.dropoff.contact }} <a v-if="r.dropoff.phone" :href="wa(r.dropoff.phone)" target="_blank">{{ r.dropoff.phone }}</a></div>
          </VCol>
        </VRow>
        <div v-if="r.package" class="text-caption text-medium-emphasis mt-1">Paquete: {{ r.package }}</div>
      </VCardText>
      <VCardActions v-if="NEXT[r.state]" class="px-4 pb-3 ga-2 flex-wrap">
        <VBtn v-for="[st, label, color] in NEXT[r.state]" :key="st" :color="color"
          size="small" :variant="color === 'error' ? 'tonal' : 'flat'" :loading="busy" @click="mark(r, st)">
          {{ label }}
        </VBtn>
      </VCardActions>
    </VCard>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="2500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
