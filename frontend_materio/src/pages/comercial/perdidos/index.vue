<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { leadServiceData, lostList, reactivateLead } from '@/services/commercialService'
import { usePipelineStore } from '@/stores/pipelineStore'
import ServiceViewDialog from '@/pages/atencion/bandeja-entrada/components/ServiceViewDialog.vue'

const router = useRouter()
const pipeline = usePipelineStore()

const rows = ref([])
const loading = ref(true)
const error = ref('')
const search = ref('')
let searchTimer

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    rows.value = (await lostList({ search: search.value })).results
  } catch (e) {
    error.value = e.message || 'No se pudo cargar la lista.'
  } finally {
    loading.value = false
  }
}

const onSearch = () => { clearTimeout(searchTimer); searchTimer = setTimeout(load, 350) }

onMounted(load)

// --- Ver detalle ---
const viewOpen = ref(false)
const viewLeadId = ref(null)
const viewServiceData = ref({})

const openDetail = async row => {
  viewLeadId.value = row.leadId
  viewServiceData.value = {}
  viewOpen.value = true
  try {
    viewServiceData.value = (await leadServiceData(row.leadId)).serviceData || {}
  } catch { /* precios vienen de /stage */ }
}

// --- Reactivar ---
const reactivateTarget = ref(null)
const reactivateBusy = ref(false)
const confirmReactivate = async () => {
  const row = reactivateTarget.value
  reactivateBusy.value = true
  try {
    const res = await reactivateLead(row.leadId)
    const dest = res.stage === 'review' ? 'Estancados' : 'Oportunidades'
    notify(`Lead reactivado (${dest}).`)
    pipeline.bump()
    reactivateTarget.value = null
    viewOpen.value = false
    await load()
  } catch (e) {
    notify(e.message || 'No se pudo reactivar.', 'error')
  } finally {
    reactivateBusy.value = false
  }
}

const openConversation = row => {
  if (row.conversationId) router.push(`/atencion/bandeja-entrada?conversation=${row.conversationId}`)
}
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">
      Perdidos
    </h1>
    <p class="text-body-2 text-medium-emphasis mb-4">
      Oportunidades descartadas o marcadas como perdidas. Revisá el motivo y, si fue un error,
      reactivá el lead para devolverlo al pipeline.
    </p>

    <VCard>
      <VCardText>
        <VTextField
          v-model="search"
          prepend-inner-icon="ri-search-line"
          label="Buscar por cliente, ruta o motivo"
          density="compact" hide-details clearable style="max-width: 380px;"
          @update:model-value="onSearch"
        />
      </VCardText>

      <VAlert v-if="error" type="error" variant="tonal" class="ma-4">
        {{ error }}
        <template #append><VBtn size="small" variant="text" @click="load">Reintentar</VBtn></template>
      </VAlert>

      <VDivider />

      <VTable>
        <thead>
          <tr>
            <th>Cliente</th><th>Ruta</th><th>Motivo</th><th>Perdido</th><th>Quién</th><th class="text-right">Acciones</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="6" class="text-center py-8"><VProgressCircular indeterminate color="primary" /></td></tr>
          <tr v-else-if="!rows.length"><td colspan="6" class="text-center text-medium-emphasis py-10">No hay leads perdidos.</td></tr>
          <tr v-for="row in rows" v-else :key="row.id">
            <td class="font-weight-medium text-primary" style="cursor: pointer;" title="Ver detalle" @click="openDetail(row)">{{ row.customerName }}</td>
            <td>
              {{ row.route }}
              <VChip v-if="row.isInterprovincial" size="x-small" color="warning" class="ms-1">Fuera de Lima</VChip>
            </td>
            <td class="text-body-2">{{ row.reason }}</td>
            <td>{{ row.lostAt ? row.lostAt.slice(0, 10) : '—' }}</td>
            <td class="text-body-2">{{ row.lostBy || '—' }}</td>
            <td class="text-right text-no-wrap">
              <VBtn size="small" variant="text" icon="ri-eye-line" title="Ver detalle" @click="openDetail(row)" />
              <VBtn size="small" variant="text" icon="ri-chat-3-line" title="Abrir conversación" :disabled="!row.conversationId" @click="openConversation(row)" />
              <VBtn size="small" variant="tonal" color="primary" class="ms-1" @click="reactivateTarget = row">Reactivar</VBtn>
            </td>
          </tr>
        </tbody>
      </VTable>
    </VCard>

    <ServiceViewDialog
      v-if="viewOpen && viewLeadId"
      :lead-id="viewLeadId"
      :service-data="viewServiceData"
      context="lost"
      @close="viewOpen = false"
    />

    <!-- Reactivar -->
    <VDialog :model-value="!!reactivateTarget" max-width="440" @update:model-value="reactivateTarget = null">
      <VCard v-if="reactivateTarget">
        <VCardTitle>Reactivar lead</VCardTitle>
        <VCardText>
          <p>
            <strong>{{ reactivateTarget.customerName }}</strong> volverá al pipeline
            (Oportunidades, o Estancados si necesita asesor). Se descartó por:
            <em>{{ reactivateTarget.reason }}</em>.
          </p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="reactivateTarget = null">Cancelar</VBtn>
          <VBtn color="primary" :loading="reactivateBusy" @click="confirmReactivate">Reactivar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
