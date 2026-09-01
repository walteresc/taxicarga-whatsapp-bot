/**
 * Shared full-screen image viewer state — module-level singleton so any
 * MessageBubble instance can open it and a single <ImageViewer /> (mounted
 * once) renders it, instead of each bubble owning its own modal.
 */
import { ref } from 'vue'

const activeImage = ref(null) // { url, filename } | null

export function useImageViewer() {
  const open = (url, filename) => {
    activeImage.value = { url, filename: filename || 'Imagen' }
  }

  const close = () => {
    activeImage.value = null
  }

  return { activeImage, open, close }
}
