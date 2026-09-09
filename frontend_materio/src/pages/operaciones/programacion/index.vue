<script setup>
import { onMounted, reactive, ref, watch } from 'vue'

import { apiClient } from '@/services/apiClient'

const STATE = {
  programado: { label: 'Programado', color: 'info' },
  en_ruta: { label: 'En ruta', color: 'warning' },
  en_servicio: { label: 'En servicio', color: 'primary' },
  finalizado: { label: 'Finalizado', color: 'success' },
  cancelado: { label: 'Cancelado', color: 'error' },
}
const NEXT = {
  programado: ['en_ruta', 'cancelado'],
  en_ruta: ['en_servicio', 'cancelado'],
  en_servicio: ['finalizado', 'cancelado'],
}

const rows = ref([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const day = ref(new Date().toISOString().slice(0, 10))
const state = ref('')
let searchTimer

const soles = n => `S/ ${Math.round(n || 0).toLocaleString('es-PE')}`

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    const data = await apiClient.get('/api/v2/schedule/', {
      date: day.value || undefined,
      state: state.value || undefined,
      search: search.value || undefined,
      pageSize: 200,
    })
    rows.value = data.results
  } catch (e) {
    error.value = e.message || 'No se pudo cargar la programación.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch([day, state], load)
watch(search, () => { clearTimeout(searchTimer); searchTimer = setTimeout(load, 350) })

const shiftDay = n => {
  const d = new Date(day.value)
  d.setDate(d.getDate() + n)
  day.value = d.toISOString().slice(0, 10)
}

const snackbar = reactive({ show: false, text: '', color: 'success' })
const setState = async (row, target) => {
  try {
    await apiClient.post(`/api/v2/schedule/${row.id}/set-state/`, { state: target })
    Object.assign(snackbar, { show: true, text: `Marcado ${STATE[target]?.label}.`, color: 'success' })
    await load()
  } catch (e) {
    Object.assign(snackbar, { show: true, text: e.message || 'No se pudo cambiar el estado.', color: 'error' })
  }
}
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">Programación</h1>
    <p class="text-body-1 text-medium-emphasis mb-6">
      Servicios asignados a un equipo, por día. La asignación se arma en la Pizarra.
    </p>

    <VCard>
      <VCardText class="d-flex flex-wrap align-center ga-4">
        <div class="d-flex align-center ga-1">
          <VBtn icon="ri-arrow-left-s-line" variant="text" size="small" @click="shiftDay(-1)" />
          <AppDateField v-model="day" hide-details style="flex: 0 0 180px; width: 180px;" />
          <VBtn icon="ri-arrow-right-s-line" variant="text" size="small" @click="shiftDay(1)" />
          <VBtn size="small" variant="text" @click="day = new Date().toISOString().slice(0, 10)">Hoy</VBtn>
        </div>
        <VTextField
          v-model="search" prepend-inner-icon="ri-search-line"
          label="Buscar código, cliente, placa o conductor"
          density="compact" hide-details clearable style="max-width: 320px;"
        />
        <div class="d-flex flex-wrap ga-2">
          <VChip
            :color="state === '' ? 'primary' : undefined" :variant="state === '' ? 'flat' : 'tonal'"
            @click="state = ''"
          >
            Todos
          </VChip>
          <VChip
            v-for="(s, value) in STATE" :key="value"
            :color="state === value ? 'primary' : undefined" :variant="state === value ? 'flat' : 'tonal'"
            @click="state = value"
          >
            {{ s.label }}
          </VChip>
        </div>
      </VCardText>

      <VAlert v-if="error" type="error" variant="tonal" class="ma-4">
        {{ error }}
        <template #append><VBtn size="small" variant="text" @click="load">Reintentar</VBtn></template>
      </VAlert>

      <VDivider />

      <VTable class="text-no-wrap">
        <thead>
          <tr>
            <th>Hora</th><th>Servicio</th><th>Cliente</th><th>Vehículo</th><th>Conductor</th>
            <th>Ayudantes</th><th class="text-right">Monto</th><th>Estado</th><th class="text-right">Acciones</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="9" class="text-center py-8"><VProgressCircular indeterminate color="primary" /></td></tr>
          <tr v-else-if="!rows.length"><td colspan="9" class="text-center text-medium-emphasis py-10">Sin programaciones para ese día.</td></tr>
          <tr v-for="row in rows" v-else :key="row.id">
            <td class="font-weight-medium">{{ row.startTime }}{{ row.endTime ? `–${row.endTime}` : '' }}</td>
            <td>{{ row.serviceCode }}</td>
            <td>{{ row.customerName }}</td>
            <td>{{ row.plate || '—' }}</td>
            <td>{{ row.driverName || '—' }}</td>
            <td class="text-medium-emphasis">{{ row.helpers.length ? row.helpers.join(', ') : '—' }}</td>
            <td class="text-right">{{ soles(row.amount) }}</td>
            <td><VChip size="small" :color="STATE[row.state]?.color">{{ STATE[row.state]?.label || row.state }}</VChip></td>
            <td class="text-right text-no-wrap">
              <VMenu v-if="NEXT[row.state]?.length">
                <template #activator="{ props }">
                  <VBtn v-bind="props" size="small" variant="tonal">Cambiar estado</VBtn>
                </template>
                <VList>
                  <VListItem v-for="t in NEXT[row.state]" :key="t" @click="setState(row, t)">
                    <VListItemTitle>{{ STATE[t]?.label }}</VListItemTitle>
                  </VListItem>
                </VList>
              </VMenu>
              <span v-else class="text-caption text-disabled">—</span>
            </td>
          </tr>
        </tbody>
      </VTable>
    </VCard>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
