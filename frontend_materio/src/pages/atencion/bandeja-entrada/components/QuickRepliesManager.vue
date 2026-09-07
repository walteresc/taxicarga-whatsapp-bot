<script setup>
import { ref } from 'vue'

import { useEscapeToClose } from '@/composables/useEscapeToClose'
import { conversationService } from '@/services/conversationService'

const props = defineProps({
  items: { type: Array, default: () => [] },
  tipo: { type: String, default: 'respuesta' },
})
const emit = defineEmits(['close', 'saved'])

useEscapeToClose(() => emit('close'), { priority: 40 })

const isQuote = props.tipo === 'cotizacion' || props.tipo === 'recotizacion'
const title = props.tipo === 'recotizacion'
  ? '💰 Mensajes de re-cotización'
  : props.tipo === 'cotizacion'
    ? '💰 Mensajes de cotización'
    : '⚡ Mensajes predefinidos'

const rows = ref(props.items.length ? [...props.items] : [''])
const busy = ref(false)
const errMsg = ref('')

const add = () => rows.value.push('')
const remove = i => rows.value.splice(i, 1)

const save = async () => {
  errMsg.value = ''
  const clean = rows.value.map(t => t.trim()).filter(Boolean).slice(0, 40)
  busy.value = true
  try {
    const r = await fetch('/dashboard/whatsapp/respuestas-rapidas/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': conversationService.getCsrfToken(),
      },
      credentials: 'include',
      body: JSON.stringify({ items: clean, tipo: props.tipo }),
    })
    const data = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`)
    emit('saved', data.items || clean)
    emit('close')
  } catch (e) {
    errMsg.value = e.message || 'No se pudo guardar.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div
    class="qr-overlay"
    @click.self="$emit('close')"
  >
    <div class="qr-modal">
      <div class="qr-header">
        <h3>{{ title }}</h3>
        <button
          class="qr-close"
          @click="$emit('close')"
        >
          <i class="ri-close-line" />
        </button>
      </div>

      <div class="qr-body">
        <p class="qr-hint">
          Son tuyos: cada asesor arma su propia lista.
          <template v-if="isQuote">
            Escribí <b>{precio}</b> donde va el monto; se reemplaza con el precio que ingreses al cotizar.
          </template>
          <template v-else>
            Aparecen en el rayo del chat.
          </template>
        </p>

        <div
          v-for="(row, i) in rows"
          :key="i"
          class="qr-row"
        >
          <textarea
            v-model="rows[i]"
            class="qr-input"
            rows="2"
            placeholder="Escribí el mensaje…"
          />
          <button
            class="qr-del"
            title="Quitar"
            @click="remove(i)"
          >
            <i class="ri-delete-bin-line" />
          </button>
        </div>

        <button
          class="qr-add"
          @click="add"
        >
          <i class="ri-add-line" /> Agregar mensaje
        </button>

        <div
          v-if="errMsg"
          class="qr-err"
        >
          {{ errMsg }}
        </div>
      </div>

      <div class="qr-footer">
        <button
          class="qr-cancel"
          @click="$emit('close')"
        >
          Cancelar
        </button>
        <button
          class="qr-save"
          :disabled="busy"
          @click="save"
        >
          <i
            v-if="busy"
            class="ri-loader-4-line spin"
          />
          Guardar
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.qr-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100040;
  pointer-events: auto;
}

.qr-modal {
  width: 460px;
  max-width: 92vw;
  max-height: 86vh;
  background: #fff;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.qr-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #eee;
}

.qr-header h3 {
  margin: 0;
  font-size: 15px;
}

.qr-close {
  border: none;
  background: none;
  font-size: 18px;
  color: #666;
  cursor: pointer;
}

.qr-body {
  padding: 14px 16px;
  overflow-y: auto;
}

.qr-hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: #999;
}

.qr-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-bottom: 8px;
}

.qr-input {
  flex: 1;
  padding: 8px 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 13px;
  font-family: inherit;
  resize: vertical;
}

.qr-input:focus {
  outline: none;
  border-color: #ff6b3d;
}

.qr-del {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border: 1px solid #eee;
  border-radius: 6px;
  background: #fff;
  color: #d32f2f;
  cursor: pointer;
}

.qr-del:hover {
  background: #ffebee;
}

.qr-add {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  padding: 7px 12px;
  border: 1px dashed #ff9800;
  border-radius: 6px;
  background: #fff8f2;
  color: #ff6b3d;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.qr-err {
  margin-top: 10px;
  padding: 8px 10px;
  background: #ffebee;
  color: #d32f2f;
  border-radius: 6px;
  font-size: 12px;
}

.qr-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid #eee;
}

.qr-cancel {
  padding: 8px 14px;
  border: 1px solid #ddd;
  border-radius: 6px;
  background: #fff;
  font-size: 13px;
  cursor: pointer;
}

.qr-save {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  background: #ff6b3d;
  color: #fff;
  font-weight: 700;
  font-size: 13px;
  cursor: pointer;
}

.qr-save:disabled {
  opacity: 0.6;
  cursor: wait;
}

.spin {
  animation: qr-spin 0.8s linear infinite;
}

@keyframes qr-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
