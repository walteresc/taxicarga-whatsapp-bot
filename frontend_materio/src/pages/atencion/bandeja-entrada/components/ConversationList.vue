<template>
  <div class="conversation-list">
    <!-- HEADER -->
    <div class="list-header">
      <h3>Conversaciones</h3>
      <span class="count-badge">{{ totalCount }}</span>
    </div>

    <!-- SEARCH -->
    <div class="search-section">
      <i class="ri-search-line search-icon"></i>
      <input
        v-model="searchPhone"
        type="text"
        placeholder="Buscar por nombre, teléfono o mensaje"
        class="search-input"
      />
    </div>

    <!-- FILTERS ROW 1 -->
    <div class="filters-row">
      <button
        v-for="tag in filterTags"
        :key="tag"
        @click="toggleFilter(tag)"
        :class="['filter-chip', { active: activeFilters.includes(tag) }]"
      >
        {{ tag }}
      </button>
      <button class="filter-chip filter-button">
        <i class="ri-filter-line"></i>
        <span v-if="activeFiltersCount > 0" class="badge">{{ activeFiltersCount }}</span>
      </button>
    </div>

    <!-- FILTERS ROW 2 (Channels) -->
    <div class="channels-row">
      <!-- Visible channels -->
      <button
        v-for="channel in visibleChannels"
        :key="channel"
        @click="toggleChannel(channel)"
        :class="['channel-chip', { active: activeChannels.includes(channel) }]"
      >
        <i :class="`ri-${getChannelIcon(channel)}`"></i>
        {{ channel }}
      </button>

      <!-- Selected hidden channels as chips with close button -->
      <button
        v-for="channel in selectedHiddenChannels"
        :key="`selected-${channel}`"
        @click.stop="removeChannel(channel)"
        :class="['channel-chip', 'active', 'removable']"
      >
        <i :class="`ri-${getChannelIcon(channel)}`"></i>
        {{ channel }}
        <span class="remove-icon">×</span>
      </button>

      <!-- Dropdown for more channels -->
      <div class="channel-dropdown-wrapper">
        <button
          @click="toggleDropdown"
          :class="['channel-chip', { active: showDropdown }]"
        >
          <span>Más</span>
          <i class="ri-arrow-down-s-line dropdown-arrow" :class="{ rotated: showDropdown }"></i>
        </button>
        <div v-if="showDropdown" class="channel-dropdown">
          <button
            v-for="channel in hiddenChannels"
            :key="`hidden-${channel}`"
            @click="toggleChannel(channel); toggleDropdown()"
            :class="['dropdown-item', { selected: activeChannels.includes(channel) }]"
          >
            <i :class="`ri-${getChannelIcon(channel)}`"></i>
            {{ channel }}
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
        class="conversation-item"
      >
        <div class="avatar">
          <img v-if="conv.avatar" :src="conv.avatar" :alt="conv.name" />
          <div v-else class="avatar-placeholder">{{ getInitials(conv.name) }}</div>
        </div>
        <div class="content">
          <div class="header">
            <h4 class="name">{{ conv.name }}</h4>
            <span class="time">{{ formatTime(conv.lastMessageTime) }}</span>
          </div>
          <p class="preview">{{ conv.lastMessage }}</p>
          <div class="badges">
            <span v-if="conv.status === 'COTIZAR'" class="badge orange">Por cotizar</span>
            <span v-if="conv.status === 'BOT'" class="badge">Bot</span>
            <span v-if="conv.status === 'ASESOR'" class="badge">Asesor</span>
            <span v-if="conv.unread" class="badge-number">{{ conv.unread }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { conversationService } from '@/services/conversationService'

const emit = defineEmits(['conversation-selected'])

const loading = ref(false)
const error = ref(false)
const searchPhone = ref('')
const activeFilters = ref(['Todos'])
const activeChannels = ref(['Todos'])
const conversations = ref([])

const filterTags = ['Todos', 'Mías', 'No leídas', 'Sin asignar']
const visibleChannels = ['Todos', 'WhatsApp', 'Correo']
const hiddenChannels = ['Instagram', 'Facebook', 'Chat web', 'TikTok', 'Otros']
const showDropdown = ref(false)

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

  if (searchPhone.value) {
    const query = searchPhone.value.toLowerCase()
    filtered = filtered.filter(
      conv =>
        conv.name.toLowerCase().includes(query) ||
        conv.phone.toLowerCase().includes(query) ||
        conv.lastMessage.toLowerCase().includes(query)
    )
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

const toggleDropdown = () => {
  showDropdown.value = !showDropdown.value
}

const removeChannel = channel => {
  const index = activeChannels.value.indexOf(channel)
  if (index > -1) {
    activeChannels.value.splice(index, 1)
  }
  if (activeChannels.value.length === 0) {
    activeChannels.value = ['Todos']
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

const loadConversations = async () => {
  loading.value = true
  error.value = false
  try {
    const data = await conversationService.getActiveConversations()
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
  setInterval(loadConversations, 3000)
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

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #e0e0e0;
}

.list-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #f0f0f0;
  font-size: 12px;
  font-weight: 600;
  color: #666;
}

.search-section {
  padding: 8px 12px;
  border-bottom: 1px solid #e0e0e0;
  position: relative;
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
}

.filters-row {
  display: flex;
  gap: 6px;
  padding: 8px 12px;
  flex-wrap: wrap;
  border-bottom: 1px solid #e0e0e0;
}

.channels-row {
  display: flex;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid #e0e0e0;
  flex-wrap: wrap;
  align-items: center;
}

.filter-chip,
.channel-chip {
  padding: 4px 10px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 16px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  position: relative;
}

.filter-chip:hover,
.channel-chip:hover {
  border-color: #999;
  background: #f9f9f9;
}

.filter-chip.active,
.channel-chip.active {
  background: var(--v-primary-base, #ff6b3d);
  color: white;
  border-color: var(--v-primary-base, #ff6b3d);
}

.filter-chip.filter-button {
  display: flex;
  align-items: center;
  gap: 4px;
}

.filter-chip.filter-button .badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #ff6b3d;
  color: white;
  font-size: 9px;
  font-weight: 600;
  position: absolute;
  right: -4px;
  top: -4px;
}

.channel-chip.removable {
  padding: 4px 8px 4px 10px;
}

.remove-icon {
  cursor: pointer;
  font-weight: bold;
  margin-left: 2px;
  opacity: 0.7;
  transition: opacity 0.2s;
}

.channel-chip.removable:hover .remove-icon {
  opacity: 1;
}

.dropdown-arrow {
  transition: transform 0.2s;
  font-size: 14px;
}

.dropdown-arrow.rotated {
  transform: rotate(180deg);
}

.channel-dropdown-wrapper {
  position: relative;
  display: inline-block;
}

.channel-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: white;
  border: 1px solid #ddd;
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  min-width: 140px;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: none;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
  color: #333;
  text-align: left;
  white-space: nowrap;
}

.dropdown-item:first-child {
  border-radius: 5px 5px 0 0;
}

.dropdown-item:last-child {
  border-radius: 0 0 5px 5px;
}

.dropdown-item:hover {
  background: #f0f0f0;
}

.dropdown-item.selected {
  background: #ffe8d6;
  color: var(--v-primary-base, #ff6b3d);
  font-weight: 600;
}

.dropdown-item i {
  font-size: 14px;
}

.conversations-container {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
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
  font-size: 14px;
  color: #666;
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
