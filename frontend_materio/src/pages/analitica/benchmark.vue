<script setup>
import { onMounted, ref } from 'vue'

import { fetchBenchmark } from '@/services/reportsService'

const data = ref(null)
const loading = ref(true)
const error = ref('')

const soles = n => `S/ ${Math.round(n || 0).toLocaleString('es-PE')}`

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
    <p class="text-body-2 text-medium-emphasis mb-6">
      Servicios importados (hoja «wally»). No crece con la operación, no es atribuible a asesor ni canal.
    </p>

    <VProgressLinear v-if="loading" indeterminate class="mb-4" />
    <VAlert v-else-if="error" type="error" variant="tonal">
      {{ error }}
    </VAlert>

    <template v-else-if="data">
      <VRow class="mb-2">
        <VCol cols="12" sm="6" md="3">
          <VCard variant="tonal"><VCardText>
            <div class="text-caption text-medium-emphasis">Servicios totales</div>
            <div class="text-h5 font-weight-bold">{{ (data.total || 0).toLocaleString('es-PE') }}</div>
            <div class="text-caption">{{ data.dateMin }} → {{ data.dateMax }}</div>
          </VCardText></VCard>
        </VCol>
        <VCol cols="12" sm="6" md="3">
          <VCard variant="tonal"><VCardText>
            <div class="text-caption text-medium-emphasis">Cerrados con precio</div>
            <div class="text-h5 font-weight-bold">{{ (data.closed || 0).toLocaleString('es-PE') }}</div>
          </VCardText></VCard>
        </VCol>
        <VCol cols="12" sm="6" md="3">
          <VCard variant="tonal"><VCardText>
            <div class="text-caption text-medium-emphasis">Precio mediano</div>
            <div class="text-h5 font-weight-bold">{{ soles(data.price.all.median) }}</div>
            <div class="text-caption">p25 {{ data.price.all.p25 }} · p75 {{ data.price.all.p75 }} · p90 {{ data.price.all.p90 }}</div>
          </VCardText></VCard>
        </VCol>
        <VCol cols="12" sm="6" md="3">
          <VCard variant="tonal" color="warning"><VCardText>
            <div class="text-caption">Interprovincial</div>
            <div class="text-h5 font-weight-bold">{{ data.scope.interprovincial.servicesPct }}%</div>
            <div class="text-caption">servicios · {{ data.scope.interprovincial.revenuePct }}% facturación</div>
          </VCardText></VCard>
        </VCol>
      </VRow>

      <VRow>
        <VCol cols="12" md="6">
          <VCard><VCardTitle>Volumen por año</VCardTitle>
            <VTable density="compact">
              <thead><tr><th>Año</th><th class="text-right">Servicios</th><th class="text-right">Cerrados</th></tr></thead>
              <tbody>
                <tr v-for="r in data.byYear" :key="r.date">
                  <td>{{ new Date(r.date).getFullYear() }}</td>
                  <td class="text-right">{{ r.count.toLocaleString('es-PE') }}</td>
                  <td class="text-right">{{ r.closed.toLocaleString('es-PE') }}</td>
                </tr>
              </tbody>
            </VTable>
          </VCard>
        </VCol>
        <VCol cols="12" md="6">
          <VCard><VCardTitle>Mix por tipo</VCardTitle>
            <VTable density="compact">
              <thead><tr><th>Tipo</th><th class="text-right">Servicios</th><th class="text-right">%</th></tr></thead>
              <tbody>
                <tr v-for="r in data.byType" :key="r.type">
                  <td class="text-capitalize">{{ r.type || '—' }}</td>
                  <td class="text-right">{{ r.count.toLocaleString('es-PE') }}</td>
                  <td class="text-right">{{ r.pct }}%</td>
                </tr>
              </tbody>
            </VTable>
          </VCard>
        </VCol>
      </VRow>

      <VCard class="mt-4"><VCardTitle>Local vs interprovincial (servicios cerrados)</VCardTitle>
        <VTable density="compact">
          <thead><tr>
            <th>Ámbito</th><th class="text-right">Servicios</th><th class="text-right">% serv.</th>
            <th class="text-right">Ticket prom.</th><th class="text-right">Mediana</th>
            <th class="text-right">Facturación</th><th class="text-right">% fact.</th>
          </tr></thead>
          <tbody>
            <tr v-for="(v, k) in { 'Local (Lima)': data.scope.local, 'Interprovincial': data.scope.interprovincial }" :key="k">
              <td>{{ k }}</td>
              <td class="text-right">{{ v.count.toLocaleString('es-PE') }}</td>
              <td class="text-right">{{ v.servicesPct }}%</td>
              <td class="text-right">{{ soles(v.averageTicket) }}</td>
              <td class="text-right">{{ soles(v.median) }}</td>
              <td class="text-right">{{ soles(v.revenue) }}</td>
              <td class="text-right">{{ v.revenuePct }}%</td>
            </tr>
          </tbody>
        </VTable>
      </VCard>

      <VCard class="mt-4"><VCardTitle>Rutas interprovinciales frecuentes (≥ 3 servicios) — tarifa típica</VCardTitle>
        <VTable density="compact">
          <thead><tr>
            <th>Ruta</th><th class="text-right">Casos</th><th class="text-right">Precio típico</th>
            <th class="text-right">Mín</th><th class="text-right">Máx</th>
          </tr></thead>
          <tbody>
            <tr v-for="r in data.interprovincialRoutes" :key="r.route">
              <td>{{ r.route }}</td>
              <td class="text-right">{{ r.cases }}</td>
              <td class="text-right font-weight-bold">{{ soles(r.typicalPrice) }}</td>
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
