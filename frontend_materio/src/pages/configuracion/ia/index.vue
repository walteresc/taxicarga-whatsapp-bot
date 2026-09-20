<script setup>
import { onMounted, reactive, ref } from 'vue'

import { aiConfigService } from '@/services/aiConfigService'

const loading = ref(true)
const loadError = ref('')
const saving = ref(false)
const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

const PROVIDER_OPTIONS = [
  { title: 'Usar el valor del servidor (.env)', value: '' },
  { title: 'OpenAI', value: 'openai' },
  { title: 'DeepSeek', value: 'deepseek' },
]

// Cada propósito tiene su propio proveedor (puede quedar vacío = sigue al
// "Proveedor general" de abajo) — ver apps/ia/providers.py::provider_name_for.
const PURPOSES = [
  { key: 'extractionProvider', effectiveKey: 'extraction', label: 'Extracción de datos' },
  { key: 'conversationProvider', effectiveKey: 'conversation', label: 'Conversación (agente)' },
  { key: 'copilotProvider', effectiveKey: 'copilot', label: 'Copiloto' },
]

const form = reactive({
  defaultProvider: '', extractionProvider: '', conversationProvider: '', copilotProvider: '',
  openaiModel: '', deepseekModel: '',
})
const effective = ref({ extraction: '', conversation: '', copilot: '' })
const serverDefaults = ref({ provider: '', openaiModel: '', deepseekModel: '' })
const hasOpenaiKey = ref(true)
const hasDeepseekKey = ref(true)

const load = async () => {
  loading.value = true
  loadError.value = ''
  try {
    const data = await aiConfigService.get()
    Object.assign(form, {
      defaultProvider: data.defaultProvider, extractionProvider: data.extractionProvider,
      conversationProvider: data.conversationProvider, copilotProvider: data.copilotProvider,
      openaiModel: data.openaiModel, deepseekModel: data.deepseekModel,
    })
    effective.value = data.effective
    serverDefaults.value = data.serverDefaults
    hasOpenaiKey.value = data.hasOpenaiKey
    hasDeepseekKey.value = data.hasDeepseekKey
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
    const data = await aiConfigService.update({ ...form })
    effective.value = data.effective
    notify('Configuración guardada.')
  } catch (e) {
    notify(e.message || 'No se pudo guardar.', 'error')
  } finally {
    saving.value = false
  }
}

// La key nunca se gestiona acá (queda en .env) — si el proveedor
// EFECTIVAMENTE en uso no tiene credencial cargada en el servidor, se avisa
// en vez de dejar que falle en silencio en la próxima llamada real.
const keyWarning = provider => {
  if (provider === 'openai' && !hasOpenaiKey.value) return 'Falta OPENAI_API_KEY en el servidor.'
  if (provider === 'deepseek' && !hasDeepseekKey.value) return 'Falta DEEPSEEK_API_KEY en el servidor.'
  return ''
}
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">Configuración de IA</h1>
    <p class="text-body-2 text-medium-emphasis mb-6" style="max-width: 70ch;">
      Elegí qué proveedor y modelo usa cada función de IA. La credencial (API key) no se gestiona acá — vive
      solo en el servidor, por seguridad; esta pantalla solo elige cuál usar de las que ya estén cargadas.
    </p>

    <VProgressLinear v-if="loading" indeterminate class="mb-4" />
    <VAlert v-else-if="loadError" type="error" variant="tonal" class="mb-4">{{ loadError }}</VAlert>

    <VRow v-else>
      <VCol cols="12" md="7">
        <VCard class="mb-4">
          <VCardText>
            <p class="text-overline mb-2">Proveedor</p>
            <VSelect
              v-model="form.defaultProvider" :items="PROVIDER_OPTIONS" label="Proveedor general (por defecto)"
              density="comfortable" class="mb-1"
            />
            <p class="text-caption text-medium-emphasis mb-4">
              Aplica a los tres propósitos de abajo salvo que se anule uno en particular.
            </p>
            <VDivider class="mb-4" />

            <template v-for="p in PURPOSES" :key="p.key">
              <VSelect
                v-model="form[p.key]" :items="PROVIDER_OPTIONS" :label="p.label"
                density="comfortable" class="mb-1" :hint="`En uso ahora: ${effective[p.effectiveKey]}`" persistent-hint
              />
              <p
                class="text-caption mb-4"
                :class="keyWarning(effective[p.effectiveKey]) ? 'text-warning' : 'text-medium-emphasis'"
              >
                {{ keyWarning(effective[p.effectiveKey]) || ' ' }}
              </p>
            </template>
          </VCardText>
        </VCard>
      </VCol>

      <VCol cols="12" md="5">
        <VCard>
          <VCardText>
            <p class="text-overline mb-2">Modelo</p>
            <VTextField
              v-model="form.openaiModel" label="Modelo OpenAI" density="comfortable" class="mb-1"
              :placeholder="serverDefaults.openaiModel" clearable
            />
            <p class="text-caption text-medium-emphasis mb-4">
              Vacío = usa {{ serverDefaults.openaiModel }} (del servidor).
            </p>

            <VTextField
              v-model="form.deepseekModel" label="Modelo DeepSeek" density="comfortable" class="mb-1"
              :placeholder="serverDefaults.deepseekModel" clearable
            />
            <p class="text-caption text-medium-emphasis">
              Vacío = usa {{ serverDefaults.deepseekModel }} (del servidor).
            </p>
          </VCardText>
        </VCard>

        <VBtn color="primary" block class="mt-4" :loading="saving" @click="save">Guardar</VBtn>
      </VCol>
    </VRow>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
