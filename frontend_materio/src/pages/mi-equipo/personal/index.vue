<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { apiClient } from '@/services/apiClient'

const router = useRouter()

const TYPE = {
  conductor: { label: 'Conductor', color: 'primary', icon: 'ri-steering-line' },
  ayudante: { label: 'Ayudante', color: 'info', icon: 'ri-user-2-line' },
  asesor: { label: 'Asesor', color: 'success', icon: 'ri-briefcase-line' },
}
const FILTERS = [
  { value: '', label: 'Todos' },
  { value: 'conductor', label: 'Conductores' },
  { value: 'ayudante', label: 'Ayudantes' },
  { value: 'asesor', label: 'Asesores' },
]

const rows = ref([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const type = ref('')
const onlyActive = ref(true)
const page = ref(1)
const pages = ref(1)
const total = ref(0)
let searchTimer

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    const data = await apiClient.get('/api/v2/personnel/', {
      search: search.value,
      type: type.value || undefined,
      status: onlyActive.value ? 'active' : undefined,
      page: page.value,
      pageSize: 25,
    })
    rows.value = data.results
    pages.value = data.pages
    total.value = data.total
  } catch (e) {
    error.value = e.message || 'No se pudo cargar el personal.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch([type, onlyActive, page], load)
watch(search, () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { page.value = 1; load() }, 350) })

const editRoute = row => (row.type === 'asesor'
  ? null
  : `/personal-campo/${row.type === 'conductor' ? 'conductores' : 'ayudantes'}`)

const counts = computed(() => rows.value.reduce((acc, r) => { acc[r.type] = (acc[r.type] || 0) + 1; return acc }, {}))
</script>

<template>
  <section>
    <div class="d-flex flex-wrap align-center justify-space-between ga-4 mb-6">
      <div>
        <h1 class="text-h4 font-weight-bold mb-1">Personal</h1>
        <p class="text-body-1 text-medium-emphasis mb-0">
          Directorio de nuestro equipo: conductores, ayudantes y asesores.
        </p>
      </div>
      <VBtn prepend-icon="ri-add-line" append-icon="ri-arrow-down-s-line">
        Nuevo personal
        <VMenu activator="parent">
          <VList>
            <VListItem prepend-icon="ri-steering-line" title="Conductor" @click="router.push('/personal-campo/conductores?new=1')" />
            <VListItem prepend-icon="ri-user-2-line" title="Ayudante" @click="router.push('/personal-campo/ayudantes?new=1')" />
            <VListItem
              prepend-icon="ri-briefcase-line" title="Asesor"
              subtitle="Desde Usuarios y permisos"
              :disabled="true"
            />
          </VList>
        </VMenu>
      </VBtn>
    </div>

    <VCard>
      <VCardText class="d-flex flex-wrap align-center ga-4">
        <VTextField
          v-model="search" prepend-inner-icon="ri-search-line"
          label="Buscar por nombre, documento o teléfono"
          density="compact" hide-details clearable style="max-width: 340px;"
        />
        <div class="d-flex flex-wrap ga-2">
          <VChip
            v-for="f in FILTERS"
            :key="f.value"
            :color="type === f.value ? 'primary' : undefined"
            :variant="type === f.value ? 'flat' : 'tonal'"
            @click="type = f.value"
          >
            {{ f.label }}
          </VChip>
        </div>
        <VSwitch v-model="onlyActive" label="Solo activos" color="primary" hide-details density="compact" />
      </VCardText>

      <VAlert v-if="error" type="error" variant="tonal" class="ma-4">
        {{ error }}
        <template #append><VBtn size="small" variant="text" @click="load">Reintentar</VBtn></template>
      </VAlert>

      <VDivider />

      <VTable>
        <thead>
          <tr>
            <th>Nombre</th><th>Tipo</th><th>Documento</th><th>Teléfono</th><th>Detalle</th>
            <th>Estado</th><th class="text-right">Acciones</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="7" class="text-center py-8"><VProgressCircular indeterminate color="primary" /></td></tr>
          <tr v-else-if="!rows.length"><td colspan="7" class="text-center text-medium-emphasis py-10">Sin personal para el filtro.</td></tr>
          <tr v-for="row in rows" v-else :key="row.id">
            <td class="font-weight-medium">{{ row.name }}</td>
            <td>
              <VChip size="small" :color="TYPE[row.type]?.color" variant="tonal">
                <VIcon start :icon="TYPE[row.type]?.icon" size="14" /> {{ TYPE[row.type]?.label }}
              </VChip>
            </td>
            <td>{{ row.documentId || '—' }}</td>
            <td>{{ row.phone || '—' }}</td>
            <td class="text-medium-emphasis text-body-2">{{ row.detail || '—' }}</td>
            <td><VChip size="small" :color="row.active ? 'success' : 'secondary'">{{ row.active ? 'Activo' : 'Inactivo' }}</VChip></td>
            <td class="text-right text-no-wrap">
              <VBtn
                v-if="editRoute(row)" size="small" variant="text" icon="ri-external-link-line"
                title="Ver en su módulo" @click="router.push(editRoute(row))"
              />
              <span v-else class="text-caption text-disabled">Usuarios y permisos</span>
            </td>
          </tr>
        </tbody>
      </VTable>

      <div v-if="pages > 1" class="d-flex justify-space-between align-center pa-4">
        <span class="text-caption text-medium-emphasis">{{ total }} en total</span>
        <VPagination v-model="page" :length="pages" :total-visible="5" density="comfortable" />
      </div>
    </VCard>
  </section>
</template>
