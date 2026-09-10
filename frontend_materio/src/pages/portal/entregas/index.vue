<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import {
  carrierDeliveries, carrierDeliveryEvent, carrierRoute, carrierRouteStart,
} from '@/services/shipmentsService'

const soles = n => `S/ ${Number(n || 0).toLocaleString('es-PE')}`
const snack = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snack, { show: true, text: t, color: c })

const route = ref(null)      // { code, state, total, done, delivered, stops[] }
const loose = ref([])        // envíos sueltos (sin ruta)
const loading = ref(true)
const busy = ref(false)

const load = async () => {
  loading.value = true
  try {
    const r = await carrierRoute()
    route.value = r.route
    loose.value = route.value ? [] : (await carrierDeliveries()).results
  } catch (e) { notify(e.message || 'No se pudo cargar.', 'error') } finally { loading.value = false }
}
onMounted(load)

const DONE = ['entregado', 'fallido', 'devuelto']
const pending = computed(() => (route.value?.stops || []).filter(s => !DONE.includes(s.state)))
const finished = computed(() => (route.value?.stops || []).filter(s => DONE.includes(s.state)))
const current = computed(() => pending.value[0] || null)
const progressPct = computed(() => {
  const t = route.value?.total || 0
  return t ? Math.round(((route.value.done || 0) / t) * 100) : 0
})

const mapUrl = s => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${s.dropoff.address}, ${s.dropoff.district}, Lima`)}`
const tel = p => `tel:${(p || '').replace(/[^\d+]/g, '')}`
const wa = p => `https://wa.me/${(p || '').replace(/\D/g, '')}`

const startRoute = async () => {
  busy.value = true
  try { await carrierRouteStart(); notify('¡A repartir!'); await load() }
  catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}

const step = async (s, state) => {
  busy.value = true
  try { await carrierDeliveryEvent(s.code, { state }); await load() }
  catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}

// --- POD (entrega) ---
const pod = reactive({ open: false, stop: null, receivedBy: '', photo: null, photoUrl: '', codAmount: '', codMethod: 'efectivo' })
const openPod = s => Object.assign(pod, {
  open: true, stop: s, receivedBy: '', photo: null, photoUrl: '',
  codAmount: s.cod ? String(s.codAmount) : '', codMethod: 'efectivo',
})
const onPhoto = e => {
  const f = e.target.files?.[0]
  if (!f) return
  pod.photo = f
  pod.photoUrl = URL.createObjectURL(f)
}
const submitPod = async () => {
  if (pod.stop.cod && !pod.codAmount) { notify('Registrá cuánto cobraste.', 'error'); return }
  busy.value = true
  try {
    const fd = new FormData()
    fd.append('state', 'entregado')
    fd.append('receivedBy', pod.receivedBy || '')
    if (pod.photo) fd.append('photo', pod.photo)
    if (pod.stop.cod) {
      fd.append('codCollected', pod.codAmount)
      fd.append('codMethod', pod.codMethod)
    }
    await carrierDeliveryEvent(pod.stop.code, fd)
    pod.open = false
    notify('Entregado ✓')
    await load()
  } catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}

// --- no entregado ---
const fail = reactive({ open: false, stop: null, reason: '' })
const openFail = s => Object.assign(fail, { open: true, stop: s, reason: '' })
const submitFail = async () => {
  busy.value = true
  try {
    await carrierDeliveryEvent(fail.stop.code, { state: 'fallido', failReason: fail.reason })
    fail.open = false
    notify('Registrado.')
    await load()
  } catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}
</script>

<template>
  <section class="pb-8">
    <h1 class="text-h5 font-weight-bold mb-3">Mi reparto</h1>

    <VProgressLinear v-if="loading" indeterminate />

    <!-- Sin ruta: entregas sueltas -->
    <template v-else-if="!route">
      <div v-if="!loose.length" class="text-center text-medium-emphasis py-12 text-body-2">
        No tenés reparto asignado para hoy.
      </div>
      <VCard v-for="s in loose" :key="s.code" class="mb-3">
        <VCardText>
          <div class="d-flex align-center ga-2 mb-2">
            <span class="font-weight-medium">{{ s.code }}</span>
            <VChip v-if="s.cod" size="x-small" color="warning">Cobrar {{ soles(s.codAmount) }}</VChip>
          </div>
          <div class="text-body-2"><strong>Recojo:</strong> {{ s.pickup.district }} · {{ s.pickup.address }}</div>
          <div class="text-body-2"><strong>Entrega:</strong> {{ s.dropoff.district }} · {{ s.dropoff.address }}</div>
        </VCardText>
        <VCardActions class="px-4 pb-3">
          <VBtn size="small" color="primary" :loading="busy" @click="step(s, 'recogido')">Recogí el paquete</VBtn>
        </VCardActions>
      </VCard>
    </template>

    <template v-else>
      <!-- Barra de progreso de la ruta -->
      <VCard class="mb-4" variant="tonal">
        <VCardText class="py-3">
          <div class="d-flex justify-space-between text-body-2 mb-1">
            <span class="font-weight-medium">Ruta {{ route.code }}</span>
            <span>{{ route.done }} / {{ route.total }} · {{ route.delivered }} entregadas</span>
          </div>
          <VProgressLinear :model-value="progressPct" height="8" rounded color="success" />
        </VCardText>
      </VCard>

      <!-- Aún no iniciada -->
      <VCard v-if="route.state === 'planificada'" class="text-center pa-6">
        <VIcon icon="ri-route-line" size="48" class="mb-2 text-medium-emphasis" />
        <div class="text-body-1 mb-1">{{ route.total }} entregas listas para hoy.</div>
        <div class="text-body-2 text-medium-emphasis mb-4">Empezá cuando tengas los paquetes contigo.</div>
        <VBtn size="large" color="primary" block :loading="busy" @click="startRoute">Empezar reparto</VBtn>
      </VCard>

      <template v-else>
        <!-- PARADA ACTUAL -->
        <VCard v-if="current" class="mb-4" elevation="4">
          <VCardText>
            <div class="d-flex align-center ga-2 mb-2">
              <VChip color="primary" size="small">Parada {{ current.order }} de {{ route.total }}</VChip>
              <VChip v-if="current.cod" color="warning" size="small">Cobrar {{ soles(current.codAmount) }}</VChip>
              <VChip v-if="current.attempts" color="error" size="small" variant="tonal">Intento {{ current.attempts + 1 }}</VChip>
            </div>
            <div class="text-h6 font-weight-bold">{{ current.dropoff.address }}</div>
            <div class="text-body-1">{{ current.dropoff.district }}</div>
            <div v-if="current.dropoff.reference" class="text-body-2 text-medium-emphasis mt-1">
              Ref: {{ current.dropoff.reference }}
            </div>
            <div class="text-body-2 mt-2">
              {{ current.dropoff.contact }} · {{ current.package }}<span v-if="current.weightKg"> · {{ current.weightKg }} kg</span>
            </div>

            <div class="d-flex ga-2 mt-3">
              <VBtn :href="mapUrl(current)" target="_blank" variant="tonal" size="small" prepend-icon="ri-map-pin-line">Mapa</VBtn>
              <VBtn :href="tel(current.dropoff.phone)" variant="tonal" size="small" prepend-icon="ri-phone-line">Llamar</VBtn>
              <VBtn :href="wa(current.dropoff.phone)" target="_blank" variant="tonal" size="small" prepend-icon="ri-whatsapp-line">WhatsApp</VBtn>
            </div>
          </VCardText>
          <VDivider />
          <div class="d-flex flex-column ga-2 pa-3">
            <VBtn size="large" color="success" block :loading="busy" @click="openPod(current)">Entregué</VBtn>
            <VBtn size="small" variant="text" color="error" :loading="busy" @click="openFail(current)">No pude entregar</VBtn>
          </div>
        </VCard>

        <VAlert v-else type="success" variant="tonal" class="mb-4">Terminaste el reparto. ¡Bien ahí!</VAlert>

        <!-- Próximas -->
        <div v-if="pending.length > 1" class="text-overline mb-1">Siguientes ({{ pending.length - 1 }})</div>
        <VList v-if="pending.length > 1" density="compact" class="mb-4 rounded border">
          <VListItem v-for="s in pending.slice(1)" :key="s.code">
            <template #prepend><VAvatar size="24" color="grey-lighten-2" class="text-caption">{{ s.order }}</VAvatar></template>
            <VListItemTitle class="text-body-2">{{ s.dropoff.district }} · {{ s.dropoff.address }}</VListItemTitle>
            <VListItemSubtitle>{{ s.dropoff.contact }}</VListItemSubtitle>
          </VListItem>
        </VList>

        <!-- Hechas -->
        <VExpansionPanels v-if="finished.length" variant="accordion">
          <VExpansionPanel :title="`Hechas (${finished.length})`">
            <template #text>
              <VList density="compact">
                <VListItem v-for="s in finished" :key="s.code">
                  <template #prepend>
                    <VIcon :icon="s.state === 'entregado' ? 'ri-check-line' : 'ri-close-line'"
                      :color="s.state === 'entregado' ? 'success' : 'error'" />
                  </template>
                  <VListItemTitle class="text-body-2">{{ s.code }} · {{ s.dropoff.district }}</VListItemTitle>
                </VListItem>
              </VList>
            </template>
          </VExpansionPanel>
        </VExpansionPanels>
      </template>
    </template>

    <!-- Bottom sheet: prueba de entrega -->
    <VDialog v-model="pod.open" max-width="420">
      <VCard>
        <VCardTitle>Confirmar entrega</VCardTitle>
        <VCardText>
          <VAlert v-if="pod.stop?.cod" type="warning" variant="tonal" class="mb-3">
            <div class="text-body-1 font-weight-bold">Cobrá {{ soles(pod.stop.codAmount) }}</div>
            <div class="text-caption">antes de entregar el paquete</div>
          </VAlert>
          <template v-if="pod.stop?.cod">
            <VTextField v-model="pod.codAmount" label="¿Cuánto cobraste? (S/)" type="number" density="compact" class="mb-2" />
            <VBtnToggle v-model="pod.codMethod" mandatory density="compact" class="mb-3" divided>
              <VBtn value="efectivo" size="small">Efectivo</VBtn>
              <VBtn value="yape" size="small">Yape / Plin</VBtn>
              <VBtn value="tarjeta" size="small">Tarjeta</VBtn>
            </VBtnToggle>
          </template>
          <label class="d-block mb-3">
            <input type="file" accept="image/*" capture="environment" class="d-none" @change="onPhoto">
            <VCard variant="outlined" class="d-flex align-center justify-center" style="height: 140px; cursor: pointer;">
              <img v-if="pod.photoUrl" :src="pod.photoUrl" style="max-height: 138px; object-fit: cover;">
              <div v-else class="text-center text-medium-emphasis">
                <VIcon icon="ri-camera-line" size="32" /><div class="text-caption">Tomar foto del paquete / lugar</div>
              </div>
            </VCard>
          </label>
          <VTextField v-model="pod.receivedBy" label="¿Quién recibió?" density="compact" />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="pod.open = false">Cancelar</VBtn>
          <VBtn color="success" :loading="busy" @click="submitPod">Confirmar entrega</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="fail.open" max-width="380">
      <VCard>
        <VCardTitle>No se pudo entregar</VCardTitle>
        <VCardText>
          <VSelect
            v-model="fail.reason" label="Motivo" density="compact"
            :items="['Nadie en casa', 'Dirección incorrecta', 'Cliente rechazó', 'Zona peligrosa', 'No contesta', 'Otro']"
          />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="fail.open = false">Cancelar</VBtn>
          <VBtn color="error" :loading="busy" :disabled="!fail.reason" @click="submitFail">Registrar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snack.show" :color="snack.color" timeout="2500">{{ snack.text }}</VSnackbar>
  </section>
</template>
