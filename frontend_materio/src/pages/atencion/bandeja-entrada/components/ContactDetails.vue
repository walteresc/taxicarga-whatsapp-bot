<template>
  <div class="contact-details">
    <!-- Header -->
    <div class="details-header">
      <h4>Información</h4>
      <button
        class="close-btn"
        title="Cerrar panel"
        @click="$emit('close')"
      >
        <i class="ri-close-line" />
      </button>
    </div>

    <!-- Contact section -->
    <div class="details-section">
      <div class="section-avatar">
        <img
          v-if="contact.avatar"
          :src="contact.avatar"
          :alt="contact.name"
        >
        <div
          v-else
          class="avatar-placeholder"
        >
          <span v-if="contactNameUsable">{{ getInitials(contactPrimary) }}</span>
          <i
            v-else
            class="ri-account-circle-line"
          />
        </div>
      </div>
      <div
        v-if="!editingName"
        class="contact-name-row"
      >
        <h3>{{ contactPrimary }}</h3>
        <button
          class="edit-name-btn"
          title="Editar nombre del contacto"
          @click="startEditName"
        >
          <i class="ri-pencil-line" />
        </button>
      </div>
      <div
        v-else
        class="contact-name-edit"
      >
        <input
          ref="nameInputRef"
          v-model="nameDraft"
          type="text"
          maxlength="160"
          placeholder="Nombre del contacto"
          :disabled="savingName"
          @keyup.enter="saveName"
          @keyup.esc="cancelEditName"
        >
        <div class="name-edit-actions">
          <button
            class="name-save"
            :disabled="savingName"
            @click="saveName"
          >
            Guardar
          </button>
          <button
            class="name-cancel"
            :disabled="savingName"
            @click="cancelEditName"
          >
            Cancelar
          </button>
        </div>
        <p
          v-if="nameError"
          class="name-error"
        >
          {{ nameError }}
        </p>
        <p class="name-edit-hint">
          El nombre que pongas tú manda sobre el de WhatsApp. Déjalo vacío para
          volver al de WhatsApp.
        </p>
      </div>
      <p
        v-if="contact.phone"
        class="phone"
      >
        <span v-if="contact.phone_is_id">ID WhatsApp: {{ contact.phone }}</span>
        <span v-else>{{ contact.phone }}</span>
        <span
          v-if="contact.name_is_manual"
          class="name-manual-tag"
        >nombre editado</span>
      </p>
      <p
        v-if="contact.phone_is_id"
        class="no-phone-hint"
      >
        Este contacto no comparte su número. Se identifica por su ID de WhatsApp;
        puedes ponerle un nombre con el lápiz.
      </p>
    </div>

    <!-- Transportista: marcado automático por código OFERTA-<código> (o a
         mano). Reversible aquí — vía obligatoria si se marcó por error. -->
    <div class="details-section transportista-toggle">
      <label class="transportista-check">
        <input
          type="checkbox"
          :checked="contact.is_transportista"
          :disabled="savingTransportista"
          @change="handleToggleTransportista($event.target.checked)"
        >
        🚚 Es transportista
      </label>
      <p
        v-if="contact.is_transportista"
        class="transportista-hint"
      >
        Esta conversación no aparece en la bandeja de clientes — solo en "Transportistas".
      </p>
    </div>

    <!-- Service info -->
    <div
      v-if="mostrarServicio"
      class="details-section"
    >
      <h4>Servicio</h4>
      <div class="info-row">
        <span class="label">Tipo</span>
        <span class="value">{{ cap(service.type) || '-' }}</span>
      </div>
      <div class="info-row">
        <span class="label">Origen</span>
        <span class="value">{{ service.address_origin || service.origin || '-' }}</span>
      </div>
      <div class="info-row">
        <span class="label">Destino</span>
        <span class="value">{{ service.address_destination || service.destination || '-' }}</span>
      </div>
      <div class="info-row">
        <span class="label">Piso origen / destino</span>
        <span class="value">{{ pisoTxt(service.floor_origin) }} / {{ pisoTxt(service.floor_destination) }}</span>
      </div>
      <div class="info-row">
        <span class="label">Ascensor o. / d.</span>
        <span class="value">{{ siNo(service.elevator_origin) }} / {{ siNo(service.elevator_destination) }}</span>
      </div>
      <div
        v-if="service.items"
        class="info-row"
      >
        <span class="label">Objetos</span>
        <span class="value">{{ service.items }}</span>
      </div>
      <div class="info-row">
        <span class="label">Fecha</span>
        <span class="value">{{ service.date || 'Por confirmar' }}</span>
      </div>
      <div
        v-if="service.schedule"
        class="info-row"
      >
        <span class="label">Horario</span>
        <span class="value">{{ service.schedule }}</span>
      </div>
      <div class="info-row">
        <span class="label">Estado</span>
        <span
          class="status"
          :class="[service.status]"
        >{{ service.status }}</span>
      </div>
      <div class="info-row">
        <span class="label">Precio sugerido</span>
        <span class="value">{{ money(service.suggested_price ?? service.price) }}</span>
      </div>
      <div class="info-row">
        <span class="label">Precio cotizado</span>
        <span class="value">{{ money(service.quoted_price) }}</span>
      </div>
      <div
        v-if="service.chat_price"
        class="info-row chat-price-row"
      >
        <span class="label">
          Precio en el chat
          <i
            class="ri-robot-2-line"
            title="Detectado por la IA en la conversación"
          />
        </span>
        <span class="value">
          {{ money(service.chat_price) }}
          <em
            v-if="service.chat_price_accepted"
            class="chat-price-ok"
          >aceptado</em>
        </span>
      </div>
      <p
        v-if="service.chat_price && (service.chat_price_includes || service.chat_price_note)"
        class="chat-price-detail"
      >
        <span v-if="service.chat_price_includes"><b>Incluye:</b> {{ service.chat_price_includes }}</span>
        <span v-if="service.chat_price_note"><b>Pago:</b> {{ service.chat_price_note }}</span>
      </p>
      <p
        v-if="service.has_lead === false"
        class="service-hint"
      >
        Datos detectados de la conversación. El lead comercial se crea al confirmarse
        tipo de servicio y ambos distritos.
      </p>
    </div>

    <!-- Advisor info -->
    <div class="details-section">
      <h4>Asesor asignado</h4>
      <div
        v-if="advisor"
        class="advisor-card"
      >
        <div class="advisor-avatar">
          <img
            v-if="advisor.avatar"
            :src="advisor.avatar"
            :alt="advisor.name"
          >
          <div
            v-else
            class="avatar-placeholder"
          >
            {{ getInitials(advisor.name) }}
          </div>
        </div>
        <div>
          <div class="advisor-name">
            {{ advisor.name }}
          </div>
          <div class="advisor-role">
            {{ advisor.role }}
          </div>
        </div>
      </div>
      <div
        v-else
        class="empty-value"
      >
        Sin asignar
      </div>
    </div>

    <!-- Action buttons -->
    <div class="details-actions">
      <button class="action-btn">
        <i class="ri-file-text-line" />
        Crear cotización
      </button>
      <button class="action-btn">
        <i class="ri-calendar-line" />
        Agendar llamada
      </button>
      <button class="action-btn">
        <i class="ri-edit-line" />
        Editar datos
      </button>
    </div>

    <!-- Notes section -->
    <div class="details-section notes">
      <h4>Notas</h4>
      <textarea
        placeholder="Agregar notas privadas..."
        class="notes-input"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { conversationService } from '@/services/conversationService'
import { useConversationsStore } from '@/stores/conversationsStore'

const props = defineProps({
  contact: {
    type: Object,
    required: true,
  },
  service: {
    type: Object,
    default: () => ({}),
  },
  advisor: Object,
})

defineEmits(['close'])

const conversationsStore = useConversationsStore()
const savingTransportista = ref(false)

// Mismo criterio que la lista y el encabezado: si el nombre de perfil no
// identifica al contacto, el teléfono ocupa el título.
const contactNameUsable = computed(() => {
  const c = props.contact
  if (c.name_usable === false) return false
  if (c.name_usable === true) return true

  return Boolean(c.name || c.profile_name)
})

const contactPrimary = computed(() => {
  const c = props.contact
  if (contactNameUsable.value) return c.profile_name || c.name

  return c.phone || 'Contacto sin identificar'
})

// --- Panel "Servicio" ---
const mostrarServicio = computed(() => {
  const s = props.service
  if (!s || typeof s !== 'object') return false

  return Boolean(
    s.type || s.origin || s.destination || s.address_origin ||
    s.address_destination || s.price || s.items || s.has_lead,
  )
})

const cap = txt => (txt ? String(txt).charAt(0).toUpperCase() + String(txt).slice(1) : txt)
const pisoTxt = n => (n === 0 ? 'PB' : n < 0 ? `S${Math.abs(n)}` : n ? String(n) : '-')
const siNo = b => (b === true ? 'Sí' : b === false ? 'No' : '-')
const money = v => (v != null && v !== '' && !Number.isNaN(Number(v)) ? `S/ ${Number(v).toFixed(2)}` : '-')

const getInitials = name => {
  if (!name) return '?'

  return name
    .split(' ')
    .map(n => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
}

// --- Editar nombre del contacto (como en la agenda del teléfono) ---
const editingName = ref(false)
const savingName = ref(false)
const nameError = ref('')
const nameDraft = ref('')
const nameInputRef = ref(null)

const startEditName = () => {
  // Parte del nombre de perfil crudo (aunque sea "🏪"), no del teléfono.
  nameDraft.value = props.contact.profile_name || props.contact.name || ''
  nameError.value = ''
  editingName.value = true
  nextTick(() => nameInputRef.value?.focus())
}

const cancelEditName = () => {
  editingName.value = false
  nameError.value = ''
}

const saveName = async () => {
  if (savingName.value) return
  savingName.value = true
  nameError.value = ''
  try {
    const data = await conversationService.setContactName(props.contact.id, nameDraft.value.trim())
    // Merge parcial en el store — la bandeja y el encabezado se actualizan solos
    // (misma conversación en pantalla). Las otras sesiones, vía SSE.
    conversationsStore.updateConversationState(props.contact.id, {
      name: data.name,
      profile_name: data.profile_name,
      name_usable: data.name_usable,
      name_is_manual: data.name_source === 'manual',
    })
    editingName.value = false
  } catch (err) {
    console.error('[ContactDetails] Error al guardar el nombre:', err)
    nameError.value = 'No se pudo guardar. Reintenta.'
  } finally {
    savingName.value = false
  }
}

/** Reversión manual de es_transportista — vía obligatoria (ver
 * apps/tercerizacion/services.py: marcar_transportista es pegajoso a
 * propósito, así que un marcado erróneo necesita una salida siempre
 * disponible aquí). */
const handleToggleTransportista = async checked => {
  savingTransportista.value = true
  try {
    const response = await fetch(
      `/dashboard/whatsapp/conversaciones/${props.contact.id}/transportista/`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': conversationService.getCsrfToken(),
        },
        credentials: 'include',
        body: JSON.stringify({ es_transportista: checked }),
      }
    )

    let data = null
    try {
      data = await response.json()
    } catch {
      data = null
    }

    if (data?.success) {
      conversationsStore.updateConversationState(props.contact.id, {
        is_transportista: data.es_transportista,
      })

      // selectedConversation in the parent is a snapshot reference, not
      // guaranteed to stay in sync with the store's splice-replace — patch it
      // directly too so the checkbox never silently reverts on next render.
      props.contact.is_transportista = data.es_transportista
    }
  } catch (error) {
    console.error('[ContactDetails] Failed to toggle transportista:', error)
  } finally {
    savingTransportista.value = false
  }
}
</script>

<style scoped>
.contact-details {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  overflow-y: auto;
}

.details-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #e0e0e0;
}

.details-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.close-btn {
  background: none;
  border: none;
  font-size: 18px;
  color: #666;
  cursor: pointer;
  padding: 0;
  transition: color 0.2s;
}

.close-btn:hover {
  color: #333;
}

.details-section {
  padding: 12px 16px;
  border-bottom: 1px solid #e0e0e0;
}

.details-section h4 {
  margin: 0 0 8px 0;
  font-size: 11px;
  font-weight: 600;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.section-avatar {
  text-align: center;
  padding: 12px 0;
}

.section-avatar img {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  object-fit: cover;
  margin-bottom: 12px;
}

.avatar-placeholder {
  width: 80px;
  height: 80px;
  background: #e0e0e0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 24px;
  color: #666;
  border-radius: 50%;
  margin: 0 auto 12px;
}

.section-avatar .avatar-placeholder i {
  font-size: 44px;
  color: #999;
}

.section-avatar h3 {
  margin: 0 0 4px 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.contact-name-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.edit-name-btn {
  border: none;
  background: transparent;
  color: #999;
  cursor: pointer;
  font-size: 14px;
  padding: 2px;
  line-height: 1;
  border-radius: 4px;
  transition: color 0.15s, background 0.15s;
}

.edit-name-btn:hover {
  color: #333;
  background: #f0f0f0;
}

.contact-name-edit {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0 8px;
}

.contact-name-edit input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 13px;
  text-align: center;
}

.contact-name-edit input:focus {
  outline: none;
  border-color: var(--v-primary-base, #ff6b3d);
}

.name-edit-actions {
  display: flex;
  gap: 6px;
  justify-content: center;
}

.name-save,
.name-cancel {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid #ddd;
}

.name-save {
  background: var(--v-primary-base, #ff6b3d);
  color: #fff;
  border-color: var(--v-primary-base, #ff6b3d);
}

.name-save:disabled,
.name-cancel:disabled {
  opacity: 0.6;
  cursor: default;
}

.name-cancel {
  background: #fff;
  color: #666;
}

.name-error {
  margin: 0;
  font-size: 11px;
  color: #f87171;
  text-align: center;
}

.name-edit-hint {
  margin: 0;
  font-size: 10px;
  color: #999;
  text-align: center;
  line-height: 1.3;
}

.name-manual-tag {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 5px;
  border-radius: 3px;
  background: #eef2ff;
  color: #6366f1;
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  vertical-align: middle;
}

.phone {
  margin: 0;
  font-size: 12px;
  color: #999;
}

.no-phone-hint {
  margin: 6px auto 0;
  max-width: 240px;
  font-size: 10px;
  line-height: 1.4;
  color: #999;
  text-align: center;
}

.service-hint {
  margin: 8px 0 0;
  font-size: 10px;
  line-height: 1.4;
  color: #999;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  font-size: 12px;
}

.label {
  color: #666;
  font-weight: 500;
}

.value {
  color: #333;
  font-weight: 600;
}

.chat-price-ok {
  margin-left: 4px;
  padding: 0 5px;
  border-radius: 8px;
  background: #dcfce7;
  color: #166534;
  font-size: 9px;
  font-weight: 700;
  font-style: normal;
  text-transform: uppercase;
}

.chat-price-detail {
  display: flex;
  flex-direction: column;
  gap: 1px;
  margin: 2px 0 0;
  font-size: 10px;
  line-height: 1.4;
  color: #6b7280;
}

.status {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  background: #e8eaf6;
  color: #3949ab;
}

.status.pending {
  background: #fef3c7;
  color: #92400e;
}

.empty-value {
  font-size: 12px;
  color: #999;
}

.transportista-toggle {
  padding-top: 10px;
  padding-bottom: 10px;
}

.transportista-check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  color: #333;
  cursor: pointer;
}

.transportista-check input {
  cursor: pointer;
}

.transportista-hint {
  margin: 6px 0 0 0;
  font-size: 11px;
  color: #999;
}

.advisor-card {
  display: flex;
  gap: 8px;
  padding: 8px;
  background: #f9f9f9;
  border-radius: 4px;
}

.advisor-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
}

.advisor-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.advisor-avatar .avatar-placeholder {
  width: 100%;
  height: 100%;
  margin: 0;
}

.advisor-name {
  font-size: 12px;
  font-weight: 600;
  color: #333;
}

.advisor-role {
  font-size: 10px;
  color: #999;
}

.details-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 16px;
  border-bottom: 1px solid #e0e0e0;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #f9f9f9;
  border-color: #999;
}

.notes {
  flex: 1;
}

.notes-input {
  width: 100%;
  min-height: 60px;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 11px;
  font-family: inherit;
  resize: none;
  outline: none;
}

.notes-input::placeholder {
  color: #999;
}
</style>
