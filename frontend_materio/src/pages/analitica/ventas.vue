<script setup>
import { onMounted, reactive, ref } from 'vue'

import { fetchSales } from '@/services/reportsService'

const data = ref(null)
const loading = ref(true)
const error = ref('')

const filters = reactive({ period: 'month', on: '', from: '', to: '', advisor: '', channel: '', type: '' })

const soles = n => `S/ ${Math.round(n || 0).toLocaleString('es-PE')}`

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
    <p class="text-body-2 text-medium-emphasis mb-4">
      Pipeline del CRM. «Venta» = reserva confirmada. Vacío al inicio, se llena con el uso.
    </p>

    <VCard class="mb-4"><VCardText class="d-flex flex-wrap ga-3 align-end">
      <VSelect
        v-model="filters.period" label="Periodo" density="compact" hide-details style="max-width: 150px;"
        :items="[
          { title: 'Día', value: 'day' }, { title: 'Semana', value: 'week' },
          { title: 'Quincena', value: 'fortnight' }, { title: 'Mes', value: 'month' },
          { title: 'Rango', value: 'range' },
        ]"
      />
      <VTextField v-if="filters.period !== 'range'" v-model="filters.on" type="date" label="En la fecha" density="compact" hide-details style="max-width: 170px;" />
      <template v-else>
        <VTextField v-model="filters.from" type="date" label="Desde" density="compact" hide-details style="max-width: 170px;" />
        <VTextField v-model="filters.to" type="date" label="Hasta" density="compact" hide-details style="max-width: 170px;" />
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
      <VBtn :loading="loading" @click="load">Aplicar</VBtn>
    </VCardText></VCard>

    <VAlert v-if="error" type="error" variant="tonal">{{ error }}</VAlert>
    <VProgressLinear v-if="loading" indeterminate class="mb-4" />

    <template v-if="data && !loading">
      <p class="text-caption text-medium-emphasis mb-4">Periodo: <strong>{{ data.from }} – {{ data.to }}</strong></p>

      <!-- Ventas -->
      <VCard class="mb-4"><VCardTitle>Ventas del periodo</VCardTitle><VCardText>
        <VRow>
          <VCol v-for="kpi in [
            { l: 'Reservas (bruto)', v: data.sales.gross.count, s: 'incluye canceladas' },
            { l: 'Facturado (bruto)', v: soles(data.sales.gross.billed) },
            { l: 'Reservas (neto)', v: data.sales.net.count, s: `${data.sales.cancelled} cancelada(s)` },
            { l: 'Facturado (neto)', v: soles(data.sales.net.billed) },
            { l: 'Ticket promedio', v: soles(data.sales.net.averageTicket) },
          ]" :key="kpi.l" cols="6" md="2">
            <div class="text-caption text-medium-emphasis">{{ kpi.l }}</div>
            <div class="text-h6 font-weight-bold">{{ kpi.v }}</div>
            <div v-if="kpi.s" class="text-caption">{{ kpi.s }}</div>
          </VCol>
        </VRow>
        <VTable v-if="data.sales.series.length" density="compact" class="mt-3">
          <thead><tr><th>Periodo</th><th class="text-right">Reservas</th><th class="text-right">Facturado</th></tr></thead>
          <tbody>
            <tr v-for="r in data.sales.series" :key="r.bucket">
              <td>{{ r.bucket }}</td><td class="text-right">{{ r.count }}</td><td class="text-right">{{ soles(r.billed) }}</td>
            </tr>
          </tbody>
        </VTable>
        <p v-else class="text-medium-emphasis text-center py-6">Sin reservas confirmadas en el periodo.</p>
      </VCardText></VCard>

      <VRow>
        <VCol v-for="grp in [
          { title: 'Por asesor', rows: data.sales.byAdvisor },
          { title: 'Por canal', rows: data.sales.byChannel },
          { title: 'Por tipo', rows: data.sales.byType },
        ]" :key="grp.title" cols="12" md="4">
          <VCard><VCardTitle>{{ grp.title }}</VCardTitle>
            <VTable density="compact">
              <thead><tr><th>{{ grp.title }}</th><th class="text-right">Res.</th><th class="text-right">Facturado</th></tr></thead>
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
      <VCard class="mt-4"><VCardTitle>Embudo: cotizado → cerrado</VCardTitle><VCardText>
        <VRow>
          <VCol v-for="k in [
            { l: 'Leads creados', v: data.funnel.created },
            { l: 'Cotizados', v: data.funnel.quoted },
            { l: 'Ganados', v: data.funnel.won },
            { l: 'Perdidos', v: data.funnel.lost },
            { l: 'Tasa cierre', v: data.funnel.closeRate + '%' },
            { l: 'Win rate', v: data.funnel.winRate + '%' },
            { l: 'Ciclo (días)', v: data.funnel.avgCycleDays, s: 'mediana ' + data.funnel.medianCycleDays },
          ]" :key="k.l" cols="6" md="3">
            <div class="text-caption text-medium-emphasis">{{ k.l }}</div>
            <div class="text-h6 font-weight-bold">{{ k.v }}</div>
            <div v-if="k.s" class="text-caption">{{ k.s }}</div>
          </VCol>
        </VRow>
        <VTable v-if="data.funnel.lossReasons.length" density="compact" class="mt-3" style="max-width: 420px;">
          <thead><tr><th>Motivo de pérdida</th><th class="text-right">n</th></tr></thead>
          <tbody><tr v-for="m in data.funnel.lossReasons" :key="m.reason"><td>{{ m.label }}</td><td class="text-right">{{ m.count }}</td></tr></tbody>
        </VTable>
      </VCardText></VCard>

      <!-- Ticket local vs interprovincial -->
      <VCard class="mt-4"><VCardTitle>Ticket — local vs interprovincial</VCardTitle>
        <VTable density="compact">
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
      <VCard class="mt-4"><VCardTitle>Cobranzas</VCardTitle><VCardText>
        <VRow>
          <VCol cols="6" md="3"><div class="text-caption text-medium-emphasis">Facturado</div><div class="text-h6 font-weight-bold">{{ soles(data.collections.billed) }}</div></VCol>
          <VCol cols="6" md="3"><div class="text-caption text-medium-emphasis">Cobrado</div><div class="text-h6 font-weight-bold">{{ soles(data.collections.collected) }}</div><div class="text-caption">{{ data.collections.collectedPct }}%</div></VCol>
          <VCol cols="6" md="3"><div class="text-caption text-medium-emphasis">Pendiente</div><div class="text-h6 font-weight-bold">{{ soles(data.collections.pending) }}</div></VCol>
        </VRow>
        <VTable v-if="data.collections.topPending.length" density="compact" class="mt-3">
          <thead><tr><th>Reserva</th><th>Cliente</th><th class="text-right">Saldo</th><th class="text-right">Días</th></tr></thead>
          <tbody><tr v-for="r in data.collections.topPending" :key="r.code"><td>{{ r.code }}</td><td>{{ r.customer }}</td><td class="text-right">{{ soles(r.balance) }}</td><td class="text-right">{{ r.days }}</td></tr></tbody>
        </VTable>
        <p v-else class="text-medium-emphasis text-center py-4">Sin saldos pendientes.</p>
      </VCardText></VCard>
    </template>
  </section>
</template>
