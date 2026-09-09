<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { ApiError } from '@/services/apiClient'
import { carrierDriversService, LICENSE_CATEGORIES } from '@/services/carriersService'

const props = defineProps({
  carrierId: { type: [Number, String], required: true },
  carrierName: { type: String, default: '' },
  driver: { type: Object, default: null }, // fila para editar; null = alta
})
const emit = defineEmits(['close', 'saved'])

const saving = ref(false)
const errs = ref({})
const editing = computed(() => !!props.driver)
const form = reactive({
  name: '', documentId: '', phone: '', licenseNumber: '', licenseCategory: null,
  licenseExpiresOn: '', isOwner: false, active: true,
})

onMounted(() => {
  if (props.driver) {
    Object.assign(form, {
      name: props.driver.name, documentId: props.driver.documentId,
      phone: props.driver.phone || '', licenseNumber: props.driver.licenseNumber || '',
      licenseCategory: props.driver.licenseCategory || null,
      licenseExpiresOn: props.driver.licenseExpiresOn || '',
      isOwner: props.driver.isOwner ?? false, active: props.driver.active ?? true,
    })
  }
})

const submit = async () => {
  saving.value = true
  errs.value = {}
  const payload = {
    carrierId: props.carrierId,
    name: form.name,
    documentId: form.documentId,
    phone: form.phone,
    licenseNumber: form.licenseNumber,
    licenseCategory: form.licenseCategory || '',
    licenseExpiresOn: form.licenseExpiresOn || null,
    isOwner: form.isOwner,
    active: form.active,
  }
  try {
    if (editing.value) await carrierDriversService.update(props.driver.id, payload)
    else await carrierDriversService.create(payload)
    emit('saved')
    emit('close')
  } catch (e) {
    if (e instanceof ApiError && Object.keys(e.fields).length) errs.value = e.fields
    else errs.value = { name: e.message || 'No se pudo guardar.' }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <VDialog :model-value="true" max-width="560" persistent @update:model-value="$emit('close')">
    <VCard>
      <VCardTitle>{{ editing ? 'Editar conductor' : 'Nuevo conductor' }}<span v-if="carrierName"> · {{ carrierName }}</span></VCardTitle>
      <VCardText>
        <VRow>
          <VCol cols="12"><VTextField v-model="form.name" label="Nombre completo" :error-messages="errs.name" /></VCol>
          <VCol cols="12" sm="6"><VTextField v-model="form.documentId" label="DNI" :error-messages="errs.documentId" /></VCol>
          <VCol cols="12" sm="6"><VTextField v-model="form.phone" label="Teléfono" :error-messages="errs.phone" /></VCol>
          <VCol cols="12" sm="6"><VTextField v-model="form.licenseNumber" label="N° de licencia" :error-messages="errs.licenseNumber" /></VCol>
          <VCol cols="12" sm="6">
            <VSelect v-model="form.licenseCategory" :items="LICENSE_CATEGORIES" label="Categoría" clearable :error-messages="errs.licenseCategory" />
          </VCol>
          <VCol cols="12" sm="6">
            <AppDateField v-model="form.licenseExpiresOn" label="Vencimiento de licencia" density="comfortable" clearable :error-messages="errs.licenseExpiresOn" />
          </VCol>
          <VCol cols="12" sm="6" class="d-flex align-center"><VSwitch v-model="form.isOwner" label="Es el titular" color="primary" hide-details /></VCol>
          <VCol cols="12"><VSwitch v-model="form.active" label="Activo" color="primary" /></VCol>
        </VRow>
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" :disabled="saving" @click="$emit('close')">Cancelar</VBtn>
        <VBtn color="primary" :loading="saving" :disabled="!form.name || !form.documentId" @click="submit">Guardar</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
