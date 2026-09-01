<template>
  <Teleport to="body">
    <div
      v-if="activeImage"
      class="image-viewer-backdrop"
      @click.self="close"
    >
      <div class="image-viewer-toolbar">
        <span class="image-viewer-filename">{{ activeImage.filename }}</span>
        <div class="image-viewer-actions">
          <a
            :href="activeImage.url"
            :download="activeImage.filename"
            class="image-viewer-btn"
            title="Descargar"
            @click.stop
          >
            <i class="ri-download-2-line" />
          </a>
          <button
            class="image-viewer-btn"
            title="Cerrar (Esc)"
            @click="close"
          >
            <i class="ri-close-line" />
          </button>
        </div>
      </div>

      <img
        :src="activeImage.url"
        :alt="activeImage.filename"
        class="image-viewer-img"
        @click.stop
      >
    </div>
  </Teleport>
</template>

<script setup>
import { onMounted, onBeforeUnmount } from 'vue'
import { useImageViewer } from '@/composables/useImageViewer'

const { activeImage, close } = useImageViewer()

const handleKeydown = event => {
  if (event.key === 'Escape') close()
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.image-viewer-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  animation: viewer-fade-in 0.15s ease-out;
}

@keyframes viewer-fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

.image-viewer-toolbar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  color: #fff;
  background: linear-gradient(to bottom, rgba(0, 0, 0, 0.5), transparent);
}

.image-viewer-filename {
  font-size: 14px;
  opacity: 0.85;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 60vw;
}

.image-viewer-actions {
  display: flex;
  gap: 8px;
}

.image-viewer-btn {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
  border: none;
  cursor: pointer;
  font-size: 20px;
  text-decoration: none;
  transition: background 0.15s;
}

.image-viewer-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}

.image-viewer-img {
  max-width: 90vw;
  max-height: 85vh;
  object-fit: contain;
  border-radius: 4px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.5);
}
</style>
