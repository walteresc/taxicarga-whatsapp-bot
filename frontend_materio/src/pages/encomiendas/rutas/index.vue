<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { carriersService } from '@/services/carriersService'
import {
  routeClose, routeCreate, routeDetail, routeList, routeStart, routeStops, shipmentList,
} from '@/services/shipmentsService'

const RSTATE = {
  planificada: { label: 'Planificada', color: 'default' },
  en_curso: { label: 'En curso', color: 'warning' },
  cerrada: { label: 'Cerrada', color: 'success' },
}
const snack = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snack, { show: true, text: t, color: c })
const soles = n => `S/ ${Number(n || 0).toLocaleString('es-PE')}`

const routes = ref([])
const loading = ref(true)
const busy = ref(false)

const load = async () => {
  loading.value = true
  try { routes.value = (await routeList()).results }
  catch (e) { notify(e.message || 'No se pudo cargar.', 'error') } finally { loading.value = false }
}
onMounted(load)

// --- nueva ruta ---
const form = reactive({ open: false, carrier: null, date: '', picked: [] })
const carrierOpts = ref([])
const unassigned = ref([])
const searchCarriers = async q => {
  carrierOpts.value = (await carriersService.list({ search: q || undefined, status: 'active', pageSize: 20 })).results
}
const openNew = async () => {
  Object.assign(form, { open: true, carrier: null, date: new Date().toISOString().slice(0, 10), picked: [] })
  searchCarriers('')
  try {
    const [a, b] = await Promise.all([
      shipmentList({ state: 'registrado', open: 'true' }), shipmentList({ state: 'asignado' }),
    ])
    unassigned.value = [...a.results, ...b.results]
  } catch { unassigned.value = [] }
}
const submitNew = async () => {
  busy.value = true
  try {
    const r = await routeCreate({
      carrierId: form.carrier.id, date: form.date, shipments: form.picked,
    })
    form.open = false
    notify(`Ruta ${r.code} creada con ${r.total} paradas.`)
    await load()
    openDetail(r.code)
  } catch (e) { notify(e.message || 'No se pudo crear.', 'error') } finally { busy.value = false }
}

// --- detalle ---
const detail = ref(null)
const openDetail = async code => { detail.value = null; try { detail.value = await routeDetail(code) } catch (e) { notify(e.message, 'error') } }
const doStart = async () => { busy.value = true; try { detail.value = await routeStart(detail.value.code); notify('Ruta iniciada.'); await load() } catch (e) { notify(e.message, 'error') } finally { busy.value = false } }
const doClose = async () => {
  if (!confirm('¿Cerrar la ruta? Los envíos sin entregar quedarán como devueltos.')) return
  busy.value = true
  try { detail.value = await routeClose(detail.value.code); notify('Ruta cerrada.'); await load() }
  catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}
const removeStop = async code => {
  busy.value = true
  try { detail.value = await routeStops(detail.value.code, { remove: [code] }); await load() }
  catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}

const STATE_LABEL = {
  registrado: 'Registrado', asignado: 'Asignado', recogido: 'Recogido', en_ruta: 'En ruta',
  entregado: 'Entregado', fallido: 'No entregado', devuelto: 'Devuelto',
}
</script>

<template>
  <section>
    <div class="d-flex align-center flex-wrap ga-2 mb-1">
      <h1 class="text-h4 font-weight-bold">Rutas de reparto</h1>
      <VSpacer />
      <VBtn color="primary" prepend-icon="ri-add-line" @click="openNew">Nueva ruta</VBtn>
    </div>
    <p class="text-body-2 text-medium-emphasis mb-4">
      Agrupá envíos en una ruta para un motorizado. Se ordenan por zona; el motorizado la ve en su portal.
    </p>

    <VRow>
      <VCol cols="12" md="5">
        <VProgressLinear v-if="loading" indeterminate />
        <div v-else-if="!routes.length" class="text-center text-medium-emphasis py-10 text-body-2">Sin rutas.</div>
        <VCard v-else>
          <VList density="compact" lines="two">
            <VListItem v-for="r in routes" :key="r.code" :active="detail?.code === r.code" @click="openDetail(r.code)">
              <VListItemTitle class="d-flex align-center ga-2">
                <span class="font-weight-medium">{{ r.code }}</span>
                <VChip size="x-small" :color="RSTATE[r.state]?.color">{{ RSTATE[r.state]?.label }}</VChip>
              </VListItemTitle>
              <VListItemSubtitle>
                {{ new Date(r.date).toLocaleDateString('es-PE') }} · {{ r.carrierName }} ·
                {{ r.done }}/{{ r.total }} ({{ r.delivered }} entregadas)
              </VListItemSubtitle>
            </VListItem>
          </VList>
        </VCard>
      </VCol>

      <VCol cols="12" md="7">
        <VCard v-if="!detail" class="d-flex align-center justify-center" style="min-height: 40vh;">
          <span class="text-medium-emphasis">Elegí una ruta.</span>
        </VCard>
        <VCard v-else>
          <VCardText class="d-flex align-center flex-wrap ga-2">
            <span class="text-h6">{{ detail.code }}</span>
            <VChip size="small" :color="RSTATE[detail.state]?.color">{{ RSTATE[detail.state]?.label }}</VChip>
            <span class="text-body-2 text-medium-emphasis">{{ detail.carrierName }} · {{ new Date(detail.date).toLocaleDateString('es-PE') }}</span>
            <VSpacer />
            <VBtn v-if="detail.state === 'planificada'" size="small" color="primary" :loading="busy" @click="doStart">Iniciar</VBtn>
            <VBtn v-if="detail.state === 'en_curso'" size="small" variant="tonal" color="error" :loading="busy" @click="doClose">Cerrar</VBtn>
          </VCardText>
          <VDivider />
          <VTable density="compact" class="text-body-2">
            <thead><tr><th style="width: 40px;">#</th><th>Entrega</th><th>Destinatario</th><th>Estado</th><th></th></tr></thead>
            <tbody>
              <tr v-for="s in detail.stops" :key="s.code">
                <td>{{ s.order }}</td>
                <td>
                  <div>{{ s.district }}</div>
                  <div class="text-caption text-medium-emphasis">{{ s.address }}</div>
                </td>
                <td>{{ s.recipient }}<VChip v-if="s.cod" size="x-small" color="warning" class="ms-1">COD</VChip></td>
                <td><VChip size="x-small">{{ STATE_LABEL[s.state] || s.state }}</VChip></td>
                <td class="text-right">
                  <VBtn v-if="detail.state === 'planificada'" icon="ri-close-line" size="x-small" variant="text" @click="removeStop(s.code)" />
                </td>
              </tr>
            </tbody>
          </VTable>
        </VCard>
      </VCol>
    </VRow>

    <VDialog v-model="form.open" max-width="560" scrollable>
      <VCard>
        <VCardTitle>Nueva ruta</VCardTitle>
        <VCardText>
          <VAutocomplete
            v-model="form.carrier" label="Motorizado" density="compact" class="mb-2"
            :items="carrierOpts" item-title="name" return-object @update:search="searchCarriers"
          />
          <VTextField v-model="form.date" label="Fecha" type="date" density="compact" class="mb-3" />
          <div class="text-overline mb-1">Envíos a incluir ({{ form.picked.length }})</div>
          <div v-if="!unassigned.length" class="text-body-2 text-medium-emphasis">No hay envíos sin rutear.</div>
          <VList v-else density="compact" class="border rounded" style="max-height: 40vh; overflow-y: auto;">
            <VListItem v-for="s in unassigned" :key="s.code">
              <template #prepend>
                <VCheckboxBtn v-model="form.picked" :value="s.code" density="compact" />
              </template>
              <VListItemTitle class="text-body-2">{{ s.code }} · {{ s.route }}</VListItemTitle>
              <VListItemSubtitle>{{ s.recipient }} · {{ soles(s.price) }}</VListItemSubtitle>
            </VListItem>
          </VList>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="form.open = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="busy" :disabled="!form.carrier || !form.date || !form.picked.length" @click="submitNew">Crear ruta</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snack.show" :color="snack.color" timeout="3000">{{ snack.text }}</VSnackbar>
  </section>
</template>
