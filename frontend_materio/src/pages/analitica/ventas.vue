<script setup>
import { onMounted, reactive, ref } from 'vue'

import { fetchSales } from '@/services/reportsService'

const data = ref(null)
const loading = ref(true)
const error = ref('')

const filters = reactive({ period: 'month', on: '', from: '', to: '', advisor: '', channel: '', type: '' })

const soles = n => `S/ ${Math.round(n || 0).toLocaleString('es-PE')}`
const num = n => (n || 0).toLocaleString('es-PE')

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    data.value = await fetchSales({ ...filters })
  } catch (e) {
    error.value = e.message || 'No se pudo cargar el reporte.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">
      Ventas vivas
    </h1>
    <p class="text-body-1 text-medium-emphasis mb-6">
      Pipeline del CRM. «Venta» = reserva confirmada. Vacío al inicio, se llena con el uso.
    </p>

    <VCard class="mb-6">
      <VCardText class="d-flex flex-wrap ga-4 align-center">
        <VSelect
          v-model="filters.period" label="Periodo" density="compact" hide-details style="max-width: 150px;"
          :items="[
            { title: 'Día', value: 'day' }, { title: 'Semana', value: 'week' },
            { title: 'Quincena', value: 'fortnight' }, { title: 'Mes', value: 'month' },
            { title: 'Rango', value: 'range' },
          ]"
        />
        <AppDateField v-if="filters.period !== 'range'" v-model="filters.on" label="En la fecha" hide-details style="max-width: 170px;" />
        <template v-else>
          <AppDateField v-model="filters.from" label="Desde" hide-details style="max-width: 170px;" />
          <AppDateField v-model="filters.to" label="Hasta" hide-details style="max-width: 170px;" />
        </template>
        <VSelect
          v-model="filters.advisor" label="Asesor" density="compact" hide-details clearable style="max-width: 170px;"
          :items="(data?.filterOptions.advisors || []).map(a => ({ title: a.firstName || a.username, value: a.id }))"
        />
        <VSelect
          v-model="filters.channel" label="Canal" density="compact" hide-details clearable style="max-width: 170px;"
          :items="(data?.filterOptions.channels || []).map(c => ({ title: c.name, value: c.id }))"
        />
        <VSelect
          v-model="filters.type" label="Tipo" density="compact" hide-details clearable style="max-width: 150px;"
          :items="data?.filterOptions.types || []"
        />
        <VBtn :loading="loading" prepend-icon="ri-filter-3-line" @click="load">Aplicar</VBtn>
      </VCardText>
    </VCard>

    <VAlert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</VAlert>
    <VProgressLinear v-if="loading" indeterminate color="primary" class="mb-4" />

    <template v-if="data && !loading">
      <VChip size="small" color="primary" variant="tonal" class="mb-6">
        <VIcon start icon="ri-calendar-line" size="16" />
        {{ data.from }} – {{ data.to }}
      </VChip>

      <!-- Ventas del periodo -->
      <VRow class="match-height mb-2">
        <VCol cols="12" sm="6" md="4" lg="">
          <StatCard title="Reservas (bruto)" :value="num(data.sales.gross.count)" icon="ri-shopping-bag-3-line" color="primary" subtitle="incluye canceladas" />
        </VCol>
        <VCol cols="12" sm="6" md="4" lg="">
          <StatCard title="Facturado (bruto)" :value="soles(data.sales.gross.billed)" icon="ri-money-dollar-circle-line" color="secondary" />
        </VCol>
        <VCol cols="12" sm="6" md="4" lg="">
          <StatCard title="Reservas (neto)" :value="num(data.sales.net.count)" icon="ri-checkbox-circle-line" color="success" :subtitle="`${data.sales.cancelled} cancelada(s)`" />
        </VCol>
        <VCol cols="12" sm="6" md="4" lg="">
          <StatCard title="Facturado (neto)" :value="soles(data.sales.net.billed)" icon="ri-wallet-3-line" color="success" />
        </VCol>
        <VCol cols="12" sm="6" md="4" lg="">
          <StatCard title="Ticket promedio" :value="soles(data.sales.net.averageTicket)" icon="ri-price-tag-3-line" color="info" />
        </VCol>
      </VRow>

      <VCard v-if="data.sales.series.length" class="mb-6">
        <VCardItem><VCardTitle>Evolución del periodo</VCardTitle></VCardItem>
        <VDivider />
        <VTable density="comfortable">
          <thead><tr><th>Periodo</th><th class="text-right">Reservas</th><th class="text-right">Facturado</th></tr></thead>
          <tbody>
            <tr v-for="r in data.sales.series" :key="r.bucket">
              <td>{{ r.bucket }}</td><td class="text-right">{{ r.count }}</td><td class="text-right">{{ soles(r.billed) }}</td>
            </tr>
          </tbody>
        </VTable>
      </VCard>

      <VRow class="match-height mb-2">
        <VCol v-for="grp in [
          { title: 'Por asesor', icon: 'ri-user-star-line', rows: data.sales.byAdvisor },
          { title: 'Por canal', icon: 'ri-broadcast-line', rows: data.sales.byChannel },
          { title: 'Por tipo', icon: 'ri-price-tag-3-line', rows: data.sales.byType },
        ]" :key="grp.title" cols="12" md="4">
          <VCard>
            <VCardItem>
              <template #prepend><VIcon :icon="grp.icon" class="text-medium-emphasis" /></template>
              <VCardTitle>{{ grp.title }}</VCardTitle>
            </VCardItem>
            <VDivider />
            <VTable density="comfortable">
              <thead><tr><th>{{ grp.title.replace('Por ', '') }}</th><th class="text-right">Res.</th><th class="text-right">Facturado</th></tr></thead>
              <tbody>
                <tr v-for="(r, i) in grp.rows" :key="i">
                  <td class="text-capitalize">{{ r.label }}</td><td class="text-right">{{ r.count }}</td><td class="text-right">{{ soles(r.billed) }}</td>
                </tr>
                <tr v-if="!grp.rows.length"><td colspan="3" class="text-center text-medium-emphasis py-4">Sin datos.</td></tr>
              </tbody>
            </VTable>
          </VCard>
        </VCol>
      </VRow>

      <!-- Embudo -->
      <h2 class="text-h6 font-weight-bold mt-8 mb-3">Embudo: cotizado → cerrado</h2>
      <VRow class="match-height mb-2">
        <VCol cols="6" sm="4" md="3"><StatCard title="Leads creados" :value="num(data.funnel.created)" icon="ri-user-add-line" color="primary" /></VCol>
        <VCol cols="6" sm="4" md="3"><StatCard title="Cotizados" :value="num(data.funnel.quoted)" icon="ri-file-list-3-line" color="info" /></VCol>
        <VCol cols="6" sm="4" md="3"><StatCard title="Ganados" :value="num(data.funnel.won)" icon="ri-trophy-line" color="success" /></VCol>
        <VCol cols="6" sm="4" md="3"><StatCard title="Perdidos" :value="num(data.funnel.lost)" icon="ri-close-circle-line" color="error" /></VCol>
        <VCol cols="6" sm="4" md="3"><StatCard title="Tasa de cierre" :value="`${data.funnel.closeRate}%`" icon="ri-percent-line" color="warning" /></VCol>
        <VCol cols="6" sm="4" md="3"><StatCard title="Win rate" :value="`${data.funnel.winRate}%`" icon="ri-medal-line" color="success" /></VCol>
        <VCol cols="6" sm="4" md="3"><StatCard title="Ciclo (días)" :value="data.funnel.avgCycleDays" icon="ri-time-line" color="secondary" :subtitle="`mediana ${data.funnel.medianCycleDays}`" /></VCol>
      </VRow>

      <VCard v-if="data.funnel.lossReasons.length" class="mb-6" max-width="480">
        <VCardItem><VCardTitle>Motivos de pérdida</VCardTitle></VCardItem>
        <VDivider />
        <VTable density="comfortable">
          <thead><tr><th>Motivo</th><th class="text-right">n</th></tr></thead>
          <tbody><tr v-for="m in data.funnel.lossReasons" :key="m.reason"><td>{{ m.label }}</td><td class="text-right">{{ m.count }}</td></tr></tbody>
        </VTable>
      </VCard>

      <!-- Ticket local vs interprovincial -->
      <VCard class="mb-6">
        <VCardItem><VCardTitle>Ticket — local vs interprovincial</VCardTitle></VCardItem>
        <VDivider />
        <VTable density="comfortable">
          <thead><tr><th>Ámbito</th><th class="text-right">Reservas</th><th class="text-right">% serv.</th><th class="text-right">Facturado</th><th class="text-right">% fact.</th><th class="text-right">Ticket prom.</th></tr></thead>
          <tbody>
            <tr v-for="(v, k) in { 'Local (Lima)': data.ticket.local, 'Interprovincial': data.ticket.interprovincial }" :key="k">
              <td>{{ k }}</td>
              <td class="text-right">{{ v.count }}</td><td class="text-right">{{ v.servicesPct }}%</td>
              <td class="text-right">{{ soles(v.billed) }}</td><td class="text-right">{{ v.revenuePct }}%</td>
              <td class="text-right">{{ soles(v.averageTicket) }}</td>
            </tr>
          </tbody>
        </VTable>
      </VCard>

      <!-- Cobranzas -->
      <h2 class="text-h6 font-weight-bold mt-8 mb-3">Cobranzas</h2>
      <VRow class="match-height mb-2">
        <VCol cols="12" sm="4"><StatCard title="Facturado" :value="soles(data.collections.billed)" icon="ri-bill-line" color="primary" /></VCol>
        <VCol cols="12" sm="4"><StatCard title="Cobrado" :value="soles(data.collections.collected)" icon="ri-hand-coin-line" color="success" :subtitle="`${data.collections.collectedPct}% de lo facturado`" /></VCol>
        <VCol cols="12" sm="4"><StatCard title="Pendiente" :value="soles(data.collections.pending)" icon="ri-alarm-warning-line" color="error" /></VCol>
      </VRow>

      <VCard v-if="data.collections.topPending.length">
        <VCardItem><VCardTitle>Saldos pendientes</VCardTitle></VCardItem>
        <VDivider />
        <VTable density="comfortable">
          <thead><tr><th>Reserva</th><th>Cliente</th><th class="text-right">Saldo</th><th class="text-right">Días</th></tr></thead>
          <tbody><tr v-for="r in data.collections.topPending" :key="r.code"><td class="font-weight-medium">{{ r.code }}</td><td>{{ r.customer }}</td><td class="text-right">{{ soles(r.balance) }}</td><td class="text-right">{{ r.days }}</td></tr></tbody>
        </VTable>
      </VCard>
    </template>
  </section>
</template>
