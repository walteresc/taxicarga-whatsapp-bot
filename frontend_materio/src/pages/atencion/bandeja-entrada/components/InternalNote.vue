<template>
  <div class="internal-note">
    <div class="note-header">
      <i class="ri-sticky-note-line" />
      <span>Nota interna</span>
      <span class="note-time">{{ formatTime(note.timestamp) }}</span>
    </div>
    <div class="note-content">
      {{ note.text }}
    </div>
    <div
      v-if="note.author"
      class="note-author"
    >
      {{ note.author }}
    </div>
  </div>
</template>

<script setup>
defineProps({
  note: {
    type: Object,
    required: true,
  },
})

const formatTime = time => {
  if (!time) return ''
  const date = new Date(time)
  
  return date.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.internal-note {
  background: #fffbea;
  border-left: 3px solid #fbbf24;
  border-radius: 4px;
  padding: 12px;
  margin: 12px auto;
  max-width: 90%;
  font-size: 12px;
}

.note-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: #666;
  margin-bottom: 6px;
}

.note-header i {
  color: #fbbf24;
}

.note-time {
  margin-left: auto;
  font-weight: normal;
  color: #999;
  font-size: 11px;
}

.note-content {
  color: #333;
  margin-bottom: 6px;
  line-height: 1.4;
}

.note-author {
  font-size: 10px;
  color: #999;
}
</style>
