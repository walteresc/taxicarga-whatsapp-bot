<script setup>
// Nombre y logo mostrados al cliente (sidebar, login, cotizador) — dato de
// negocio, no una variable de entorno: se guarda en base de datos y se ve
// reflejado al toque, sin rebuild ni redeploy. Ver
// apps/dashboard/models.py::ConfiguracionMarca y frontend_materio/src/stores/brandStore.js
// (el store que el resto de la app lee para mostrar el nombre/logo actual).
import { onMounted, reactive, ref } from 'vue'

import { brandConfig, updateBrand } from '@/services/brandService'
import { useBrandStore } from '@/stores/brandStore'
import { BRAND_NAME as DEFAULT_BRAND_NAME } from '@/utils/brand'

const brand = useBrandStore()

const loading = ref(true)
const loadError = ref('')
const saving = ref(false)
const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

const form = reactive({ name: '' })
const currentLogoUrl = ref(null)   // el que ya está guardado
const logoFile = ref(null)         // el que se acaba de elegir (todavía sin guardar)
const logoPreview = ref(null)      // object URL del archivo recién elegido
const removeLogo = ref(false)
const fileInput = ref(null)

const load = async () => {
  loading.value = true
  loadError.value = ''
  try {
    const data = await brandConfig()
    form.name = data.name || ''
    currentLogoUrl.value = data.logoUrl
  } catch (e) {
    loadError.value = e.message || 'No se pudo cargar la configuración.'
  } finally {
    loading.value = false
  }
}
onMounted(load)

const openPicker = () => fileInput.value?.click()
const onPick = e => {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  logoFile.value = file
  logoPreview.value = URL.createObjectURL(file)
  removeLogo.value = false
}
const clearLogo = () => {
  logoFile.value = null
  logoPreview.value = null
  removeLogo.value = true
}

const save = async () => {
  saving.value = true
  try {
    const data = await updateBrand({
      name: form.name.trim(),
      logoFile: logoFile.value,
      removeLogo: removeLogo.value,
    })
    brand.setFromConfig(data)
    currentLogoUrl.value = data.logoUrl
    logoFile.value = null
    logoPreview.value = null
    removeLogo.value = false
    notify('Marca actualizada.')
  } catch (e) {
    notify(e.message || 'No se pudo guardar.', 'error')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">Marca</h1>
    <p class="text-body-2 text-medium-emphasis mb-6" style="max-width: 70ch;">
      Nombre y logo que ve el cliente (sidebar, pantalla de acceso, cotizador). Se aplica al instante, sin
      necesidad de un nuevo despliegue.
    </p>

    <VProgressLinear v-if="loading" indeterminate class="mb-4" />
    <VAlert v-else-if="loadError" type="error" variant="tonal" class="mb-4">{{ loadError }}</VAlert>

    <VRow v-else>
      <VCol cols="12" md="7">
        <VCard>
          <VCardText>
            <p class="text-overline mb-2">Nombre</p>
            <VTextField
              v-model="form.name" label="Nombre de marca" density="comfortable" class="mb-1"
              :placeholder="DEFAULT_BRAND_NAME" clearable maxlength="60"
            />
            <p class="text-caption text-medium-emphasis mb-4">
              Vacío = usa "{{ DEFAULT_BRAND_NAME }}" (el nombre por defecto de este servidor).
            </p>

            <VDivider class="mb-4" />

            <p class="text-overline mb-2">Logo</p>
            <input ref="fileInput" type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" class="d-none" @change="onPick">
            <div class="d-flex align-center ga-4">
              <div
                class="d-flex align-center justify-center rounded"
                style="width: 72px; height: 72px; border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); overflow: hidden;"
              >
                <img
                  v-if="logoPreview || (!removeLogo && currentLogoUrl)"
                  :src="logoPreview || currentLogoUrl" alt="" style="max-width: 100%; max-height: 100%;"
                >
                <VIcon v-else icon="ri-image-line" size="28" color="disabled" />
              </div>
              <div class="d-flex flex-column ga-2">
                <VBtn variant="outlined" size="small" prepend-icon="ri-upload-2-line" @click="openPicker">
                  {{ (logoPreview || currentLogoUrl) && !removeLogo ? 'Cambiar logo' : 'Subir logo' }}
                </VBtn>
                <VBtn
                  v-if="(logoPreview || currentLogoUrl) && !removeLogo" variant="text" size="small" color="error"
                  prepend-icon="ri-delete-bin-line" @click="clearLogo"
                >
                  Quitar logo
                </VBtn>
              </div>
            </div>
            <p class="text-caption text-medium-emphasis mt-2 mb-0">
              PNG, JPG, WEBP o SVG — máx. 500 KB. Sin logo propio se muestra el ícono por defecto.
            </p>
          </VCardText>
        </VCard>

        <VBtn color="primary" block class="mt-4" :loading="saving" @click="save">Guardar</VBtn>
      </VCol>
    </VRow>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
