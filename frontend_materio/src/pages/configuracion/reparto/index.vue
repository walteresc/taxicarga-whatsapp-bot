<script setup>
import { onMounted, reactive, ref } from 'vue'

import { encomiendasPricingConfigService } from '@/services/encomiendasPricingConfigService'

const loading = ref(true)
const loadError = ref('')
const saving = ref(false)
const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

const form = reactive({
  comision_cod_porcentaje: 0, costo_recojo_domicilio_nacional: 0, costo_entrega_domicilio_nacional: 0,
  envioIncluidoEnCod: true,
})

const load = async () => {
  loading.value = true
  loadError.value = ''
  try {
    Object.assign(form, await encomiendasPricingConfigService.get())
  } catch (e) {
    loadError.value = e.message || 'No se pudo cargar la configuración.'
  } finally {
    loading.value = false
  }
}
onMounted(load)

const save = async () => {
  saving.value = true
  try {
    Object.assign(form, await encomiendasPricingConfigService.update({ ...form }))
    notify('Configuración guardada.')
  } catch (e) {
    notify(e.message || 'No se pudo guardar.', 'error')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">Configuración de Reparto</h1>
    <p class="text-body-2 text-medium-emphasis mb-6" style="max-width: 70ch;">
      Parámetros de Entregas/Encomiendas — el reparto local (zona × zona) ya es puerta a puerta por diseño;
      esto es específico del envío nacional (otra ciudad), donde no hay oficina propia en destino.
    </p>

    <VProgressLinear v-if="loading" indeterminate class="mb-4" />
    <VAlert v-else-if="loadError" type="error" variant="tonal" class="mb-4">{{ loadError }}</VAlert>

    <VRow v-else>
      <VCol cols="12" md="6">
        <VCard class="mb-4">
          <VCardText>
            <p class="text-overline mb-1">Envío nacional — puerta a puerta</p>
            <p class="text-caption text-medium-emphasis mb-3">
              No hay oficina propia en destino: el servicio siempre incluye recojo en el domicilio de origen
              (Lima) y entrega en el domicilio de destino — estos costos se suman siempre al precio de la
              tabla de tarifa nacional (Configuración → Comisiones → Carga nacional), no son opcionales.
            </p>
            <VTextField
              v-model.number="form.costo_recojo_domicilio_nacional" label="Recojo en Lima (origen)"
              type="number" step="0.01" prefix="S/" density="comfortable" class="mb-2"
            />
            <VTextField
              v-model.number="form.costo_entrega_domicilio_nacional" label="Entrega en destino (otra ciudad)"
              type="number" step="0.01" prefix="S/" density="comfortable"
            />
            <p class="text-caption text-medium-emphasis mt-2 mb-0">
              En provincia suele ser más barato que en Lima (menos tráfico, distancias más cortas).
            </p>
          </VCardText>
        </VCard>
      </VCol>

      <VCol cols="12" md="6">
        <VCard>
          <VCardText>
            <p class="text-overline mb-1">Contra-entrega (COD)</p>
            <VTextField
              v-model.number="form.comision_cod_porcentaje" label="Comisión de la plataforma"
              type="number" step="0.01" suffix="%" density="comfortable" class="mb-2"
            />
            <VCheckbox
              v-model="form.envioIncluidoEnCod" density="compact" hide-details
              label="El monto contra-entrega incluye el precio del envío (la plataforma lo retiene)"
            />
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

    <VBtn v-if="!loading && !loadError" color="primary" size="large" class="mt-4" :loading="saving" @click="save">
      Guardar cambios
    </VBtn>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
