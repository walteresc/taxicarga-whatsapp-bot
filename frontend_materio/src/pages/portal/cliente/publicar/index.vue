<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import AddressAutocomplete from '@/components/AddressAutocomplete.vue'
import { customerPublish } from '@/services/customerPortalService'

const router = useRouter()

const CATEGORIES = [
  { title: 'Mudanza, muebles y electrodomésticos', value: 'mudanza' },
  { title: 'Cajas, paquetes y bultos', value: 'cajas' },
  { title: 'Mercadería comercial', value: 'mercaderia' },
  { title: 'Maquinaria y equipos', value: 'maquinaria' },
  { title: 'Materiales de construcción', value: 'construccion' },
  { title: 'Pallets / parihuelas', value: 'pallets' },
  { title: 'Otros', value: 'otros' },
]
const TRUCKS = [
  { title: 'Furgón pequeño (hasta 1 ton)', value: 'furgon_1t' },
  { title: 'Camión 2 ton', value: 'camion_2t' },
  { title: 'Camión 4 ton', value: 'camion_4t' },
  { title: 'Camión 8 ton', value: 'camion_8t' },
]

const step = ref(1)
const form = reactive({
  origin: { district: '', address: '', floor: null, province: '', region: '', lat: null, lng: null },
  destination: { district: '', address: '', floor: null, province: '', region: '', lat: null, lng: null },
  cargo: { category: 'mudanza', detail: '', weightKg: '', volumeM3: '', operators: null, truckType: 'camion_2t' },
  date: '',
  schedule: '',
  quoteMode: 'por_carga',
  loadMode: 'completa',   // completa|parcial — solo importa si la ruta es nacional
})

const submitting = ref(false)
const result = ref(null)
const error = ref('')

const step1ok = computed(() => form.origin.district && form.origin.address && form.destination.district && form.destination.address)
const step2ok = computed(() => form.quoteMode === 'por_vehiculo' ? !!form.cargo.truckType : !!form.cargo.category)

const submit = async () => {
  submitting.value = true
  error.value = ''
  try {
    result.value = await customerPublish({ ...form })
    step.value = 4
  } catch (e) { error.value = e.message || 'No se pudo publicar.' } finally { submitting.value = false }
}
const soles = n => (n == null ? null : `S/ ${Math.round(n).toLocaleString('es-PE')}`)
</script>

<template>
  <div>
    <h1 class="text-h5 font-weight-bold mb-4">Publicar carga</h1>

    <VCard>
      <VCardText>
        <VStepper v-model="step" flat :items="['Direcciones', 'Carga', 'Confirmar', 'Precio']" hide-actions>
          <template #item.1>
            <div class="text-subtitle-2 mb-2">Origen</div>
            <AddressAutocomplete v-model="form.origin" label="Dirección de origen" />
            <VTextField v-model.number="form.origin.floor" label="Piso (opcional)" type="number" class="mb-4" />
            <div class="text-subtitle-2 mb-2">Destino</div>
            <AddressAutocomplete v-model="form.destination" label="Dirección de destino" />
            <VTextField v-model.number="form.destination.floor" label="Piso (opcional)" type="number" />
          </template>

          <template #item.2>
            <VBtnToggle v-model="form.quoteMode" mandatory density="comfortable" class="mb-4">
              <VBtn value="por_carga">Describir la carga</VBtn>
              <VBtn value="por_vehiculo">Elegir vehículo</VBtn>
            </VBtnToggle>

            <template v-if="form.quoteMode === 'por_carga'">
              <VSelect v-model="form.cargo.category" :items="CATEGORIES" label="Tipo de carga" class="mb-2" />
              <VTextarea v-model="form.cargo.detail" label="¿Qué vas a mover? (detalle)" rows="2" auto-grow class="mb-2" />
              <div class="d-flex ga-2">
                <VTextField v-model="form.cargo.weightKg" label="Peso aprox. (kg)" type="number" />
                <VTextField v-model="form.cargo.volumeM3" label="Volumen aprox. (m³)" type="number" />
              </div>
              <VTextField v-model.number="form.cargo.operators" label="¿Necesitás operarios de carga? ¿Cuántos?" type="number" />
            </template>
            <template v-else>
              <VSelect v-model="form.cargo.truckType" :items="TRUCKS" label="Tipo de vehículo" class="mb-2" />
              <VTextarea v-model="form.cargo.detail" label="Detalle (opcional)" rows="2" auto-grow />
            </template>

            <template v-if="form.origin.district && form.destination.district">
              <div class="text-caption text-medium-emphasis mb-1 mt-2">
                Si tu carga es a otra ciudad, elegí cómo la enviamos (si es dentro de Lima, no aplica):
              </div>
              <VBtnToggle v-model="form.loadMode" mandatory density="comfortable" class="mb-2" divided>
                <VBtn value="completa" size="small">Completa (camión dedicado, más rápido)</VBtn>
                <VBtn value="parcial" size="small">Parcial (comparte camión, más económico)</VBtn>
              </VBtnToggle>
            </template>

            <VDivider class="my-3" />
            <div class="d-flex ga-2">
              <VTextField v-model="form.date" label="Fecha" type="date" />
              <VTextField v-model="form.schedule" label="Horario (ej. 09:00)" />
            </div>
          </template>

          <template #item.3>
            <VList density="compact">
              <VListItem prepend-icon="ri-map-pin-line" :title="`${form.origin.district} → ${form.destination.district}`" :subtitle="`${form.origin.address} → ${form.destination.address}`" />
              <VListItem prepend-icon="ri-archive-line" :title="form.quoteMode === 'por_vehiculo' ? TRUCKS.find(t => t.value === form.cargo.truckType)?.title : CATEGORIES.find(c => c.value === form.cargo.category)?.title" :subtitle="form.cargo.detail || '—'" />
              <VListItem prepend-icon="ri-calendar-line" :title="form.date || 'Fecha por confirmar'" :subtitle="form.schedule || 'Horario por confirmar'" />
            </VList>
            <VAlert v-if="error" type="error" variant="tonal" class="mt-3">{{ error }}</VAlert>
          </template>

          <template #item.4>
            <div v-if="result" class="text-center py-4">
              <VIcon icon="ri-checkbox-circle-line" color="success" size="48" class="mb-2" />
              <div class="text-h6">Carga {{ result.code }} publicada</div>
              <div v-if="soles(result.price?.amount)" class="text-h5 font-weight-bold my-2">{{ soles(result.price.amount) }}</div>
              <div v-else class="text-body-2 text-medium-emphasis my-2">Un asesor te confirmará el precio pronto.</div>
              <div v-if="result.price?.daysEstimated" class="text-caption text-medium-emphasis">
                Llega en {{ result.price.daysEstimated }} días hábiles aprox.
              </div>
              <VBtn color="primary" class="mt-2" @click="router.push(`/portal/cliente/carga/${result.code}`)">Ver carga</VBtn>
            </div>
          </template>
        </VStepper>
      </VCardText>

      <VCardActions v-if="step < 4" class="px-4 pb-4">
        <VBtn v-if="step > 1" variant="text" @click="step--">Atrás</VBtn>
        <VSpacer />
        <VBtn v-if="step === 1" color="primary" :disabled="!step1ok" @click="step = 2">Siguiente</VBtn>
        <VBtn v-else-if="step === 2" color="primary" :disabled="!step2ok" @click="step = 3">Siguiente</VBtn>
        <VBtn v-else-if="step === 3" color="primary" :loading="submitting" @click="submit">Publicar y cotizar</VBtn>
      </VCardActions>
    </VCard>
  </div>
</template>
