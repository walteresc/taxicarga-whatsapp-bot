<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import {
  codPending, codRemit, codSettlementCreate, codSettlementDetail,
  codSettlementReconcile, codSettlements, codToRemit,
} from '@/services/shipmentsService'

const soles = n => `S/ ${Number(n || 0).toLocaleString('es-PE', { minimumFractionDigits: 2 })}`
const snack = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snack, { show: true, text: t, color: c })

const tab = ref('rendir')
const busy = ref(false)
const loading = ref(true)

const pending = ref([])       // por rendir, agrupado por motorizado
const remit = ref([])         // por remitir, agrupado por remitente
const settlements = ref([])   // rendiciones

const load = async () => {
  loading.value = true
  try {
    const [p, r, s] = await Promise.all([codPending(), codToRemit(), codSettlements()])
    pending.value = p.groups
    remit.value = r.groups
    settlements.value = s.results
  } catch (e) { notify(e.message || 'No se pudo cargar.', 'error') } finally { loading.value = false }
}
onMounted(load)

// --- rendición ---
const detail = ref(null)
const openSettlement = async code => { detail.value = null; try { detail.value = await codSettlementDetail(code) } catch (e) { notify(e.message, 'error') } }
const createSettlement = async g => {
  busy.value = true
  try {
    const r = await codSettlementCreate({ carrierId: g.carrierId })
    notify(`Rendición ${r.code} creada.`)
    await load()
    openSettlement(r.code)
  } catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}
const recForm = reactive({ open: false, amount: '', reference: '', note: '' })
const openRec = () => Object.assign(recForm, { open: true, amount: String(detail.value.expected), reference: '', note: '' })
const doReconcile = async () => {
  busy.value = true
  try {
    await codSettlementReconcile(detail.value.code, { amount: recForm.amount, reference: recForm.reference, note: recForm.note })
    recForm.open = false
    notify('Rendición conciliada.')
    detail.value = await codSettlementDetail(detail.value.code)
    await load()
  } catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}

// --- remitir al remitente ---
const doRemit = async g => {
  if (!confirm(`¿Marcar como remitidos ${soles(g.total)} a ${g.sender}?`)) return
  busy.value = true
  try {
    const ref = prompt('Referencia del pago:') || ''
    await codRemit({ shipmentCodes: g.shipments.map(s => s.code), reference: ref })
    notify('Remitido.')
    await load()
  } catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}

const totalPending = computed(() => pending.value.reduce((a, g) => a + g.total, 0))
const totalRemit = computed(() => remit.value.reduce((a, g) => a + g.total, 0))
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">Contra-entrega (COD)</h1>
    <p class="text-body-2 text-medium-emphasis mb-4" style="max-width: 70ch;">
      Plata que los motorizados cobran al entregar. Primero la <strong>rinden</strong> a la plataforma;
      después la plataforma <strong>remite</strong> a cada remitente su parte (neto de envío y comisión).
    </p>

    <VRow class="mb-2">
      <VCol cols="6" md="3"><VCard variant="tonal"><VCardText class="py-3">
        <div class="text-caption text-medium-emphasis">Por rendir (motorizados)</div>
        <div class="text-h6">{{ soles(totalPending) }}</div>
      </VCardText></VCard></VCol>
      <VCol cols="6" md="3"><VCard variant="tonal"><VCardText class="py-3">
        <div class="text-caption text-medium-emphasis">Por remitir (remitentes)</div>
        <div class="text-h6">{{ soles(totalRemit) }}</div>
      </VCardText></VCard></VCol>
    </VRow>

    <VTabs v-model="tab" class="mb-3">
      <VTab value="rendir">Por rendir</VTab>
      <VTab value="remitir">Por remitir</VTab>
      <VTab value="historial">Rendiciones</VTab>
    </VTabs>

    <VProgressLinear v-if="loading" indeterminate />

    <!-- POR RENDIR -->
    <VWindow v-else v-model="tab">
      <VWindowItem value="rendir">
        <VRow>
          <VCol cols="12" md="6">
            <div v-if="!pending.length" class="text-medium-emphasis text-body-2 py-6 text-center">Nada por rendir.</div>
            <VCard v-for="g in pending" :key="g.carrierId" class="mb-2">
              <VCardText class="d-flex align-center flex-wrap ga-2">
                <div>
                  <div class="font-weight-medium">{{ g.carrierName }}</div>
                  <div class="text-caption text-medium-emphasis">{{ g.count }} entrega(s) · {{ soles(g.total) }}</div>
                </div>
                <VSpacer />
                <VBtn size="small" color="primary" :loading="busy" @click="createSettlement(g)">Crear rendición</VBtn>
              </VCardText>
            </VCard>
          </VCol>
          <VCol cols="12" md="6">
            <VCard v-if="detail">
              <VCardText class="d-flex align-center flex-wrap ga-2">
                <span class="text-h6">{{ detail.code }}</span>
                <VChip size="small" :color="detail.state === 'conciliada' ? 'success' : 'warning'">
                  {{ detail.state === 'conciliada' ? 'Conciliada' : 'Pendiente' }}
                </VChip>
                <VSpacer />
                <VBtn v-if="detail.state !== 'conciliada'" size="small" color="success" @click="openRec">Conciliar</VBtn>
              </VCardText>
              <VCardText class="pt-0">
                <div class="text-body-2 mb-2">
                  {{ detail.carrierName }} · esperado <strong>{{ soles(detail.expected) }}</strong>
                  <span v-if="detail.state === 'conciliada'">
                    · entregó {{ soles(detail.handedOver) }}
                    <span :class="detail.difference != 0 ? 'text-error' : 'text-success'">
                      ({{ detail.difference > 0 ? '+' : '' }}{{ soles(detail.difference) }})
                    </span>
                  </span>
                </div>
                <VTable density="compact" class="text-body-2">
                  <tbody>
                    <tr v-for="s in detail.shipments" :key="s.code">
                      <td>{{ s.code }}</td><td>{{ s.recipient }}</td>
                      <td class="text-capitalize">{{ s.method }}</td>
                      <td class="text-right">{{ soles(s.amount) }}</td>
                    </tr>
                  </tbody>
                </VTable>
              </VCardText>
            </VCard>
          </VCol>
        </VRow>
      </VWindowItem>

      <!-- POR REMITIR -->
      <VWindowItem value="remitir">
        <div v-if="!remit.length" class="text-medium-emphasis text-body-2 py-6 text-center">Nada por remitir.</div>
        <VCard v-for="g in remit" :key="g.sender" class="mb-2">
          <VCardText class="d-flex align-center flex-wrap ga-2">
            <div>
              <div class="font-weight-medium">{{ g.sender }}</div>
              <div class="text-caption text-medium-emphasis">{{ g.count }} envío(s) · {{ g.phone }}</div>
            </div>
            <VSpacer />
            <span class="text-h6">{{ soles(g.total) }}</span>
            <VBtn size="small" color="primary" :loading="busy" @click="doRemit(g)">Marcar remitido</VBtn>
          </VCardText>
        </VCard>
      </VWindowItem>

      <!-- HISTORIAL -->
      <VWindowItem value="historial">
        <VCard>
          <VTable density="compact" class="text-body-2">
            <thead><tr><th>Código</th><th>Motorizado</th><th class="text-right">Esperado</th><th class="text-right">Entregado</th><th class="text-right">Dif.</th><th>Estado</th></tr></thead>
            <tbody>
              <tr v-for="r in settlements" :key="r.code" style="cursor: pointer;" @click="tab = 'rendir'; openSettlement(r.code)">
                <td>{{ r.code }}</td><td>{{ r.carrierName }}</td>
                <td class="text-right">{{ soles(r.expected) }}</td>
                <td class="text-right">{{ r.handedOver != null ? soles(r.handedOver) : '—' }}</td>
                <td class="text-right" :class="r.difference ? 'text-error' : ''">{{ r.difference ? soles(r.difference) : '—' }}</td>
                <td><VChip size="x-small" :color="r.state === 'conciliada' ? 'success' : 'warning'">{{ r.state }}</VChip></td>
              </tr>
            </tbody>
          </VTable>
        </VCard>
      </VWindowItem>
    </VWindow>

    <VDialog v-model="recForm.open" max-width="400">
      <VCard>
        <VCardTitle>Conciliar rendición</VCardTitle>
        <VCardText>
          <p class="text-body-2 mb-3">Esperado: <strong>{{ soles(detail?.expected) }}</strong></p>
          <VTextField v-model="recForm.amount" label="¿Cuánto entregó el motorizado? (S/)" type="number" density="compact" class="mb-2" />
          <VTextField v-model="recForm.reference" label="Referencia (depósito, Yape…)" density="compact" class="mb-2" />
          <VTextField v-model="recForm.note" label="Nota (si hay diferencia)" density="compact" />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="recForm.open = false">Cancelar</VBtn>
          <VBtn color="success" :loading="busy" @click="doReconcile">Conciliar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snack.show" :color="snack.color" timeout="3000">{{ snack.text }}</VSnackbar>
  </section>
</template>
