<template>
  <div class="channel-dropdown-wrapper">
    <button
      class="channel-btn"
      @click="isOpen = !isOpen"
      :title="`Filtrar por ${selectedLabel}`"
    >
      <i :class="`ri-${selectedIcon}-line`"></i>
      <span>{{ selectedLabel }}</span>
      <i class="ri-arrow-down-s-line dropdown-icon"></i>
    </button>

    <div v-if="isOpen" class="channel-menu">
      <button
        v-for="channel in channels"
        :key="channel"
        class="channel-item"
        :class="{ active: activeChannels.includes(channel) }"
        @click="toggleChannel(channel)"
      >
        <i :class="`ri-${getChannelIcon(channel)}-line`"></i>
        {{ channel }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

defineProps({
  activeChannels: {
    type: Array,
    default: () => ['Todos'],
  },
})

const emit = defineEmits(['update:activeChannels'])

const isOpen = ref(false)
const channels = ['Todos', 'WhatsApp', 'Correo', 'Instagram', 'Facebook', 'Chat web', 'TikTok', 'Otros']

const selectedLabel = computed(() => {
  if (activeChannels.length === 0) return 'Todos'
  if (activeChannels.includes('Todos')) return 'Todos'
  return activeChannels[0]
})

const selectedIcon = computed(() => getChannelIcon(selectedLabel.value))

const getChannelIcon = (channel) => {
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

const toggleChannel = (channel) => {
  let newChannels = [...activeChannels]

  if (channel === 'Todos') {
    newChannels = ['Todos']
  } else {
    const index = newChannels.indexOf(channel)
    if (index > -1) {
      newChannels.splice(index, 1)
    } else {
      const todoIndex = newChannels.indexOf('Todos')
      if (todoIndex > -1) {
        newChannels.splice(todoIndex, 1)
      }
      newChannels.push(channel)
    }

    if (newChannels.length === 0) {
      newChannels = ['Todos']
    }
  }

  emit('update:activeChannels', newChannels)
  isOpen.value = false
}
</script>

<style scoped>
.channel-dropdown-wrapper {
  position: relative;
}

.channel-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 16px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.channel-btn:hover {
  border-color: #999;
  background: #f9f9f9;
}

.channel-btn i {
  font-size: 14px;
}

.dropdown-icon {
  font-size: 16px;
  transition: transform 0.2s;
}

.channel-menu {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 4px;
  background: white;
  border: 1px solid #ddd;
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  min-width: 150px;
  overflow: hidden;
}

.channel-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: none;
  font-size: 12px;
  color: #333;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s;
}

.channel-item:hover {
  background: #f5f5f5;
}

.channel-item.active {
  background: #f0f0f0;
  color: var(--v-primary-base, #ff6b3d);
  font-weight: 600;
}

.channel-item i {
  font-size: 14px;
}
</style>
