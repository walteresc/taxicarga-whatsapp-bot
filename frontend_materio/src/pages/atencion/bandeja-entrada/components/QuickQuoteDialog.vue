<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import { apiClient } from '@/services/apiClient'
import { useEscapeToClose } from '@/composables/useEscapeToClose'
import { usePipelineStore } from '@/stores/pipelineStore'
import QuickRepliesManager from './QuickRepliesManager.vue'
import ServiceSummary from './ServiceSummary.vue'

const props = defineProps({
  leadId: { type: Number, required: true },
  initialMessage: { type: String, default: '' },
  // Resumen + precios ya calculados por la bandeja (_service_data). El modal los
  // muestra tal cual, sin volver a consultar el motor de precios.
  serviceData: { type: Object, default: () => ({}) },
  // Modo panel flotante arrastrable (se abre al frente del modal Ver).
  draggable: { type: Boolean, default: false },
  // Ruta interprovincial: muestra el aviso de que el cotizador automático no es fiable.
  interprovincial: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'done'])

// ── Arrastre del panel ─────────────────────────────────────────────────────
const dragPos = ref({ x: 0, y: 0 })
let dragStart = null
const onDragStart = e => {
  if (!props.draggable || e.target.closest('button, input, textarea, a')) return
  dragStart = { px: e.clientX, py: e.clientY, x: dragPos.value.x, y: dragPos.value.y }
  window.addEventListener('pointermove', onDragMove)
  window.addEventListener('pointerup', onDragEnd)
}
const onDragMove = e => {
  if (!dragStart) return
  dragPos.value = {
    x: dragStart.x + (e.clientX - dragStart.px),
    y: dragStart.y + (e.clientY - dragStart.py),
  }
}
const onDragEnd = () => {
  dragStart = null
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragEnd)
}

const pipelineStore = usePipelineStore()
useEscapeToClose(() => emit('close'), { priority: 20 })

const price = ref('')
const message = ref('')
const busy = ref(false)
const errMsg = ref('')
const messageRef = ref(null)
const priceRef = ref(null)

const templates = ref([])
const selectedIdx = ref(0)      // índice del template elegido, -1 = personalizado
const manualEdit = ref(false)   // el asesor tocó el textarea a mano
const showManager = ref(false)
const stage = ref(null)
const lastQuoted = ref(null)
const fetchedSuggested = ref(null)
const chat = ref({ price: null, includes: null, note: null, accepted: false })

const alreadyQuoted = () => stage.value === 'quotes'
const hasBooking = () => stage.value === 'bookings'
const showInterprovincial = computed(() => props.interprovincial || !!props.serviceData?.is_interprovincial)

// Precios frescos del endpoint /stage — se los pasamos a <ServiceSummary> para
// que muestre lo mismo que el panel derecho sin recalcular nada.
const stageExtra = computed(() => ({
  suggestedPrice: fetchedSuggested.value,
  quotedPrice: lastQuoted.value,
  chatPrice: chat.value.price,
  chatPriceIncludes: chat.value.includes,
  chatPriceNote: chat.value.note,
  chatPriceAccepted: chat.value.accepted,
}))
const onUseSuggested = amount => {
  price.value = String(amount)
  nextTick(() => priceRef.value?.focus())
}
const _money = v => (v != null && v !== '' && !Number.isNaN(Number(v)) ? `S/ ${Number(v).toFixed(2)}` : null)
const suggestedMoney = computed(() => _money(fetchedSuggested.value ?? props.serviceData?.suggested_price))
const quotedMoney = computed(() => _money(lastQuoted.value ?? props.serviceData?.quoted_price))
const suggestedNum = computed(() => fetchedSuggested.value ?? props.serviceData?.suggested_price ?? null)

// Mensajes distintos según el caso: cotización nueva vs re-cotización (ajuste
// de precio sobre una ya enviada).
const templateTipo = computed(() => (alreadyQuoted() ? 'recotizacion' : 'cotizacion'))

// Precio efectivo: lo que el asesor tipeó, o el último monto cotizado si dejó
// el campo vacío (así "re-cotizar sin cambiar precio, solo mensaje" funciona).
const effectivePrice = computed(() => {
  const typed = Number(String(price.value).replace(',', '.'))
  return typed > 0 ? typed : (lastQuoted.value || 0)
})
const priceLabel = computed(() => (effectivePrice.value > 0 ? String(effectivePrice.value) : 'XXX'))
const pricePlaceholder = computed(() =>
  lastQuoted.value != null ? String(lastQuoted.value) : 'Monto',
)

// Texto del template elegido con el precio actual insertado — reactivo: cambia
// solo si el asesor cambia el precio o elige otro mensaje del combo.
const renderedTemplate = computed(() => {
  const tpl = templates.value[selectedIdx.value]
  return tpl ? tpl.replace(/\{precio\}/gi, priceLabel.value) : ''
})

// Mantener el textarea sincronizado con el template + precio, salvo que el
// asesor ya lo haya editado a mano.
watch(renderedTemplate, val => {
  if (!manualEdit.value && val) message.value = val
})

const onMessageInput = () => {
  manualEdit.value = true
}
// Combo de mensajes: valor -1 = editado a mano.
const comboValue = computed({
  get: () => (manualEdit.value ? -1 : selectedIdx.value),
  set: v => {
    if (v >= 0) selectTemplateAt(v)
  },
})
const comboOption = tpl => {
  const t = tpl.replace(/\{precio\}/gi, priceLabel.value).replace(/\s+/g, ' ').trim()
  return t.length > 60 ? `${t.slice(0, 57)}…` : t
}
const selectTemplateAt = i => {
  selectedIdx.value = i
  manualEdit.value = false
  message.value = renderedTemplate.value
  nextTick(() => priceRef.value?.focus())
}
const clearMessage = () => {
  message.value = ''
  manualEdit.value = true
  nextTick(() => messageRef.value?.focus())
}
const onTemplatesSaved = list => {
  templates.value = list
  if (selectedIdx.value >= list.length) selectedIdx.value = 0
  if (!manualEdit.value && list.length) message.value = renderedTemplate.value
}

const loadTemplates = async () => {
  try {
    const r = await fetch(`/dashboard/whatsapp/respuestas-rapidas/?tipo=${templateTipo.value}`, { credentials: 'include' })
    if (r.ok) templates.value = (await r.json()).items || []
  } catch { /* sin plantillas; se puede escribir a mano igual */ }
  selectedIdx.value = 0
  if (props.initialMessage) {
    message.value = props.initialMessage
    manualEdit.value = true
  } else if (templates.value.length && !manualEdit.value) {
    message.value = renderedTemplate.value
  }
}
const loadStage = async () => {
  // Semilla desde serviceData (ya en memoria) para no esperar al fetch.
  const qp = (props.serviceData || {}).quoted_price
  lastQuoted.value = qp != null ? Number(qp) : null
  try {
    const d = await apiClient.get(`pipeline/leads/${props.leadId}/stage`)
    stage.value = d.stage
    if (d.quotedPrice != null) lastQuoted.value = d.quotedPrice
    if (d.suggestedPrice != null) fetchedSuggested.value = d.suggestedPrice
    chat.value = {
      price: d.chatPrice ?? null,
      includes: d.chatPriceIncludes ?? null,
      note: d.chatPriceNote ?? null,
      accepted: !!d.chatPriceAccepted,
    }
  } catch { /* no bloquea */ }
}
// Cuando se resuelve la etapa (nueva vs re-cotización) recargar los mensajes
// del tipo que corresponde.
watch(templateTipo, loadTemplates)
onMounted(async () => {
  await loadStage()
  await loadTemplates()
  nextTick(() => priceRef.value?.focus())
})

// Formato tipo composer: negrita *...*, viñetas "- ", Ctrl/Shift+Enter = salto.
const editAt = fn => {
  const el = messageRef.value
  if (!el) return
  const start = el.selectionStart
  const end = el.selectionEnd
  const { text, caret } = fn(message.value, start, end)
  message.value = text
  requestAnimationFrame(() => {
    el.focus()
    el.selectionStart = el.selectionEnd = caret
  })
}

const wrapBold = () => editAt((t, s, e) => {
  const sel = t.slice(s, e)
  return { text: t.slice(0, s) + '*' + sel + '*' + t.slice(e), caret: sel ? e + 2 : s + 1 }
})

const toggleBullet = () => editAt((t, s) => {
  let ls = t.lastIndexOf('\n', s - 1) + 1
  const line = t.slice(ls)
  if (line.startsWith('- ')) {
    return { text: t.slice(0, ls) + line.slice(2), caret: Math.max(ls, s - 2) }
  }
  return { text: t.slice(0, ls) + '- ' + line, caret: s + 2 }
})

const onKeydown = e => {
  if (e.key === 'Enter' && (e.ctrlKey || e.shiftKey)) {
    e.preventDefault()
    editAt((t, s, en) => ({ text: t.slice(0, s) + '\n' + t.slice(en), caret: s + 1 }))
  }
}

const submit = async () => {
  errMsg.value = ''
  if (busy.value || hasBooking()) return
  if (!(effectivePrice.value > 0)) { errMsg.value = 'Ingresá un precio válido.'; return }
  if (!message.value.trim()) { errMsg.value = 'Escribí el mensaje para el cliente.'; return }
  busy.value = true
  try {
    await apiClient.post(`pipeline/leads/${props.leadId}/quick-quote`, {
      price: effectivePrice.value,
      message: message.value.trim(),
    })
    pipelineStore.bump()
    window.dispatchEvent(new Event('pipeline:stage-refresh'))
    emit('done', { stage: 'quotes' })
    emit('close')
  } catch (e) {
    errMsg.value = e.message || 'No se pudo cotizar.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div
    class="qd-overlay"
    :class="{ 'qd-overlay--drag': draggable }"
    @click.self="draggable ? null : $emit('close')"
  >
    <div
      class="qd-modal"
      :class="{ 'qd-modal--drag': draggable }"
      :style="draggable ? { transform: `translate(${dragPos.x}px, ${dragPos.y}px)` } : {}"
    >
      <div
        class="qd-header"
        :class="{ 'qd-header--drag': draggable }"
        @pointerdown="onDragStart"
      >
        <h3>
          <i
            v-if="draggable"
            class="ri-drag-move-2-line qd-drag-hint"
          />
          💰 {{ alreadyQuoted() ? 'Volver a cotizar' : 'Cotizar' }}
        </h3>
        <button
          class="qd-close"
          @click="$emit('close')"
        >
          <i class="ri-close-line" />
        </button>
      </div>

      <div class="qd-body">
        <div
          v-if="hasBooking()"
          class="qd-banner qd-banner--err"
        >
          Ya tiene <b>reserva confirmada</b>. El precio se ajusta desde Reservas.
        </div>

        <div
          v-if="showInterprovincial"
          class="qd-banner qd-banner--warn"
        >
          <b>Ruta fuera de Lima.</b> El cotizador automático usa reglas de Lima y suele quedarse
          corto (caso real Lima→Piura: estimó S/&nbsp;300, precio real S/&nbsp;2.500).
          Pon el precio a mano.
        </div>

        <!-- En modo panel (abierto desde Ver) el resumen ya se ve en Ver;
             solo se repiten los precios de referencia. -->
        <ServiceSummary
          v-if="!draggable"
          :service-data="serviceData"
          :stage-extra="stageExtra"
          :lead-id="leadId"
          interactive
          @use-suggested="onUseSuggested"
        />

        <template v-if="draggable">
          <div class="qd-field qd-field--price qd-refline">
            <label>Precio sugerido</label>
            <b>{{ suggestedMoney || '—' }}</b>
          </div>
          <div
            v-if="alreadyQuoted() && quotedMoney"
            class="qd-field qd-field--price qd-refline qd-refline--quoted"
          >
            <label>Último cotizado</label>
            <b>{{ quotedMoney }}</b>
          </div>
        </template>

        <!-- Precio a cotizar: justo debajo del precio sugerido -->
        <div class="qd-field qd-field--price">
          <label>{{ alreadyQuoted() ? 'Nuevo precio' : 'Precio a cotizar' }}</label>
          <div class="qd-price-box">
            <span class="qd-price-prefix">S/</span>
            <input
              ref="priceRef"
              v-model="price"
              class="qd-price-input"
              type="text"
              inputmode="decimal"
              :placeholder="pricePlaceholder"
              @keydown.enter.prevent="submit"
            >
          </div>
        </div>

        <!-- Mensaje: debajo del precio -->
        <div class="qd-field">
          <div class="qd-pick-msg-head">
            <label>Mensaje</label>
            <button
              type="button"
              class="qd-tpl-edit"
              title="Editar mensajes predefinidos"
              @click="showManager = true"
            >
              <i class="ri-settings-3-line" />
            </button>
          </div>
          <select
            v-if="templates.length"
            v-model.number="comboValue"
            class="qd-combo"
          >
            <option
              v-for="(tpl, i) in templates"
              :key="i"
              :value="i"
            >
              {{ comboOption(tpl) }}
            </option>
            <option
              v-if="manualEdit"
              :value="-1"
              disabled
            >
              ✏️ Mensaje propio
            </option>
          </select>
        </div>

        <div class="qd-toolbar">
          <button
            type="button"
            title="Negrita (*texto*)"
            @click="wrapBold"
          >
            <b>B</b>
          </button>
          <button
            type="button"
            title="Viñeta"
            @click="toggleBullet"
          >
            <i class="ri-list-unordered" />
          </button>
          <button
            type="button"
            class="qd-clear"
            title="Vaciar para escribir un mensaje propio"
            @click="clearMessage"
          >
            <i class="ri-eraser-line" /> Limpiar
          </button>
        </div>

        <div class="qd-row">
          <textarea
            ref="messageRef"
            v-model="message"
            class="qd-msg"
            rows="3"
            placeholder="Mensaje para el cliente…"
            @input="onMessageInput"
            @keydown="onKeydown"
          />
          <button
            class="qd-send"
            :class="{ 'qd-send--new': !alreadyQuoted() }"
            :disabled="busy || hasBooking()"
            :title="alreadyQuoted() ? 'Re-cotizar y enviar' : 'Cotizar y enviar (nueva)'"
            @click="submit"
          >
            <i :class="busy ? 'ri-loader-4-line spin' : 'ri-send-plane-2-fill'" />
          </button>
        </div>

        <div
          v-if="errMsg"
          class="qd-err"
        >
          {{ errMsg }}
        </div>
      </div>
    </div>

    <QuickRepliesManager
      v-if="showManager"
      :items="templates"
      :tipo="templateTipo"
      @close="showManager = false"
      @saved="onTemplatesSaved"
    />
  </div>
</template>

<style scoped>
.qd-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100000;
}

/* Modo panel flotante arrastrable: sin fondo oscuro, arranca a la derecha y
   deja pasar los clics hacia el modal Ver que queda detrás. */
/* Panel Cotizar: siempre centrado, con un velo tenue para que resalte sobre
   lo que haya detrás (chat o modal Ver). Se puede arrastrar por el encabezado. */
.qd-overlay--drag {
  background: rgba(0, 0, 0, 0.22);
  padding: 24px;
  z-index: 100010;
}

.qd-modal {
  width: 560px;
  max-width: 94vw;
  max-height: 88vh;
  background: #fff;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.qd-modal--drag {
  pointer-events: auto;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
  width: 480px;
}

.qd-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #eee;
}

.qd-header--drag {
  cursor: move;
  user-select: none;
  background: #faf8ff;
}

.qd-drag-hint {
  color: #a78bfa;
  margin-right: 4px;
}

/* Precio sugerido / último cotizado: fila simple, sin tarjeta. */
.qd-refline {
  margin: 8px 0;
}

.qd-refline b {
  font-size: 14px;
  font-weight: 700;
  color: #6b7280;
}

.qd-refline--quoted b {
  color: #047857;
}

.qd-header h3 {
  margin: 0;
  font-size: 15px;
}



.qd-close {
  border: none;
  background: none;
  font-size: 18px;
  color: #666;
  cursor: pointer;
}

.qd-body {
  padding: 12px 16px;
  overflow-y: auto;
}

/* Campos apilados: precio primero, luego mensaje. */
.qd-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 10px 0;
}

.qd-field label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: #6b7280;
}

/* Precio a cotizar: etiqueta a la izquierda, input a la derecha, misma línea. */
.qd-field--price {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.qd-field--price .qd-price-box {
  flex: 0 0 auto;
  width: 200px;
  max-width: 60%;
}

.qd-pick-msg-head {
  display: flex;
  align-items: center;
  gap: 6px;
}

.qd-tpl-edit {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  background: none;
  color: #9ca3af;
  font-size: 14px;
  cursor: pointer;
}

.qd-tpl-edit:hover {
  color: #4b5563;
}

.qd-combo {
  width: 100%;
  padding: 7px 8px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 12px;
  font-family: inherit;
  background: #f3f4f6;
  color: #374151;
  cursor: pointer;
}

.qd-combo:focus {
  outline: none;
  border-color: #9ca3af;
}

/* Fila estilo composer: mensaje | enviar */
.qd-row {
  display: flex;
  align-items: stretch;
  gap: 8px;
}

.qd-price-box {
  display: flex;
  align-items: center;
  width: 100%;
  border: 1px solid #c4b5fd;
  border-radius: 8px;
  padding: 0 10px;
  background: #fff;
}

.qd-price-box:focus-within {
  border-color: #8b5cf6;
}

.qd-price-prefix {
  font-size: 12px;
  font-weight: 700;
  color: #999;
}

.qd-price-input {
  width: 100%;
  border: none;
  outline: none;
  padding: 9px 4px 9px 6px;
  font-size: 15px;
  font-weight: 700;
  font-family: inherit;
  background: transparent;
  text-align: right;
}

.qd-msg {
  flex: 1;
  min-width: 0;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 13px;
  font-family: inherit;
  resize: vertical;
  line-height: 1.4;
}

.qd-msg:focus {
  outline: none;
  border-color: #8b5cf6;
}

.qd-send {
  flex-shrink: 0;
  align-self: center;
  width: 52px;
  height: 52px;
  border: none;
  border-radius: 50%;
  background: #8b5cf6;
  color: #fff;
  font-size: 20px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.qd-send:hover:not(:disabled) {
  background: #7c3aed;
}

.qd-send--new {
  background: #2563eb;
}

.qd-send--new:hover:not(:disabled) {
  background: #1d4ed8;
}

.qd-send:disabled {
  background: #e0e0e0;
  color: #999;
  cursor: not-allowed;
}

.qd-toolbar {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.qd-toolbar button:not(.qd-clear):not(.qd-restore) {
  width: 28px;
  height: 26px;
  border: 1px solid #ddd;
  border-radius: 5px;
  background: #fff;
  color: #555;
  font-size: 13px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.qd-toolbar button:hover {
  background: #f2f2f2;
}

.qd-clear,
.qd-restore {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  padding: 0 8px;
  border: 1px solid #ddd;
  border-radius: 5px;
  background: #fff;
  color: #666;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.qd-restore {
  border-color: #ddd6fe;
  color: #7c3aed;
  background: #f6f3fe;
}

.qd-err {
  margin-top: 10px;
  padding: 8px 10px;
  background: #ffebee;
  color: #d32f2f;
  border-radius: 6px;
  font-size: 12px;
}

.qd-banner {
  margin-bottom: 10px;
  padding: 9px 11px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.4;
}

.qd-banner--err {
  background: #ffebee;
  color: #c62828;
  border: 1px solid #ffcdd2;
}

.qd-banner--warn {
  background: #fff8e1;
  color: #a15c00;
  border: 1px solid #ffe0a3;
}

.spin {
  animation: qd-spin 0.8s linear infinite;
}

@keyframes qd-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
