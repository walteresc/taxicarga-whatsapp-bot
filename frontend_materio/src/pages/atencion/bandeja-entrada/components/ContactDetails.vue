<template>
  <div class="contact-details">
    <!-- Header -->
    <div class="details-header">
      <h4>Información</h4>
      <button
        v-if="mobileClose"
        class="close-btn"
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
          {{ getInitials(contact.name) }}
        </div>
      </div>
      <h3>{{ contact.name }}</h3>
      <p class="phone">
        {{ contact.phone }}
      </p>
    </div>

    <!-- Service info -->
    <div
      v-if="service"
      class="details-section"
    >
      <h4>Servicio</h4>
      <div class="info-row">
        <span class="label">Origen</span>
        <span class="value">{{ service.origin || '-' }}</span>
      </div>
      <div class="info-row">
        <span class="label">Destino</span>
        <span class="value">{{ service.destination || '-' }}</span>
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
        <span class="value">S/ {{ service.price || '-' }}</span>
      </div>
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
defineProps({
  contact: {
    type: Object,
    required: true,
  },
  service: {
    type: Object,
    default: () => ({}),
  },
  advisor: Object,
  mobileClose: Boolean,
})

defineEmits(['close'])

const getInitials = name => {
  if (!name) return '?'
  
  return name
    .split(' ')
    .map(n => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
}
</script>

<style scoped>
.contact-details {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  border-left: 1px solid #e0e0e0;
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

.section-avatar h3 {
  margin: 0 0 4px 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.phone {
  margin: 0;
  font-size: 12px;
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
