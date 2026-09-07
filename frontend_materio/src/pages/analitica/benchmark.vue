<script setup>
import { onMounted, ref } from 'vue'

import { fetchBenchmark } from '@/services/reportsService'

const data = ref(null)
const loading = ref(true)
const error = ref('')

const soles = n => `S/ ${Math.round(n || 0).toLocaleString('es-PE')}`
const num = n => (n || 0).toLocaleString('es-PE')

onMounted(async () => {
  try {
    data.value = await fetchBenchmark()
  } catch (e) {
    error.value = e.message || 'No se pudo cargar el reporte.'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">
      Benchmark histórico
    </h1>
    <p class="text-body-1 text-medium-emphasis mb-6">
      Servicios importados (hoja «wally»). No crece con la operación, no es atribuible a asesor ni canal.
    </p>

    <VProgressLinear v-if="loading" indeterminate color="primary" class="mb-4" />
    <VAlert v-else-if="error" type="error" variant="tonal">
      {{ error }}
    </VAlert>

    <template v-else-if="data">
      <VRow class="match-height mb-2">
        <VCol cols="12" sm="6" md="3">
          <StatCard
            title="Servicios totales" :value="num(data.total)" icon="ri-database-2-line" color="primary"
            :subtitle="`${data.dateMin} → ${data.dateMax}`"
          />
        </VCol>
        <VCol cols="12" sm="6" md="3">
          <StatCard title="Cerrados con precio" :value="num(data.closed)" icon="ri-checkbox-circle-line" color="success" />
        </VCol>
        <VCol cols="12" sm="6" md="3">
          <StatCard
            title="Precio mediano" :value="soles(data.price.all.median)" icon="ri-price-tag-3-line" color="info"
            :subtitle="`p25 ${data.price.all.p25} · p75 ${data.price.all.p75} · p90 ${data.price.all.p90}`"
          />
        </VCol>
        <VCol cols="12" sm="6" md="3">
          <StatCard
            title="Interprovincial" :value="`${data.scope.interprovincial.servicesPct}%`" icon="ri-truck-line" color="warning"
            :subtitle="`${data.scope.interprovincial.revenuePct}% de la facturación`"
          />
        </VCol>
      </VRow>

      <VRow class="match-height mb-2">
        <VCol cols="12" md="6">
          <VCard>
            <VCardItem>
              <template #prepend><VIcon icon="ri-calendar-line" class="text-medium-emphasis" /></template>
              <VCardTitle>Volumen por año</VCardTitle>
            </VCardItem>
            <VDivider />
            <VTable density="comfortable">
              <thead><tr><th>Año</th><th class="text-right">Servicios</th><th class="text-right">Cerrados</th></tr></thead>
              <tbody>
                <tr v-for="r in data.byYear" :key="r.date">
                  <td class="font-weight-medium">{{ new Date(r.date).getFullYear() }}</td>
                  <td class="text-right">{{ num(r.count) }}</td>
                  <td class="text-right">{{ num(r.closed) }}</td>
                </tr>
              </tbody>
            </VTable>
          </VCard>
        </VCol>
        <VCol cols="12" md="6">
          <VCard>
            <VCardItem>
              <template #prepend><VIcon icon="ri-pie-chart-2-line" class="text-medium-emphasis" /></template>
              <VCardTitle>Mix por tipo</VCardTitle>
            </VCardItem>
            <VDivider />
            <VTable density="comfortable">
              <thead><tr><th>Tipo</th><th class="text-right">Servicios</th><th class="text-right">%</th></tr></thead>
              <tbody>
                <tr v-for="r in data.byType" :key="r.type">
                  <td class="text-capitalize">{{ r.type || '—' }}</td>
                  <td class="text-right">{{ num(r.count) }}</td>
                  <td class="text-right">
                    <VChip size="x-small" color="primary" variant="tonal">{{ r.pct }}%</VChip>
                  </td>
                </tr>
              </tbody>
            </VTable>
          </VCard>
        </VCol>
      </VRow>

      <VCard class="mb-6">
        <VCardItem><VCardTitle>Local vs interprovincial (servicios cerrados)</VCardTitle></VCardItem>
        <VDivider />
        <VTable density="comfortable">
          <thead><tr>
            <th>Ámbito</th><th class="text-right">Servicios</th><th class="text-right">% serv.</th>
            <th class="text-right">Ticket prom.</th><th class="text-right">Mediana</th>
            <th class="text-right">Facturación</th><th class="text-right">% fact.</th>
          </tr></thead>
          <tbody>
            <tr v-for="(v, k) in { 'Local (Lima)': data.scope.local, 'Interprovincial': data.scope.interprovincial }" :key="k">
              <td class="font-weight-medium">{{ k }}</td>
              <td class="text-right">{{ num(v.count) }}</td>
              <td class="text-right">{{ v.servicesPct }}%</td>
              <td class="text-right">{{ soles(v.averageTicket) }}</td>
              <td class="text-right">{{ soles(v.median) }}</td>
              <td class="text-right">{{ soles(v.revenue) }}</td>
              <td class="text-right">{{ v.revenuePct }}%</td>
            </tr>
          </tbody>
        </VTable>
      </VCard>

      <VCard>
        <VCardItem>
          <VCardTitle>Rutas interprovinciales frecuentes</VCardTitle>
          <VCardSubtitle>≥ 3 servicios — tarifa típica</VCardSubtitle>
        </VCardItem>
        <VDivider />
        <VTable density="comfortable">
          <thead><tr>
            <th>Ruta</th><th class="text-right">Casos</th><th class="text-right">Precio típico</th>
            <th class="text-right">Mín</th><th class="text-right">Máx</th>
          </tr></thead>
          <tbody>
            <tr v-for="r in data.interprovincialRoutes" :key="r.route">
              <td class="font-weight-medium">{{ r.route }}</td>
              <td class="text-right">{{ r.cases }}</td>
              <td class="text-right">
                <VChip size="small" color="success" variant="tonal">{{ soles(r.typicalPrice) }}</VChip>
              </td>
              <td class="text-right">{{ soles(r.priceMin) }}</td>
              <td class="text-right">{{ soles(r.priceMax) }}</td>
            </tr>
            <tr v-if="!data.interprovincialRoutes.length">
              <td colspan="5" class="text-center text-medium-emphasis py-6">Sin rutas con 3 o más servicios.</td>
            </tr>
          </tbody>
        </VTable>
      </VCard>
    </template>
  </section>
</template>
