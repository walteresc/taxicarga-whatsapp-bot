<template>
  <div class="service-card">
    <div v-if="!conversation" class="empty">
      <p>Selecciona una conversación</p>
    </div>
    <div v-else class="card-content">
      <!-- CLIENTE HEADER -->
      <div class="client-header">
        <div class="avatar">
          <img v-if="conversation.avatar" :src="conversation.avatar" :alt="conversation.name" />
          <div v-else class="avatar-placeholder">{{ getInitials(conversation.name) }}</div>
        </div>
        <div class="client-info">
          <h3>{{ conversation.name }}</h3>
          <p>{{ conversation.phone }}</p>
          <p class="channel">
            <i class="ri-whatsapp-line"></i>
            {{ conversation.channel }}
          </p>
        </div>
      </div>

      <!-- ATENCIÓN SECTION -->
      <div class="section attention-section">
        <h4>Atención</h4>
        <div class="attention-info">
          <div class="info-row">
            <span>Responsable</span>
            <strong>{{ serviceData.responsable || 'Sin asignar' }}</strong>
          </div>
          <p class="status-text">Atiende ahora</p>
        </div>
        <div class="buttons">
          <button class="btn btn-orange">Tomar control</button>
          <button class="btn btn-secondary">Pausar bot</button>
        </div>
      </div>

      <!-- DATOS DEL SERVICIO -->
      <div class="section service-data-section">
        <h4>Datos del servicio</h4>
        <div class="data-grid">
          <div class="data-item">
            <label>Origen</label>
            <p>{{ serviceData.origen || '-' }}</p>
          </div>
          <div class="data-item">
            <label>Destino</label>
            <p>{{ serviceData.destino || '-' }}</p>
          </div>
          <div class="data-item">
            <label>Piso origen</label>
            <p>{{ serviceData.pisoOrigen || '-' }}</p>
          </div>
          <div class="data-item">
            <label>Piso destino</label>
            <p>{{ serviceData.pisoDestino || '-' }}</p>
          </div>
          <div class="data-item">
            <label>Ayudantes</label>
            <p>{{ serviceData.ayudantes || '-' }}</p>
          </div>
          <div class="data-item">
            <label>Fecha</label>
            <p>
              {{ serviceData.fecha || 'Pendiente' }}
              <span v-if="!serviceData.fechaConfirmada" class="warning-badge">⚠️</span>
            </p>
          </div>
        </div>
      </div>

      <!-- COMERCIAL SECTION -->
      <div class="section commercial-section">
        <h4>Commercial</h4>
        <div class="commercial-info">
          <div class="info-row">
            <span>Etapa</span>
            <button class="badge-orange">{{ serviceData.etapa || 'Por cotizar' }}</button>
          </div>
          <div class="info-row">
            <span>Precio sugerido</span>
            <strong>S/ {{ serviceData.precioSugerido || '-' }}</strong>
          </div>
        </div>
      </div>

      <!-- CREATE QUOTE BUTTON -->
      <button class="btn-create-quote">
        <i class="ri-file-list-line"></i>
        Crear cotización
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  conversation: Object,
})

const serviceData = ref({
  responsable: 'María',
  origen: 'Surco',
  destino: 'Miraflores',
  pisoOrigen: '2.° - Escaleras',
  pisoDestino: '1.°',
  ayudantes: '2',
  fecha: 'Pendiente',
  fechaConfirmada: false,
  etapa: 'Por cotizar',
  precioSugerido: '450',
})

const getInitials = name => {
  return name
    .split(' ')
    .map(n => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
}
</script>

<style scoped>
.service-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  border-left: 1px solid #e0e0e0;
  overflow-y: auto;
}

.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
  font-size: 12px;
}

.card-content {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.client-header {
  display: flex;
  gap: 12px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e0e0e0;
}

.avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
}

.avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-placeholder {
  width: 100%;
  height: 100%;
  background: #e0e0e0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 18px;
  color: #666;
}

.client-info h3 {
  margin: 0 0 4px 0;
  font-size: 14px;
  font-weight: 600;
}

.client-info p {
  margin: 0;
  font-size: 12px;
  color: #666;
}

.channel {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #10b981;
}

.section {
  padding-bottom: 16px;
  border-bottom: 1px solid #e0e0e0;
}

.section:last-child {
  border-bottom: none;
}

.section h4 {
  margin: 0 0 12px 0;
  font-size: 12px;
  font-weight: 600;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.attention-section .buttons {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.btn {
  flex: 1;
  padding: 8px 12px;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-orange {
  background: #ff6b3d;
  color: white;
}

.btn-orange:hover {
  background: #ff5722;
}

.btn-secondary {
  background: #f0f0f0;
  color: #333;
}

.btn-secondary:hover {
  background: #e0e0e0;
}

.status-text {
  margin: 8px 0 0 0;
  font-size: 11px;
  color: #999;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
}

.info-row span {
  color: #666;
}

.info-row strong {
  color: #333;
  font-weight: 600;
}

.data-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.data-item {
  padding: 8px;
  background: #f9f9f9;
  border-radius: 4px;
}

.data-item label {
  display: block;
  font-size: 11px;
  color: #999;
  margin-bottom: 4px;
  font-weight: 600;
  text-transform: uppercase;
}

.data-item p {
  margin: 0;
  font-size: 12px;
  color: #333;
  font-weight: 600;
}

.warning-badge {
  margin-left: 4px;
}

.commercial-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.badge-orange {
  padding: 4px 10px;
  background: #ffe8d6;
  color: #ff6b3d;
  border: none;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.btn-create-quote {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  background: #ff6b3d;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  margin-top: auto;
}

.btn-create-quote:hover {
  background: #ff5722;
}
</style>
