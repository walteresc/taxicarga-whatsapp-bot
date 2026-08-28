<template>
  <div class="channel-dropdown-wrapper">
    <button
      class="channel-btn"
      :title="`Filtrar por ${selectedLabel}`"
      @click="isOpen = !isOpen"
    >
      <i :class="`ri-${selectedIcon}-line`" />
      <span>{{ selectedLabel }}</span>
      <i class="ri-arrow-down-s-line dropdown-icon" />
    </button>

    <div
      v-if="isOpen"
      class="channel-menu"
    >
      <button
        class="channel-item"
        :class="{ active: props.activeChannels.includes('Todos') }"
        @click="toggleChannel('Todos')"
      >
        <i class="ri-global-line" />
        Todos los canales
      </button>
      <button
        v-for="channel in channels"
        v-if="channel !== 'Todos'"
        :key="channel"
        class="channel-item"
        :class="{ active: props.activeChannels.includes(channel) }"
        @click="toggleChannel(channel)"
      >
        <i :class="`ri-${getChannelIcon(channel)}`" />
        {{ channel }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  activeChannels: {
    type: Array,
    default: () => ['Todos'],
  },
})

const emit = defineEmits(['update:activeChannels', 'open-dropdown'])

const isOpen = ref(false)

watch(isOpen, newVal => {
  if (newVal) {
    emit('open-dropdown')
  }
})

const channels = ['Todos', 'WhatsApp', 'Correo', 'Instagram', 'Facebook', 'Chat web', 'TikTok', 'Otros']

const selectedLabel = computed(() => {
  if (props.activeChannels.length === 0) return 'Canal'
  if (props.activeChannels.includes('Todos')) return 'Canal'
  
  return props.activeChannels[0]
})

const selectedIcon = computed(() => {
  const selected = selectedLabel.value
  if (selected === 'Canal') return 'global-line'
  
  return getChannelIcon(selected)
})

const getChannelIcon = channel => {
  const icons = {
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

const toggleChannel = channel => {
  let newChannels = [...props.activeChannels]

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
  z-index: 100;
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
  top: calc(100% + 4px);
  left: 0;
  background: white;
  border: 1px solid #ddd;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 10000;
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
