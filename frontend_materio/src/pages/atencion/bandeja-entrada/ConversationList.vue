<template>
  <div class="conversation-list">
    <!-- COMPACT HEADER -->
    <div class="compact-header">
      <div class="header-top">
        <h3>Bandeja de entrada <span class="count">{{ totalCount }}</span></h3>
        <div class="header-controls">
          <div class="search-section">
            <i class="ri-search-line search-icon"></i>
            <input
              v-model="searchPhone"
              type="text"
              placeholder="Buscar..."
              class="search-input"
            />
          </div>

          <!-- Filter menu button -->
          <button
            class="filter-btn"
            @click="showFilterMenu = !showFilterMenu"
            :title="activeFiltersCount > 0 ? `${activeFiltersCount} filtro(s) activo(s)` : 'Filtros avanzados'"
          >
            <i class="ri-filter-line"></i>
            <span v-if="activeFiltersCount > 0" class="badge">{{ activeFiltersCount }}</span>
          </button>

          <!-- Channel dropdown -->
          <ChannelDropdown
            :active-channels="activeChannels"
            @update:active-channels="activeChannels = $event"
          />
        </div>
      </div>

      <!-- ACTIVE FILTERS CHIPS (only show if filters active) -->
      <div v-if="hasActiveFilters" class="active-filters">
        <!-- State filter chips -->
        <button
          v-for="tag in activeFilters"
          v-if="tag !== 'Todos'"
          :key="tag"
          @click="toggleFilter(tag)"
          class="filter-chip"
        >
          {{ tag }}
          <i class="ri-close-line"></i>
        </button>

        <!-- Channel filter chips -->
        <button
          v-for="channel in activeChannels"
          v-if="channel !== 'Todos'"
          :key="`ch-${channel}`"
          @click="toggleChannel(channel)"
          class="filter-chip"
        >
          <i :class="`ri-${getChannelIcon(channel)}`"></i>
          {{ channel }}
          <i class="ri-close-line"></i>
        </button>

        <!-- Clear all button -->
        <button @click="clearFilters" class="clear-all-btn">
          Limpiar todo
        </button>
      </div>
    </div>

    <!-- FILTER MENU (dropdown) -->
    <div v-if="showFilterMenu" class="filter-menu">
      <div class="filter-group">
        <label class="group-title">Estado</label>
        <button
          v-for="tag in filterTags"
          :key="tag"
          @click="toggleFilter(tag)"
          :class="['menu-item', { active: activeFilters.includes(tag) }]"
        >
          <i class="ri-checkbox-blank-circle-line"></i>
          {{ tag }}
        </button>
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
            {{ getInitials(conv.name || conv.phone) }}
          </div>
        </div>
        <div class="content">
          <div class="header">
            <h4 class="name">{{ conv.name || formatPhone(conv.phone) }}</h4>
            <span class="time">{{ formatTime(conv.lastActivity) }}</span>
          </div>
          <p class="preview">{{ conv.preview }}</p>
          <div class="badges">
            <span v-if="conv.estadoCotizacion === 'Por cotizar'" class="badge orange">Por cotizar</span>
            <span v-if="conv.attentionMode === 'bot'" class="badge">🤖 Bot</span>
            <span v-if="conv.attentionMode === 'advisor'" class="badge">👤 Asesor</span>
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
import { ref, computed, onMounted } from 'vue'
import { conversationService } from '@/services/conversationService'
import ChannelDropdown from './components/ChannelDropdown.vue'

const props = defineProps({
  selectedConversationId: {
    type: Number,
    default: null,
  },
})

const emit = defineEmits(['conversation-selected'])

const loading = ref(false)
const error = ref(false)
const searchPhone = ref('')
const activeFilters = ref(['Todos'])
const activeChannels = ref(['Todos'])
const conversations = ref([])
const showFilterMenu = ref(false)

const filterTags = ['Todos', 'Mías', 'No leídas', 'Sin asignar']

const totalCount = computed(() => conversations.value.length)

const activeFiltersCount = computed(() => {
  const count = activeFilters.value.filter(f => f !== 'Todos').length +
    activeChannels.value.filter(c => c !== 'Todos').length
  return count > 0 ? count : 0
})

const hasActiveFilters = computed(() => {
  return searchPhone.value.trim() !== '' ||
    !activeFilters.value.includes('Todos') ||
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
  if (!activeFilters.value.includes('Todos')) {
    filtered = filtered.filter(conv => {
      if (activeFilters.value.includes('Mías') && (!conv.responsable || !conv.responsable.id)) return false
      if (activeFilters.value.includes('No leídas') && conv.unread === 0) return false
      if (activeFilters.value.includes('Sin asignar') && conv.responsable && conv.responsable.id) return false
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
  if (tag === 'Todos') {
    activeFilters.value = ['Todos']
  } else {
    const index = activeFilters.value.indexOf(tag)
    if (index > -1) {
      activeFilters.value.splice(index, 1)
    } else {
      const todoIndex = activeFilters.value.indexOf('Todos')
      if (todoIndex > -1) {
        activeFilters.value.splice(todoIndex, 1)
      }
      activeFilters.value.push(tag)
    }
    if (activeFilters.value.length === 0) {
      activeFilters.value = ['Todos']
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
  activeFilters.value = ['Todos']
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
  return name
    .split(' ')
    .map(n => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
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
</script>

<style scoped>
.conversation-list {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  border-right: 1px solid #e0e0e0;
  width: 350px;
}

.compact-header {
  display: flex;
  flex-direction: column;
  gap: 0;
  background: #fff;
  border-bottom: 1px solid #e0e0e0;
  position: relative;
}

.header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  gap: 8px;
  flex-wrap: wrap;
}

.header-top h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #333;
  white-space: nowrap;
}

.count {
  margin-left: 6px;
  padding: 2px 6px;
  background: #f0f0f0;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  color: #666;
}

.header-controls {
  display: flex;
  gap: 6px;
  align-items: center;
  flex: 1;
  min-width: 0;
  justify-content: flex-end;
}

.search-section {
  position: relative;
  flex: 1;
  min-width: 120px;
  max-width: 180px;
}

.search-icon {
  position: absolute;
  left: 8px;
  top: 50%;
  transform: translateY(-50%);
  color: #999;
  font-size: 14px;
  pointer-events: none;
}

.search-input {
  width: 100%;
  padding: 4px 8px 4px 26px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 11px;
  min-height: 28px;
}

.search-input::placeholder {
  color: #ccc;
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

.active-filters {
  display: flex;
  gap: 6px;
  padding: 6px 12px;
  flex-wrap: wrap;
  align-items: center;
  border-top: 1px solid #f0f0f0;
}

.active-filters .filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  background: #ffe8d6;
  border: 1px solid var(--v-primary-base, #ff6b3d);
  color: var(--v-primary-base, #ff6b3d);
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.active-filters .filter-chip:hover {
  background: #ffd6b8;
}

.active-filters .filter-chip i {
  font-size: 11px;
  opacity: 0.7;
}

.clear-all-btn {
  padding: 3px 8px;
  border: 1px solid #ddd;
  background: #f5f5f5;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 500;
  color: #666;
  cursor: pointer;
  transition: all 0.2s;
}

.clear-all-btn:hover {
  background: #e8e8e8;
  border-color: #999;
}

.filter-menu {
  position: absolute;
  top: 100%;
  right: 0;
  z-index: 1000;
  background: white;
  border: 1px solid #ddd;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  min-width: 180px;
  margin-top: 4px;
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
  gap: 12px;
  padding: 12px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background 0.15s;
}

.conversation-item:hover {
  background: #f9f9f9;
}

.conversation-item.active {
  background: #f0f4ff;
  border-left: 3px solid var(--v-primary-base, #ff6b3d);
  padding-left: 9px;
}

.avatar {
  width: 48px;
  height: 48px;
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
  font-size: 16px;
  color: #fff;
  text-transform: uppercase;
}

.content {
  flex: 1;
  min-width: 0;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 4px;
}

.name {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.time {
  font-size: 11px;
  color: #999;
  flex-shrink: 0;
  margin-left: 4px;
}

.preview {
  margin: 4px 0;
  font-size: 12px;
  color: #666;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.badges {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 4px;
}

.badge {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  background: #e8eaf6;
  color: var(--v-primary-base, #ff6b3d);
}

.badge.orange {
  background: #ffe8d6;
  color: var(--v-primary-base, #ff6b3d);
}

.badge-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--v-error-base, #f87171);
  color: white;
  font-size: 10px;
  font-weight: 600;
}
</style>
