<script setup>
import { onMounted, reactive, ref } from 'vue'

import { botConfigService } from '@/services/botConfigService'

const loading = ref(true)
const loadError = ref('')
const status = ref(null) // { customers, carriers, operations }
const acting = reactive({ customers: false, carriers: false, operations: false })
const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

const load = async () => {
  loading.value = true
  loadError.value = ''
  try {
    status.value = await botConfigService.getStatus()
  } catch (e) {
    loadError.value = e.message || 'No se pudo cargar el estado del bot.'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const fmt = iso => iso ? new Date(iso).toLocaleString('es-PE') : ''

const CARDS = [
  {
    key: 'customers',
    title: 'Bot de conversaciones',
    description: 'Responde por WhatsApp a los clientes. Al pausarlo, el bot deja de contestar — la bandeja sigue mostrando los mensajes y un asesor puede tomar la conversación en cualquier momento.',
    pause: () => botConfigService.pauseCustomers(),
    resume: () => botConfigService.resumeCustomers(),
  },
  {
    key: 'carriers',
    title: 'Bot de transportistas',
    description: 'Responde a los transportistas en apps/tercerizacion (ofertas de carga). Independiente del bot de clientes: puedes tener uno activo y el otro pausado.',
    pause: () => botConfigService.pauseCarriers(),
    resume: () => botConfigService.resumeCarriers(),
  },
  {
    key: 'operations',
    title: 'Bot operativo',
    description: 'El trabajo interno del CRM: captura los datos de la conversación, crea o actualiza el Lead, y deriva a "Para revisión" cuando corresponde. No envía ni responde nada — puede seguir activo aunque el bot de conversaciones esté pausado. Al pausarlo se detiene todo ese trabajo, incluida la derivación automática.',
    pause: () => botConfigService.pauseOperations(),
    resume: () => botConfigService.resumeOperations(),
  },
]

const toggle = async card => {
  acting[card.key] = true
  try {
    const paused = status.value?.[card.key]?.paused
    await (paused ? card.resume() : card.pause())
    await load()
    notify(`${card.title}: ${paused ? 'reanudado' : 'pausado'}.`)
  } catch (e) {
    notify(e.message || 'No se pudo cambiar el estado.', 'error')
  } finally {
    acting[card.key] = false
  }
}
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">
      Configuración del bot
    </h1>
    <p class="text-body-2 text-medium-emphasis mb-6">
      Tres interruptores independientes. Pausar uno no afecta a los otros dos.
    </p>

    <VProgressLinear v-if="loading" indeterminate class="mb-4" />
    <VAlert v-else-if="loadError" type="error" variant="tonal" class="mb-4">
      {{ loadError }}
    </VAlert>

    <VRow v-else-if="status">
      <VCol v-for="card in CARDS" :key="card.key" cols="12" md="4">
        <VCard :color="status[card.key].paused ? undefined : 'success'" :variant="status[card.key].paused ? 'outlined' : 'tonal'">
          <VCardText>
            <div class="d-flex align-center justify-space-between mb-2">
              <span class="text-subtitle-1 font-weight-bold">{{ card.title }}</span>
              <VChip :color="status[card.key].paused ? 'error' : 'success'" size="small" variant="flat">
                {{ status[card.key].paused ? 'Pausado' : 'Activo' }}
              </VChip>
            </div>
            <p class="text-body-2 text-medium-emphasis mb-3">
              {{ card.description }}
            </p>
            <p v-if="card.key === 'carriers' && !status.carriers.enabledInDeployment" class="text-caption text-warning mb-3">
              ⚠ Deshabilitado a nivel de despliegue (TRANSPORTISTA_BOT_ENABLED) — este interruptor no tiene efecto hasta que se habilite ahí.
            </p>
            <p v-if="status[card.key].pausedAt" class="text-caption text-medium-emphasis mb-3">
              Pausado desde: {{ fmt(status[card.key].pausedAt) }}
            </p>
            <VBtn
              block
              :color="status[card.key].paused ? 'success' : 'error'"
              :loading="acting[card.key]"
              @click="toggle(card)"
            >
              {{ status[card.key].paused ? 'Reanudar' : 'Pausar' }}
            </VBtn>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">
      {{ snackbar.text }}
    </VSnackbar>
  </section>
</template>
