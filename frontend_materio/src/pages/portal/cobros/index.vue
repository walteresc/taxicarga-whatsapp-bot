<script setup>
import { onMounted, ref } from 'vue'

import { carrierEarnings } from '@/services/settlementsService'

const STATE = {
  pending: { label: 'Pendiente', color: 'warning' },
  confirmed: { label: 'Confirmado', color: 'info' },
  settled: { label: 'Pagado', color: 'success' },
}
const soles = n => `S/ ${Math.round(Math.abs(n)).toLocaleString('es-PE')}`

const rows = ref([])
const summary = ref(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    const r = await carrierEarnings()
    rows.value = r.results
    summary.value = r.summary
  } catch (e) { error.value = e.message || 'No se pudo cargar.' } finally { loading.value = false }
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

      <VCard>
        <div v-if="!rows.length" class="text-center text-medium-emphasis py-10 text-body-2">
          Todavía no tenés cobros registrados.
        </div>
        <VTable v-else density="comfortable">
          <thead>
            <tr><th>Servicio</th><th>Fecha</th><th class="text-right">Monto</th><th>Estado</th><th>Referencia</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.id">
              <td>
                <div class="font-weight-medium">{{ r.serviceCode }}</div>
                <div class="text-caption text-medium-emphasis">{{ r.route }}</div>
              </td>
              <td>{{ r.date ? new Date(r.date).toLocaleDateString('es-PE') : '—' }}</td>
              <td class="text-right font-weight-medium" :class="r.youOwe ? 'text-error' : 'text-success'">
                {{ r.youOwe ? '-' : '' }}{{ soles(r.amount) }}
              </td>
              <td><VChip size="small" :color="STATE[r.state]?.color">{{ STATE[r.state]?.label }}</VChip></td>
              <td class="text-caption">{{ r.paymentRef || '—' }}</td>
            </tr>
          </tbody>
        </VTable>
      </VCard>
    </template>
  </section>
</template>
