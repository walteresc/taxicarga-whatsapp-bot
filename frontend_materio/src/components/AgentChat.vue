<script setup>
import { nextTick, onMounted, reactive, ref } from 'vue'

import {
  agentAsk, agentProposalApply, agentProposalReject, agentStatus,
} from '@/services/agentService'

const STORE_KEY = 'agent:conversation'

const enabled = ref(false)
const open = ref(false)
const busy = ref(false)
const draft = ref('')
const conversationId = ref(null)
const messages = ref([])        // { rol: 'usuario'|'agente', texto, propuestas?, ejecutadas? }
const scroller = ref(null)
const snackbar = reactive({ show: false, text: '' })

onMounted(async () => {
  try {
    enabled.value = (await agentStatus()).enabled === true
  } catch { enabled.value = false }
  try {
    const saved = Number(localStorage.getItem(STORE_KEY))
    if (saved) conversationId.value = saved
  } catch { /* private mode */ }
})

const scrollBottom = () => nextTick(() => {
  const el = scroller.value
  if (el) el.scrollTop = el.scrollHeight
})

const send = async () => {
  const text = draft.value.trim()
  if (!text || busy.value) return
  messages.value.push({ rol: 'usuario', texto: text })
  draft.value = ''
  busy.value = true
  scrollBottom()
  try {
    const r = await agentAsk({ message: text, conversationId: conversationId.value || undefined })
    conversationId.value = r.conversationId
    try { localStorage.setItem(STORE_KEY, String(r.conversationId)) } catch { /* */ }
    messages.value.push({
      rol: 'agente',
      texto: r.reply,
      propuestas: (r.proposals || []).map(p => ({ ...p, estado: 'pendiente' })),
      ejecutadas: (r.executed || []).filter(e => e.ok).map(e => e.capacidad),
    })
  } catch (e) {
    messages.value.push({ rol: 'agente', texto: e.message || 'No pude responder. Probá de nuevo.' })
  } finally {
    busy.value = false
    scrollBottom()
  }
}

const resolver = async (msg, prop, accion) => {
  prop.estado = 'procesando'
  try {
    if (accion === 'apply') {
      const r = await agentProposalApply(prop.id)
      prop.estado = r.ok ? 'aplicada' : 'rechazada'
      snackbar.text = r.ok ? 'Acción confirmada.' : (r.error || 'No se pudo aplicar.')
    } else {
      await agentProposalReject(prop.id, '')
      prop.estado = 'rechazada'
      snackbar.text = 'Propuesta descartada.'
    }
  } catch (e) {
    prop.estado = 'pendiente'
    snackbar.text = e.message || 'Error.'
  }
  snackbar.show = true
}

const nuevaConversacion = () => {
  messages.value = []
  conversationId.value = null
  try { localStorage.removeItem(STORE_KEY) } catch { /* */ }
}
</script>

<template>
  <div v-if="enabled" class="agent-chat">
    <!-- Panel -->
    <VCard v-if="open" class="agent-panel d-flex flex-column" elevation="12">
      <div class="d-flex align-center px-4 py-2" style="border-bottom: 1px solid rgba(var(--v-border-color), .12);">
        <VIcon icon="ri-robot-2-line" class="me-2" />
        <span class="font-weight-medium">Asistente</span>
        <VSpacer />
        <VBtn icon="ri-add-line" size="x-small" variant="text" title="Nueva conversación" @click="nuevaConversacion" />
        <VBtn icon="ri-subtract-line" size="x-small" variant="text" title="Minimizar" @click="open = false" />
      </div>

      <div ref="scroller" class="agent-messages flex-grow-1 pa-3">
        <div v-if="!messages.length" class="text-caption text-medium-emphasis text-center py-6">
          Preguntame por una carga, una negociación, un precio…
        </div>
        <div v-for="(m, i) in messages" :key="i" class="mb-3 d-flex" :class="m.rol === 'usuario' ? 'justify-end' : 'justify-start'">
          <div style="max-width: 85%;">
            <VCard
              :color="m.rol === 'usuario' ? 'primary' : undefined"
              :variant="m.rol === 'usuario' ? 'flat' : 'tonal'"
              class="px-3 py-2 text-body-2" style="white-space: pre-wrap;"
            >
              {{ m.texto }}
            </VCard>

            <div v-if="m.ejecutadas && m.ejecutadas.length" class="text-caption text-medium-emphasis mt-1">
              <VIcon icon="ri-check-line" size="12" /> {{ m.ejecutadas.join(', ') }}
            </div>

            <VCard
              v-for="p in (m.propuestas || [])" :key="p.id"
              variant="outlined" class="mt-2 px-3 py-2"
            >
              <div class="text-caption text-medium-emphasis mb-1">Requiere tu confirmación</div>
              <div class="text-body-2 mb-2">{{ p.resumen }}</div>
              <div v-if="p.estado === 'pendiente'" class="d-flex ga-2">
                <VBtn size="x-small" color="success" @click="resolver(m, p, 'apply')">Confirmar</VBtn>
                <VBtn size="x-small" variant="text" @click="resolver(m, p, 'reject')">Descartar</VBtn>
              </div>
              <VChip v-else size="x-small" :color="p.estado === 'aplicada' ? 'success' : 'default'">
                {{ p.estado === 'procesando' ? 'Procesando…' : (p.estado === 'aplicada' ? 'Confirmada' : 'Descartada') }}
              </VChip>
            </VCard>
          </div>
        </div>
        <div v-if="busy" class="text-caption text-medium-emphasis">
          <VProgressCircular indeterminate size="14" width="2" class="me-1" /> pensando…
        </div>
      </div>

      <div class="pa-2" style="border-top: 1px solid rgba(var(--v-border-color), .12);">
        <VTextarea
          v-model="draft" placeholder="Escribí un mensaje…" rows="1" auto-grow max-rows="4"
          density="compact" hide-details variant="solo-filled" flat
          append-inner-icon="ri-send-plane-2-line"
          @click:append-inner="send"
          @keydown.enter.exact.prevent="send"
        />
      </div>
    </VCard>

    <!-- Botón flotante -->
    <VBtn
      icon :color="open ? 'default' : 'primary'" size="large" elevation="8"
      class="agent-fab"
      @click="open = !open"
    >
      <VIcon :icon="open ? 'ri-close-line' : 'ri-robot-2-line'" />
    </VBtn>

    <VSnackbar v-model="snackbar.show" timeout="3000" location="bottom end">{{ snackbar.text }}</VSnackbar>
  </div>
</template>

<style scoped>
.agent-fab {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 2400;
}
.agent-panel {
  position: fixed;
  right: 20px;
  bottom: 88px;
  z-index: 2400;
  width: 380px;
  max-width: calc(100vw - 40px);
  height: 540px;
  max-height: calc(100vh - 120px);
  border-radius: 14px;
  overflow: hidden;
}
.agent-messages {
  overflow-y: auto;
}
@media (max-width: 480px) {
  .agent-panel { width: calc(100vw - 32px); right: 16px; bottom: 84px; }
  .agent-fab { right: 16px; bottom: 16px; }
}
</style>
