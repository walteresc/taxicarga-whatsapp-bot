<script setup>
import { onMounted, reactive, ref } from 'vue'

import { pricingConfigService } from '@/services/pricingConfigService'

const loading = ref(true)
const loadError = ref('')
const saving = ref(false)
const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

// Espeja apps/cotizador/models.py::ConfiguracionPrecios — es el cálculo por
// reglas base (apps/cotizador/pricing.py::fallback_price_for_lead), el que
// se usa cuando no hay suficientes históricos parecidos para cotizar por
// mediana.
const SECTIONS = [
  {
    title: 'Precio base por tipo de servicio',
    hint: 'Punto de partida antes de sumar peso, volumen, pisos, etc.',
    fields: [
      { key: 'base_mudanza', label: 'Mudanza' },
      { key: 'base_carga', label: 'Carga' },
      { key: 'base_traslado_pequeno', label: 'Traslado pequeño' },
      { key: 'base_oficina', label: 'Oficina' },
      { key: 'base_corporativo', label: 'Corporativo' },
      { key: 'base_otros', label: 'Otros (sin base propia arriba)' },
    ],
  },
  {
    title: 'Por unidad de carga',
    fields: [
      { key: 'costo_por_kg', label: 'Costo por kg', decimals: 2 },
      { key: 'costo_por_m3', label: 'Costo por m³' },
      { key: 'costo_por_piso_sin_ascensor', label: 'Por piso sin ascensor' },
    ],
  },
  {
    title: 'Servicios adicionales',
    fields: [
      { key: 'costo_personal_carga', label: 'Personal de carga incluido' },
      { key: 'costo_desarmado', label: 'Desarmado de muebles' },
      { key: 'costo_objeto_pesado', label: 'Por objeto pesado (c/u)' },
      { key: 'costo_camion_no_llega', label: 'Camión no llega a la puerta (por punto)' },
    ],
  },
  {
    title: 'Embalaje',
    hint: 'Según la modalidad de servicio elegida.',
    fields: [
      { key: 'costo_embalaje_basico', label: 'Básico' },
      { key: 'costo_embalaje_completo', label: 'Completo' },
      { key: 'costo_embalaje_full', label: 'Full' },
    ],
  },
  {
    title: 'Descripción larga de la carga',
    hint: 'Proxy de volumen cuando no hay peso/volumen explícito.',
    fields: [
      { key: 'costo_descripcion_media', label: 'Más de 10 palabras' },
      { key: 'costo_descripcion_grande', label: 'Más de 15 palabras' },
      { key: 'costo_descripcion_muy_grande', label: 'Más de 35 palabras' },
    ],
  },
  {
    title: 'Distancia',
    hint: 'Solo aplica si el Lead tiene coordenadas (ya obligatorio en /cotizar y Portal Cliente). En km/km_gratis = 0 la distancia no afecta el precio.',
    fields: [
      { key: 'km_gratis', label: 'Km sin costo adicional (cubiertos por el precio base)', suffix: 'km' },
      { key: 'costo_por_km', label: 'Costo por km después de eso', decimals: 2 },
    ],
  },
  {
    title: 'Otros',
    fields: [
      { key: 'costo_caminata_por_bloque', label: 'Caminata — por bloque de 25m (más allá de 20m)' },
      { key: 'rango_min_pct', label: 'Rango mostrado — piso (%)', suffix: '%' },
      { key: 'rango_max_pct', label: 'Rango mostrado — techo (%)', suffix: '%' },
    ],
  },
]

const form = reactive({})

const load = async () => {
  loading.value = true
  loadError.value = ''
  try {
    Object.assign(form, await pricingConfigService.get())
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
    Object.assign(form, await pricingConfigService.update({ ...form }))
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
    <h1 class="text-h4 font-weight-bold mb-1">Configuración de precios</h1>
    <p class="text-body-2 text-medium-emphasis mb-6" style="max-width: 70ch;">
      Parámetros del cálculo por reglas base — el que se usa cuando no hay suficientes históricos parecidos
      para cotizar por mediana. Los cambios aplican a la próxima cotización, no recalculan las ya hechas.
    </p>

    <VProgressLinear v-if="loading" indeterminate class="mb-4" />
    <VAlert v-else-if="loadError" type="error" variant="tonal" class="mb-4">{{ loadError }}</VAlert>

    <VRow v-else>
      <VCol v-for="section in SECTIONS" :key="section.title" cols="12" md="6">
        <VCard class="mb-4">
          <VCardText>
            <p class="text-overline mb-1">{{ section.title }}</p>
            <p v-if="section.hint" class="text-caption text-medium-emphasis mb-3">{{ section.hint }}</p>
            <VTextField
              v-for="f in section.fields" :key="f.key" v-model.number="form[f.key]" :label="f.label"
              type="number" :step="f.decimals === 2 ? '0.01' : '1'" density="comfortable" class="mb-1"
              :prefix="f.suffix ? undefined : 'S/'" :suffix="f.suffix"
            />
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

    <VBtn v-if="!loading && !loadError" color="primary" size="large" :loading="saving" @click="save">
      Guardar cambios
    </VBtn>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
