<script setup>
import { onMounted, reactive, ref } from 'vue'

import { fetchOutsourcing } from '@/services/reportsService'

const MODALITY = {
  propio: { label: 'Nuestro equipo', color: 'primary' },
  tercerizado: { label: 'Tercerizado', color: 'warning' },
  por_definir: { label: 'Por definir', color: 'default' },
}

const data = ref(null)
const loading = ref(true)
const error = ref('')
const filters = reactive({ period: 'month', on: '', from: '', to: '' })

const soles = n => `S/ ${Math.round(n || 0).toLocaleString('es-PE')}`

const load = async () => {
  loading.value = true
  error.value = ''
  try { data.value = await fetchOutsourcing({ ...filters }) }
  catch (e) { error.value = e.message || 'No se pudo cargar.' }
  finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">Propio vs Tercerizado</h1>
    <p class="text-body-1 text-medium-emphasis mb-6">
      Reservas confirmadas por quién ejecuta. El margen de tercerización = venta al cliente − costo del transportista.
    </p>

    <VCard class="mb-6">
      <VCardText class="d-flex flex-wrap ga-4 align-center">
        <VSelect
          v-model="filters.period" label="Período" density="compact" hide-details style="max-width: 160px;"
          :items="[
            { title: 'Este mes', value: 'month' },
            { title: 'Esta quincena', value: 'fortnight' },
            { title: 'Esta semana', value: 'week' },
            { title: 'Rango', value: 'range' },
          ]"
          @update:model-value="load"
        />
        <template v-if="filters.period === 'range'">
          <VTextField v-model="filters.from" label="Desde" type="date" density="compact" hide-details style="max-width: 170px;" @update:model-value="load" />
          <VTextField v-model="filters.to" label="Hasta" type="date" density="compact" hide-details style="max-width: 170px;" @update:model-value="load" />
        </template>
      </VCardText>
    </VCard>

    <VAlert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</VAlert>
    <div v-if="loading" class="text-center py-10"><VProgressCircular indeterminate /></div>

    <template v-else-if="data">
      <VRow class="mb-2">
        <VCol v-for="r in data.summary" :key="r.modality" cols="12" md="4">
          <VCard>
            <VCardText>
              <div class="d-flex align-center ga-2 mb-2">
                <VChip size="small" :color="MODALITY[r.modality]?.color">{{ MODALITY[r.modality]?.label }}</VChip>
                <span class="text-caption text-medium-emphasis">{{ r.count }} reserva(s)</span>
              </div>
              <div class="text-h5 font-weight-bold">{{ soles(r.revenue) }}</div>
              <div class="text-caption text-medium-emphasis">facturación</div>
              <template v-if="r.modality === 'tercerizado'">
                <VDivider class="my-2" />
                <div class="d-flex justify-space-between text-body-2">
                  <span class="text-medium-emphasis">Costo transportistas</span><span>{{ soles(r.cost) }}</span>
                </div>
                <div class="d-flex justify-space-between text-body-2 font-weight-bold" :class="r.margin >= 0 ? 'text-success' : 'text-error'">
                  <span>Margen</span>
                  <span>{{ soles(r.margin) }}<span v-if="r.marginPct != null" class="text-caption"> ({{ r.marginPct }}%)</span></span>
                </div>
              </template>
            </VCardText>
          </VCard>
        </VCol>
      </VRow>

      <VCard>
        <VCardText>
          <div class="text-overline mb-2">Evolución</div>
          <div v-if="!data.series.length" class="text-body-2 text-medium-emphasis py-4">Sin datos en el período.</div>
          <VTable v-else density="compact">
            <thead>
              <tr>
                <th>Período</th>
                <th class="text-right">Fact. propia</th>
                <th class="text-right">Fact. tercerizada</th>
                <th class="text-right">Costo tercerización</th>
                <th class="text-right">Margen tercerización</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in data.series" :key="row.bucket">
                <td>{{ new Date(row.bucket).toLocaleDateString('es-PE', { day: '2-digit', month: 'short' }) }}</td>
                <td class="text-right">{{ soles(row.ownRevenue) }}</td>
                <td class="text-right">{{ soles(row.outsourcedRevenue) }}</td>
                <td class="text-right">{{ soles(row.outsourcedCost) }}</td>
                <td class="text-right font-weight-medium" :class="row.outsourcedMargin >= 0 ? 'text-success' : 'text-error'">
                  {{ soles(row.outsourcedMargin) }}
                </td>
              </tr>
            </tbody>
          </VTable>
        </VCardText>
      </VCard>
    </template>
  </section>
</template>
