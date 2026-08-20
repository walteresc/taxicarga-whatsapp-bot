<template>
  <div class="conversation-sidebar">
    <!-- FILA 1: BUSCADOR -->
    <div class="conversation-search">
      <i class="ri-search-line search-icon"></i>
      <input
        v-model="searchPhone"
        type="text"
        placeholder="Buscar por nombre, teléfono o mensaje"
        class="search-input"
      />
    </div>

    <!-- FILA 2: FILTROS -->
    <div class="conversation-filters">
      <!-- State filter tabs -->
      <button
        v-for="tag in filterTabs"
        :key="tag"
        @click="toggleFilter(tag)"
        :class="['filter-tab', { active: activeFilters.includes(tag) }]"
        :title="tag"
      >
        {{ tag }}
      </button>

      <!-- Channel dropdown -->
      <ChannelDropdown
        :active-channels="activeChannels"
        @update:active-channels="activeChannels = $event"
      />

      <!-- Advanced filters button -->
      <button
        class="filter-btn"
        @click="showFilterMenu = !showFilterMenu"
        :title="activeFiltersCount > 0 ? `${activeFiltersCount} filtro(s) activo(s)` : 'Filtros avanzados'"
      >
        <i class="ri-filter-line"></i>
        <span v-if="activeFiltersCount > 0" class="badge">{{ activeFiltersCount }}</span>
      </button>

      <!-- Advanced filter menu (positioned absolutely) -->
      <div v-if="showFilterMenu" class="filter-menu">
        <div class="filter-group">
          <label class="group-title">Más filtros</label>
          <button
            v-for="tag in advancedFilterTags"
            :key="tag"
            @click="toggleFilter(tag)"
            :class="['menu-item', { active: activeFilters.includes(tag) }]"
          >
            <i class="ri-checkbox-blank-circle-line"></i>
            {{ tag }}
          </button>
        </div>
      </div>
    </div>

    <!-- CONVERSATIONS LIST -->
    <div class="conversations-container">
      <!-- LOADING STATE -->
      <div v-if="loading" class="state-container">
        <div v-for="i in 5" :key="`skeleton-${i}`" class="skeleton-item">
          <div class="skeleton-avatar"></div>
          <div class="skeleton-content">
            <div class="skeleton-line"></div>
            <div class="skeleton-line short"></div>
          </div>
        </div>
      </div>

      <!-- ERROR STATE -->
      <div v-else-if="error" class="state-container">
        <div class="empty-state">
          <i class="ri-error-warning-line error-icon"></i>
          <p class="error-title">No pudimos cargar las conversaciones</p>
          <button @click="loadConversations" class="retry-btn">Reintentar</button>
        </div>
      </div>

      <!-- NO RESULTS STATE -->
      <div v-else-if="filteredConversations.length === 0 && hasActiveFilters" class="state-container">
        <div class="empty-state">
          <i class="ri-inbox-line empty-icon"></i>
          <p class="empty-title">No encontramos conversaciones</p>
          <p class="empty-text">No hay conversaciones que coincidan con los filtros seleccionados</p>
          <button @click="clearFilters" class="clear-btn">Limpiar filtros</button>
        </div>
      </div>

      <!-- EMPTY STATE -->
      <div v-else-if="filteredConversations.length === 0" class="state-container">
        <div class="empty-state">
          <i class="ri-inbox-line empty-icon"></i>
          <p class="empty-title">Aún no hay conversaciones</p>
          <p class="empty-text">Las nuevas conversaciones aparecerán aquí</p>
        </div>
      </div>

      <!-- CONVERSATIONS -->
      <div
        v-for="conv in filteredConversations"
        :key="conv.id"
        @click="selectConversation(conv)"
        :class="['conversation-item', { active: props.selectedConversationId === conv.id }]"
      >
        <div class="avatar">
          <img v-if="conv.avatar" :src="conv.avatar" :alt="conv.name" />
          <div v-else class="avatar-placeholder" :style="getAvatarStyle(conv.id)">
            <span v-if="conv.name">{{ getInitials(conv.name) }}</span>
            <i v-else class="ri-account-circle-line"></i>
          </div>
        </div>
        <div class="content">
          <div class="header">
            <h4 class="name">{{ conv.name || formatPhone(conv.phone) }}</h4>
            <span class="time">{{ formatTime(conv.lastActivity) }}</span>
          </div>
          <p class="preview">{{ formatPreview(conv.preview) }}</p>
          <div class="badges">
            <span v-if="conv.estadoCotizacion === 'Por cotizar'" class="badge orange">Por cotizar</span>
            <span v-if="conv.attentionMode === 'bot'" class="badge">Bot</span>
            <span v-if="conv.attentionMode === 'advisor'" class="badge">Asesor</span>
            <span v-if="conv.attentionMode === 'unassigned'" class="badge gray">Sin asignar</span>
            <span v-if="conv.attentionMode === 'closed'" class="badge gray">Cerrada</span>
            <span v-if="conv.unread > 0" class="badge-number">{{ conv.unread }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { conversationService } from '@/services/conversationService'
import ChannelDropdown from './components/ChannelDropdown.vue'

const props = defineProps({
  selectedConversationId: {
    type: Number,
    default: null,
  },
})

const emit = defineEmits(['conversation-selected', 'update-count'])

const loading = ref(false)
const error = ref(false)
const searchPhone = ref('')
const activeFilters = ref(['Todas'])
const activeChannels = ref(['Todos'])
const conversations = ref([])
const showFilterMenu = ref(false)

const filterTabs = ['Todas', 'Mías', 'No leídas']
const advancedFilterTags = ['Sin asignar', 'Bot atendiendo', 'Asesor atendiendo', 'Cerradas']

const totalCount = computed(() => conversations.value.length)

const activeFiltersCount = computed(() => {
  const count = activeFilters.value.filter(f => f !== 'Todas').length +
    activeChannels.value.filter(c => c !== 'Todos').length
  return count > 0 ? count : 0
})

const hasActiveFilters = computed(() => {
  return searchPhone.value.trim() !== '' ||
    !activeFilters.value.includes('Todas') ||
    !activeChannels.value.includes('Todos')
})

const selectedHiddenChannels = computed(() => {
  return hiddenChannels.filter(channel => activeChannels.value.includes(channel))
})

const filteredConversations = computed(() => {
  let filtered = conversations.value

  // Apply search filter
  if (searchPhone.value) {
    const query = searchPhone.value.toLowerCase()
    filtered = filtered.filter(
      conv =>
        conv.name.toLowerCase().includes(query) ||
        conv.phone.toLowerCase().includes(query) ||
        (conv.preview && conv.preview.toLowerCase().includes(query)) ||
        (conv.resumen && conv.resumen.toLowerCase().includes(query))
    )
  }

  // Apply state filters
  if (!activeFilters.value.includes('Todas')) {
    filtered = filtered.filter(conv => {
      if (activeFilters.value.includes('Mías') && (!conv.responsable || !conv.responsable.id)) return false
      if (activeFilters.value.includes('No leídas') && conv.unread === 0) return false
      if (activeFilters.value.includes('Sin asignar') && conv.responsable && conv.responsable.id) return false
      if (activeFilters.value.includes('Bot atendiendo') && conv.attentionMode !== 'bot') return false
      if (activeFilters.value.includes('Asesor atendiendo') && conv.attentionMode !== 'advisor') return false
      if (activeFilters.value.includes('Cerradas') && conv.attentionMode !== 'closed') return false
      return true
    })
  }

  // Apply channel filters
  if (!activeChannels.value.includes('Todos')) {
    filtered = filtered.filter(conv => activeChannels.value.includes(conv.channel))
  }

  return filtered
})

const toggleFilter = tag => {
  if (tag === 'Todas') {
    activeFilters.value = ['Todas']
  } else {
    const index = activeFilters.value.indexOf(tag)
    if (index > -1) {
      activeFilters.value.splice(index, 1)
    } else {
      const todasIndex = activeFilters.value.indexOf('Todas')
      if (todasIndex > -1) {
        activeFilters.value.splice(todasIndex, 1)
      }
      activeFilters.value.push(tag)
    }
    if (activeFilters.value.length === 0) {
      activeFilters.value = ['Todas']
    }
  }
  // Close filter menu after selection
  showFilterMenu.value = false
}

const toggleChannel = channel => {
  if (channel === 'Todos') {
    activeChannels.value = ['Todos']
  } else {
    const index = activeChannels.value.indexOf(channel)
    if (index > -1) {
      activeChannels.value.splice(index, 1)
    } else {
      const todoIndex = activeChannels.value.indexOf('Todos')
      if (todoIndex > -1) {
        activeChannels.value.splice(todoIndex, 1)
      }
      activeChannels.value.push(channel)
    }
    if (activeChannels.value.length === 0) {
      activeChannels.value = ['Todos']
    }
  }
}

const clearFilters = () => {
  searchPhone.value = ''
  activeFilters.value = ['Todas']
  activeChannels.value = ['Todos']
}

const selectConversation = conv => {
  emit('conversation-selected', conv)
}

const formatTime = time => {
  if (!time) return ''
  const date = new Date(time)
  const now = new Date()
  const diff = (now - date) / 1000

  if (diff < 60) return 'Ahora'
  if (diff < 3600) return `${Math.floor(diff / 60)}m`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`
  return date.toLocaleDateString('es-ES', { month: 'short', day: 'numeric' })
}

const getInitials = name => {
  if (!name) return ''
  return name
    .split(' ')
    .map(n => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
}

const formatPreview = text => {
  if (!text) return 'Conversación nueva'
  // Normalize common message types
  if (text.includes('Imagen') || text.match(/📷|Foto/i)) return '📷 Foto'
  if (text.includes('Audio') || text.match(/🎤|Audio/i)) return '🎤 Audio'
  if (text.includes('Documento') || text.match(/📄|Documento/i)) return '📄 Documento'
  if (text.includes('Ubicación') || text.match(/📍|Ubicación/i)) return '📍 Ubicación'
  return text
}

const getChannelIcon = channel => {
  const icons = {
    Todos: 'global-line',
    WhatsApp: 'whatsapp-line',
    Correo: 'mail-line',
    Instagram: 'instagram-line',
    Facebook: 'facebook-circle-line',
    'Chat web': 'chat-3-line',
    TikTok: 'tiktok-line',
    Otros: 'more-2-fill',
  }
  return icons[channel] || 'global-line'
}

const getAvatarStyle = contactId => {
  const colors = ['#FF6B9D', '#C44569', '#F8B500', '#56AB2F', '#0085CA', '#662E9B']
  const index = Math.abs(contactId % colors.length)
  return {
    backgroundColor: colors[index],
    color: '#fff',
  }
}

const formatPhone = phone => {
  if (!phone) return 'Desconocido'
  if (phone.startsWith('+')) {
    return phone.slice(0, 3) + ' ' + phone.slice(3)
  }
  return phone
}


const loadConversations = async () => {
  loading.value = true
  error.value = false
  try {
    // Build filters object from active filters
    const filters = {}
    if (searchPhone.value) filters.q = searchPhone.value

    // Map state filters to backend states
    if (!activeFilters.value.includes('Todos')) {
      if (activeFilters.value.includes('No leídas')) filters.state = 'unread'
      else if (activeFilters.value.includes('Mías')) filters.state = 'assigned'
      else if (activeFilters.value.includes('Sin asignar')) filters.state = 'unassigned'
    }

    const data = await conversationService.getActiveConversations(filters)
    conversations.value = data.conversations || []
  } catch (err) {
    console.error('Error loading conversations:', err)
    error.value = true
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadConversations()
})

// Emit count update whenever filtered results change
watch(() => filteredConversations.value.length, (newCount) => {
  emit('update-count', newCount)
})
</script>

<style scoped>
.conversation-sidebar {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  height: 100%;
  background: #fff;
  border-right: 1px solid #e0e0e0;
  width: 350px;
  min-height: 0;
  overflow: visible;
}

/* FILA 1: BUSCADOR */
.conversation-search {
  padding: 8px 12px;
  position: relative;
  flex-shrink: 0;
}

.search-icon {
  position: absolute;
  left: 20px;
  top: 50%;
  transform: translateY(-50%);
  color: #999;
  font-size: 16px;
  pointer-events: none;
}

.search-input {
  width: 100%;
  padding: 6px 12px 6px 32px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  font-size: 12px;
  height: 42px;
  background: #fff;
  transition: border-color 0.2s;
}

.search-input:focus {
  outline: none;
  border-color: var(--v-primary-base, #ff6b3d);
}

.search-input::placeholder {
  color: #ccc;
}

/* FILA 2: FILTROS */
.conversation-filters {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px 8px;
  min-height: auto;
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  position: relative;
  flex-shrink: 0;
  z-index: 100;
}

.filter-tab {
  padding: 4px 10px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 16px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  flex-shrink: 0;
  min-width: fit-content;
}

.filter-tab:hover {
  border-color: #999;
  background: #f9f9f9;
}

.filter-tab.active {
  background: var(--v-primary-base, #ff6b3d);
  color: white;
  border-color: var(--v-primary-base, #ff6b3d);
}

.filter-btn {
  position: relative;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 4px;
  color: #666;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: auto;
}

.filter-btn:hover {
  border-color: #999;
  background: #f9f9f9;
}

.filter-btn .badge {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--v-primary-base, #ff6b3d);
  color: white;
  font-size: 9px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

.filter-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 10000;
  background: white;
  border: 1px solid #ddd;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  min-width: 180px;
}

.filter-group {
  padding: 8px 0;
}

.group-title {
  display: block;
  padding: 6px 12px;
  font-size: 10px;
  font-weight: 600;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: none;
  font-size: 11px;
  color: #333;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s;
}

.menu-item:hover {
  background: #f5f5f5;
}

.menu-item.active {
  color: var(--v-primary-base, #ff6b3d);
  font-weight: 600;
}

.menu-item i {
  font-size: 12px;
  opacity: 0;
  transition: opacity 0.2s;
}

.menu-item.active i {
  opacity: 1;
}


.conversations-container {
  flex: 1 1 auto;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.state-container {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 20px;
}

.skeleton-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.skeleton-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: loading 1.5s infinite;
  flex-shrink: 0;
}

.skeleton-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.skeleton-line {
  height: 8px;
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: loading 1.5s infinite;
  border-radius: 2px;
  width: 100%;
}

.skeleton-line.short {
  width: 70%;
}

@keyframes loading {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

.empty-state {
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
}

.empty-icon,
.error-icon {
  font-size: 48px;
  color: #ddd;
}

.error-icon {
  color: #f87171;
}

.empty-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.empty-text {
  margin: 0;
  font-size: 12px;
  color: #999;
}

.retry-btn,
.clear-btn {
  padding: 6px 16px;
  background: var(--v-primary-base, #ff6b3d);
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.retry-btn:hover,
.clear-btn:hover {
  opacity: 0.9;
}

.conversation-item {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background 0.15s;
  min-height: 88px;
  border-left: 3px solid transparent;
}

.conversation-item:hover {
  background: #fafafa;
}

.conversation-item.active {
  background: #fffaf5;
  border-left-color: var(--v-primary-base, #ff6b3d);
}

.avatar {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
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
  font-size: 16px;
  color: #fff;
  text-transform: uppercase;
}

.avatar-placeholder i {
  font-size: 24px;
  color: #999;
}

.content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 3px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 6px;
}

.name {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.time {
  font-size: 11px;
  color: #999;
  flex-shrink: 0;
  white-space: nowrap;
}

.preview {
  margin: 0;
  font-size: 13px;
  color: #666;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.2;
}

.badges {
  display: flex;
  gap: 4px;
  align-items: center;
  flex-wrap: wrap;
}

.badge {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  background: #e8eaf6;
  color: var(--v-primary-base, #ff6b3d);
  white-space: nowrap;
}

.badge.orange {
  background: #ffe8d6;
  color: var(--v-primary-base, #ff6b3d);
}

.badge.gray {
  background: #f0f0f0;
  color: #666;
}

.badge-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--v-error-base, #f87171);
  color: white;
  font-size: 10px;
  font-weight: 600;
}
</style>
