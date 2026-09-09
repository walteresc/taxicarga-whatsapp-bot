<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { ApiError } from '@/services/apiClient'
import { carrierVehiclesService, fetchVehicleCatalog } from '@/services/carriersService'

const props = defineProps({
  carrierId: { type: [Number, String], required: true },
  carrierName: { type: String, default: '' },
  vehicle: { type: Object, default: null }, // fila para editar; null = alta
})
const emit = defineEmits(['close', 'saved'])

const vehicleTypes = ref([])
const bodyTypes = ref([])
const saving = ref(false)
const errs = ref({})

const editing = computed(() => !!props.vehicle)
const form = reactive({
  plate: '', vehicleTypeId: null, bodyTypeId: null,
  brand: '', model: '', year: '', capacityUsefulTons: '',
  lengthUsefulM: '', widthUsefulM: '', heightUsefulM: '', active: true,
})

onMounted(async () => {
  try {
    const cat = await fetchVehicleCatalog()
    vehicleTypes.value = cat.vehicleTypes
    bodyTypes.value = cat.bodyTypes
  } catch { /* */ }
  if (props.vehicle) {
    Object.assign(form, {
      plate: props.vehicle.plate, vehicleTypeId: props.vehicle.vehicleTypeId,
      bodyTypeId: props.vehicle.bodyTypeId,
      brand: props.vehicle.brand || '', model: props.vehicle.model || '',
      year: props.vehicle.year ?? '', capacityUsefulTons: props.vehicle.capacityUsefulTons ?? '',
      lengthUsefulM: props.vehicle.lengthUsefulM ?? '',
      widthUsefulM: props.vehicle.widthUsefulM ?? '',
      heightUsefulM: props.vehicle.heightUsefulM ?? '',
      active: props.vehicle.active ?? true,
    })
  }
})

const typeOptions = computed(() => vehicleTypes.value.map(t => ({ title: t.name, value: t.id })))
const selType = computed(() => vehicleTypes.value.find(t => t.id === form.vehicleTypeId))
const bodyOptions = computed(() => {
  const ids = new Set((selType.value?.compatibleBodyTypes || []).map(c => c.id))
  return bodyTypes.value.filter(b => ids.has(b.id)).map(b => ({ title: b.name, value: b.id }))
})
const bodyNA = computed(() => selType.value && !(selType.value.compatibleBodyTypes || []).length)
const numOrNull = v => (v === '' || v == null ? null : Number(v))

const submit = async () => {
  saving.value = true
  errs.value = {}
  const payload = {
    carrierId: props.carrierId,
    plate: form.plate,
    vehicleTypeId: form.vehicleTypeId,
    bodyTypeId: bodyNA.value ? null : form.bodyTypeId,
    brand: form.brand,
    model: form.model,
    year: numOrNull(form.year),
    capacityUsefulTons: numOrNull(form.capacityUsefulTons),
    lengthUsefulM: numOrNull(form.lengthUsefulM),
    widthUsefulM: numOrNull(form.widthUsefulM),
    heightUsefulM: numOrNull(form.heightUsefulM),
    active: form.active,
  }
  try {
    if (editing.value) await carrierVehiclesService.update(props.vehicle.id, payload)
    else await carrierVehiclesService.create(payload)
    emit('saved')
    emit('close')
  } catch (e) {
    if (e instanceof ApiError && Object.keys(e.fields).length) errs.value = e.fields
    else errs.value = { plate: e.message || 'No se pudo guardar.' }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <VDialog :model-value="true" max-width="560" persistent @update:model-value="$emit('close')">
    <VCard>
      <VCardTitle>{{ editing ? 'Editar vehículo' : 'Nuevo vehículo' }}<span v-if="carrierName"> · {{ carrierName }}</span></VCardTitle>
      <VCardText>
        <VRow>
          <VCol cols="12" sm="6"><VTextField v-model="form.plate" label="Placa" :error-messages="errs.plate" /></VCol>
          <VCol cols="12" sm="6">
            <VSelect v-model="form.vehicleTypeId" :items="typeOptions" label="Tipo de vehículo" :error-messages="errs.vehicleTypeId" />
          </VCol>
          <VCol cols="12" sm="6">
            <VSelect
              v-model="form.bodyTypeId" :items="bodyOptions" label="Carrocería"
              :disabled="!form.vehicleTypeId || bodyNA" clearable
              :hint="bodyNA ? 'Este tipo no lleva carrocería' : ''" persistent-hint
              :error-messages="errs.bodyTypeId"
            />
          </VCol>
          <VCol cols="6" sm="3"><VTextField v-model="form.brand" label="Marca" :error-messages="errs.brand" /></VCol>
          <VCol cols="6" sm="3"><VTextField v-model="form.model" label="Modelo" :error-messages="errs.model" /></VCol>
          <VCol cols="6" sm="3"><VTextField v-model="form.year" label="Año" type="number" :error-messages="errs.year" /></VCol>
          <VCol cols="6" sm="3"><VTextField v-model="form.capacityUsefulTons" label="Cap. útil (t)" type="number" :error-messages="errs.capacityUsefulTons" /></VCol>
          <VCol cols="12" class="pb-0"><div class="text-caption text-medium-emphasis">Dimensiones útiles (m)</div></VCol>
          <VCol cols="4"><VTextField v-model="form.lengthUsefulM" label="Largo" type="number" :error-messages="errs.lengthUsefulM" /></VCol>
          <VCol cols="4"><VTextField v-model="form.widthUsefulM" label="Ancho" type="number" :error-messages="errs.widthUsefulM" /></VCol>
          <VCol cols="4"><VTextField v-model="form.heightUsefulM" label="Alto" type="number" :error-messages="errs.heightUsefulM" /></VCol>
          <VCol cols="12"><VSwitch v-model="form.active" label="Activo" color="primary" /></VCol>
        </VRow>
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" :disabled="saving" @click="$emit('close')">Cancelar</VBtn>
        <VBtn color="primary" :loading="saving" :disabled="!form.plate || !form.vehicleTypeId" @click="submit">Guardar</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
