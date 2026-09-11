<script setup>
import { onMounted, reactive, ref } from 'vue'

import { carrierEarnings, carrierPayout, carrierPayoutUpdate } from '@/services/settlementsService'

const STATE = {
  pending: { label: 'Pendiente', color: 'warning' },
  confirmed: { label: 'Confirmado', color: 'info' },
  settled: { label: 'Pagado', color: 'success' },
}
const BANKS = [
  { title: 'BCP', value: 'bcp' }, { title: 'BBVA', value: 'bbva' }, { title: 'Interbank', value: 'interbank' },
  { title: 'Scotiabank', value: 'scotiabank' }, { title: 'Banco de la Nación', value: 'nacion' }, { title: 'Otro', value: 'otro' },
]
const ACCT = [{ title: 'Ahorros', value: 'ahorros' }, { title: 'Corriente', value: 'corriente' }]
const soles = n => `S/ ${Math.round(Math.abs(n)).toLocaleString('es-PE')}`

const rows = ref([])
const summary = ref(null)
const loading = ref(true)
const error = ref('')

const payout = reactive({ bank: '', accountType: '', account: '', cci: '', holder: '', yape: '' })
const payoutBusy = ref(false)
const savePayout = async () => {
  payoutBusy.value = true
  try { Object.assign(payout, await carrierPayoutUpdate({ ...payout })); notify('Datos de cobro guardados.') }
  catch (e) { notify(e.message || 'No se pudo guardar.', 'error') } finally { payoutBusy.value = false }
}
const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snackbar, { show: true, text: t, color: c })

onMounted(async () => {
  try {
    const [e, p] = await Promise.all([carrierEarnings(), carrierPayout()])
    rows.value = e.results
    summary.value = e.summary
    Object.assign(payout, p)
  } catch (err) { error.value = err.message || 'No se pudo cargar.' } finally { loading.value = false }
})
</script>

<template>
  <section>
    <h1 class="text-h5 font-weight-bold mb-1">Mis cobros</h1>
    <p class="text-body-2 text-medium-emphasis mb-4">
      Lo que Lima Express te va a pagar por los servicios que ejecutaste. Si cobraste un servicio en efectivo,
      acá figura lo que le debés a la plataforma por comisión.
    </p>

    <VAlert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</VAlert>
    <VProgressLinear v-else-if="loading" indeterminate />

    <template v-else>
      <VRow v-if="summary" class="mb-2">
        <VCol cols="12" sm="4"><VCard variant="tonal"><VCardText class="py-3">
          <div class="text-caption text-medium-emphasis">Por cobrar</div>
          <div class="text-h6 text-success">{{ soles(summary.pendingPayout) }}</div>
        </VCardText></VCard></VCol>
        <VCol cols="12" sm="4"><VCard variant="tonal"><VCardText class="py-3">
          <div class="text-caption text-medium-emphasis">Ya pagado</div>
          <div class="text-h6">{{ soles(summary.settled) }}</div>
        </VCardText></VCard></VCol>
        <VCol cols="12" sm="4"><VCard variant="tonal"><VCardText class="py-3">
          <div class="text-caption text-medium-emphasis">Debés a la plataforma</div>
          <div class="text-h6" :class="{ 'text-error': summary.youOwePlatform > 0 }">{{ soles(summary.youOwePlatform) }}</div>
        </VCardText></VCard></VCol>
      </VRow>

      <div v-if="!rows.length" class="text-center text-medium-emphasis py-10 text-body-2">
        Todavía no tenés cobros registrados.
      </div>
      <VCard v-for="r in rows" v-else :key="r.id" class="mb-2">
        <VCardText class="d-flex align-center flex-wrap ga-2">
          <div class="flex-grow-1" style="min-width: 0;">
            <div class="font-weight-medium">{{ r.serviceCode }}</div>
            <div class="text-caption text-medium-emphasis">
              {{ r.route }}
              <span v-if="r.date"> · {{ new Date(r.date).toLocaleDateString('es-PE') }}</span>
              <span v-if="r.paymentRef"> · {{ r.paymentRef }}</span>
            </div>
          </div>
          <VChip size="small" :color="STATE[r.state]?.color">{{ STATE[r.state]?.label }}</VChip>
          <span class="text-body-1 font-weight-bold" :class="r.youOwe ? 'text-error' : 'text-success'">
            {{ r.youOwe ? '-' : '' }}{{ soles(r.amount) }}
          </span>
        </VCardText>
      </VCard>

      <VCard class="mt-4">
        <VCardText>
          <div class="text-overline mb-2">Mis datos de cobro</div>
          <p class="text-body-2 text-medium-emphasis mb-3">
            A dónde te transfiere Lima Express. El CCI (20 dígitos) sirve para transferencias entre bancos.
          </p>
          <VRow dense>
            <VCol cols="12" sm="6"><VSelect v-model="payout.bank" :items="BANKS" label="Banco" density="compact" clearable /></VCol>
            <VCol cols="12" sm="6"><VSelect v-model="payout.accountType" :items="ACCT" label="Tipo de cuenta" density="compact" clearable /></VCol>
            <VCol cols="12" sm="6"><VTextField v-model="payout.account" label="N° de cuenta" density="compact" /></VCol>
            <VCol cols="12" sm="6"><VTextField v-model="payout.cci" label="CCI (20 dígitos)" density="compact" /></VCol>
            <VCol cols="12" sm="6"><VTextField v-model="payout.holder" label="Titular de la cuenta" density="compact" /></VCol>
            <VCol cols="12" sm="6"><VTextField v-model="payout.yape" label="Número Yape / Plin" density="compact" /></VCol>
          </VRow>
          <VBtn color="primary" :loading="payoutBusy" class="mt-2" @click="savePayout">Guardar</VBtn>
        </VCardText>
      </VCard>
    </template>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3000">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
