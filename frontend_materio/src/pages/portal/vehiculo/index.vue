<script setup>
import { onMounted, reactive, ref } from 'vue'

import { carrierVehiclePhotosUpload, carrierVehicles } from '@/services/portalService'

const vehicles = ref([])
const loading = ref(true)
const busySlot = reactive({})   // `${vehicleId}-${slot}` -> true mientras sube
const cacheBust = ref(Date.now())   // fuerza recargar la <img> tras reemplazar una foto
const snack = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snack, { show: true, text: t, color: c })

const load = async () => {
  loading.value = true
  try { vehicles.value = (await carrierVehicles()).results }
  catch (e) { notify(e.message || 'No se pudo cargar.', 'error') }
  finally { loading.value = false }
}
onMounted(load)

const inputs = {}   // `${vehicleId}-${slot}` -> <input type=file> ref
const setInputRef = (key, el) => { if (el) inputs[key] = el }
const openPicker = (vehicleId, slot) => inputs[`${vehicleId}-${slot}`]?.click()

const onPick = async (vehicle, slot, event) => {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  const key = `${vehicle.id}-${slot}`
  busySlot[key] = true
  try {
    const fd = new FormData()
    fd.append(`photo${slot}`, file)
    const updated = await carrierVehiclePhotosUpload(vehicle.id, fd)
    vehicle.photos = updated.photos
    cacheBust.value = Date.now()
    notify('Foto subida.')
  } catch (e) { notify(e.message || 'No se pudo subir la foto.', 'error') }
  finally { busySlot[key] = false }
}
</script>

<template>
  <section>
    <h1 class="text-h5 font-weight-bold mb-1">Mi vehículo</h1>
    <p class="text-body-2 text-medium-emphasis mb-4">
      Subí 3 fotos de tu camión (exterior, carrocería, interior de carga) para que el asesor sepa con qué unidad
      está tratando.
    </p>

    <VProgressLinear v-if="loading" indeterminate />
    <div v-else-if="!vehicles.length" class="text-center text-medium-emphasis py-10 text-body-2">
      Todavía no tenés un vehículo registrado — pedile a tu asesor que te lo cargue.
    </div>

    <VCard v-for="vehicle in vehicles" v-else :key="vehicle.id" class="mb-4">
      <VCardText>
        <div class="d-flex align-center ga-2 mb-3 flex-wrap">
          <span class="text-subtitle-1 font-weight-bold">{{ vehicle.plate }}</span>
          <span v-if="vehicle.brand || vehicle.model" class="text-body-2 text-medium-emphasis">
            {{ [vehicle.brand, vehicle.model, vehicle.year].filter(Boolean).join(' · ') }}
          </span>
        </div>

        <VRow>
          <VCol v-for="slot in [1, 2, 3]" :key="slot" cols="12" sm="4">
            <input
              :ref="el => setInputRef(`${vehicle.id}-${slot}`, el)"
              type="file" accept="image/*" capture="environment" class="d-none"
              @change="e => onPick(vehicle, slot, e)"
            >
            <VCard
              variant="outlined" class="d-flex align-center justify-center position-relative"
              style="height: 160px; cursor: pointer;" @click="openPicker(vehicle.id, slot)"
            >
              <VProgressCircular v-if="busySlot[`${vehicle.id}-${slot}`]" indeterminate color="primary" />
              <img
                v-else-if="vehicle.photos[slot - 1]" :src="`${vehicle.photos[slot - 1]}?t=${cacheBust}`"
                style="width: 100%; height: 100%; object-fit: cover;" :alt="`Foto ${slot}`"
              >
              <div v-else class="text-center text-medium-emphasis">
                <VIcon icon="ri-camera-line" size="32" />
                <div class="text-caption">Foto {{ slot }}</div>
              </div>
            </VCard>
          </VCol>
        </VRow>
      </VCardText>
    </VCard>

    <VSnackbar v-model="snack.show" :color="snack.color" timeout="2500">{{ snack.text }}</VSnackbar>
  </section>
</template>
