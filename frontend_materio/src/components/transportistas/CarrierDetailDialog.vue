<script setup>
import { computed, onMounted, ref } from 'vue'

import { carrierDriversService, carriersService, carrierVehiclesService } from '@/services/carriersService'
import CarrierVehicleFormDialog from './CarrierVehicleFormDialog.vue'
import CarrierDriverFormDialog from './CarrierDriverFormDialog.vue'

const props = defineProps({
  carrier: { type: Object, default: null },
  carrierId: { type: [Number, String], default: null },
})
defineEmits(['close'])

const info = ref(props.carrier)
const vehicles = ref([])
const drivers = ref([])
const loading = ref(true)
const error = ref('')
const vehDialog = ref(false)
const drvDialog = ref(false)

const cid = computed(() => props.carrier?.id ?? props.carrierId)

const loadLists = async () => {
  const [v, d] = await Promise.all([
    carrierVehiclesService.list({ carrierId: cid.value, pageSize: 200 }),
    carrierDriversService.list({ carrierId: cid.value, pageSize: 200 }),
  ])
  vehicles.value = v.results
  drivers.value = d.results
}

onMounted(async () => {
  try {
    const [c] = await Promise.all([
      info.value ? Promise.resolve(info.value) : carriersService.get(cid.value),
      loadLists(),
    ])
    info.value = c
  } catch (e) {
    error.value = e.message || 'No se pudo cargar el detalle.'
  } finally {
    loading.value = false
  }
})

const dash = v => v || '—'
</script>

<template>
  <VDialog :model-value="true" max-width="760" scrollable @update:model-value="$emit('close')">
    <VCard>
      <VCardTitle class="d-flex align-center justify-space-between">
        <div>
          <span class="text-h6">{{ info?.name || 'Transportista' }}</span>
          <span v-if="info?.documentId" class="text-body-2 text-medium-emphasis ms-2">{{ info.documentId }}</span>
        </div>
        <VBtn icon="ri-close-line" variant="text" size="small" @click="$emit('close')" />
      </VCardTitle>

      <VDivider />
      <VCardText>
        <div v-if="info" class="d-flex flex-wrap ga-2 mb-4">
          <VChip size="small" :color="info.active ? 'success' : 'secondary'">
            {{ info.active ? 'Activo' : 'Inactivo' }}
          </VChip>
          <VChip v-if="info.phone" size="small" variant="tonal" prepend-icon="ri-phone-line">{{ info.phone }}</VChip>
          <VChip v-if="info.email" size="small" variant="tonal" prepend-icon="ri-mail-line">{{ info.email }}</VChip>
          <VChip v-if="info.homeCity" size="small" variant="tonal" prepend-icon="ri-map-pin-line">{{ info.homeCity }}</VChip>
          <VChip v-if="info.isDriver" size="small" variant="tonal" prepend-icon="ri-steering-line">Titular conduce</VChip>
        </div>
        <p v-if="info?.address" class="text-body-2 text-medium-emphasis mb-1">{{ info.address }}</p>
        <p v-if="info?.notes" class="text-body-2 text-medium-emphasis mb-4">{{ info.notes }}</p>

        <VAlert v-if="error" type="error" variant="tonal" density="compact" class="mb-3">{{ error }}</VAlert>
        <div v-if="loading" class="text-center py-6"><VProgressCircular indeterminate color="primary" size="28" /></div>

        <template v-else>
          <div class="d-flex align-center justify-space-between mb-2">
            <span class="text-overline text-medium-emphasis">Vehículos ({{ vehicles.length }})</span>
            <VBtn size="small" variant="tonal" prepend-icon="ri-add-line" @click="vehDialog = true">Agregar vehículo</VBtn>
          </div>
          <VTable v-if="vehicles.length" density="compact" class="mb-4">
            <thead><tr><th>Placa</th><th>Tipo / carrocería</th><th>Marca modelo</th><th>Cap. útil (t)</th><th>Fotos</th><th>Estado</th></tr></thead>
            <tbody>
              <tr v-for="v in vehicles" :key="v.id">
                <td class="font-weight-medium">{{ v.plate }}</td>
                <td>{{ dash(v.vehicleTypeName) }}<span v-if="v.bodyTypeName"> · {{ v.bodyTypeName }}</span></td>
                <td>{{ dash([v.brand, v.model].filter(Boolean).join(' ')) }}</td>
                <td>{{ dash(v.capacityUsefulTons) }}</td>
                <td>
                  <div v-if="v.photos?.some(Boolean)" class="d-flex ga-1">
                    <a v-for="(url, i) in v.photos.filter(Boolean)" :key="i" :href="url" target="_blank">
                      <img :src="url" style="width: 32px; height: 32px; object-fit: cover; border-radius: 4px;" alt="Foto del vehículo">
                    </a>
                  </div>
                  <span v-else class="text-medium-emphasis">—</span>
                </td>
                <td><VChip size="x-small" :color="v.active ? 'success' : 'secondary'">{{ v.active ? 'Activo' : 'Inactivo' }}</VChip></td>
              </tr>
            </tbody>
          </VTable>
          <p v-else class="text-body-2 text-medium-emphasis mb-4">Sin vehículos afiliados.</p>

          <div class="d-flex align-center justify-space-between mb-2">
            <span class="text-overline text-medium-emphasis">Conductores ({{ drivers.length }})</span>
            <VBtn size="small" variant="tonal" prepend-icon="ri-add-line" @click="drvDialog = true">Agregar conductor</VBtn>
          </div>
          <VTable v-if="drivers.length" density="compact">
            <thead><tr><th>Nombre</th><th>DNI</th><th>Teléfono</th><th>Licencia</th><th>Titular</th></tr></thead>
            <tbody>
              <tr v-for="d in drivers" :key="d.id">
                <td class="font-weight-medium">{{ d.name }}</td>
                <td>{{ dash(d.documentId) }}</td>
                <td>{{ dash(d.phone) }}</td>
                <td>{{ d.licenseNumber ? `${d.licenseNumber}${d.licenseCategory ? ` · ${d.licenseCategory}` : ''}` : '—' }}</td>
                <td>{{ d.isOwner ? 'Sí' : '—' }}</td>
              </tr>
            </tbody>
          </VTable>
          <p v-else class="text-body-2 text-medium-emphasis">Sin conductores registrados.</p>
        </template>
      </VCardText>
    </VCard>

    <CarrierVehicleFormDialog
      v-if="vehDialog" :carrier-id="cid" :carrier-name="info?.name || ''"
      @close="vehDialog = false" @saved="loadLists"
    />
    <CarrierDriverFormDialog
      v-if="drvDialog" :carrier-id="cid" :carrier-name="info?.name || ''"
      @close="drvDialog = false" @saved="loadLists"
    />
  </VDialog>
</template>
