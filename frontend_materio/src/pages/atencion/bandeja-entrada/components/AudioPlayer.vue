<template>
  <div class="audio-player">
    <button
      class="play-btn"
      type="button"
      :aria-label="isPlaying ? 'Pausar' : 'Reproducir'"
      @click="togglePlay"
    >
      <i :class="isPlaying ? 'ri-pause-fill' : 'ri-play-fill'" />
    </button>

    <div
      class="audio-track"
      role="slider"
      :aria-valuenow="Math.round(progressPercent)"
      aria-valuemin="0"
      aria-valuemax="100"
      tabindex="0"
      @click="seek"
      @keydown.left="skip(-5)"
      @keydown.right="skip(5)"
    >
      <div class="audio-bars">
        <span
          v-for="n in barCount"
          :key="n"
          class="audio-bar"
          :class="{ played: (n / barCount) * 100 <= progressPercent }"
          :style="{ height: barHeights[n - 1] + '%' }"
        />
      </div>
    </div>

    <span class="audio-time">{{ displayTime }}</span>

    <audio
      ref="audioEl"
      :src="src"
      preload="metadata"
      @timeupdate="onTimeUpdate"
      @loadedmetadata="onLoadedMetadata"
      @ended="onEnded"
      @error="onError"
    />
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount } from 'vue'

const props = defineProps({
  src: {
    type: String,
    required: true,
  },
})

const audioEl = ref(null)
const isPlaying = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const hasError = ref(false)

// Static pseudo-waveform (WhatsApp decodes the real one; this approximates the look
// without adding an audio-decoding dependency). Seeded so it doesn't reflow on re-render.
const barCount = 27
const barHeights = Array.from({ length: barCount }, (_, i) => {
  const wave = Math.sin(i * 0.7) * 0.5 + Math.sin(i * 0.35) * 0.3

  return 30 + Math.abs(wave) * 65
})

const progressPercent = computed(() => {
  if (!duration.value) return 0

  return Math.min(100, (currentTime.value / duration.value) * 100)
})

const formatTime = seconds => {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)

  return `${m}:${s.toString().padStart(2, '0')}`
}

const displayTime = computed(() => {
  if (hasError.value) return '--:--'
  if (isPlaying.value || currentTime.value > 0) return formatTime(currentTime.value)

  return formatTime(duration.value)
})

const togglePlay = () => {
  if (!audioEl.value || hasError.value) return
  if (isPlaying.value) {
    audioEl.value.pause()
  } else {
    audioEl.value.play().catch(() => {
      hasError.value = true
    })
  }
}

const onTimeUpdate = () => {
  isPlaying.value = !audioEl.value.paused
  currentTime.value = audioEl.value.currentTime
}

const onLoadedMetadata = () => {
  duration.value = audioEl.value.duration || 0
}

const onEnded = () => {
  isPlaying.value = false
  currentTime.value = 0
}

const onError = () => {
  hasError.value = true
}

const seek = event => {
  if (!audioEl.value || !duration.value) return
  const rect = event.currentTarget.getBoundingClientRect()
  const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width))

  audioEl.value.currentTime = ratio * duration.value
}

const skip = delta => {
  if (!audioEl.value || !duration.value) return
  audioEl.value.currentTime = Math.min(duration.value, Math.max(0, audioEl.value.currentTime + delta))
}

onBeforeUnmount(() => {
  audioEl.value?.pause()
})
</script>

<style scoped>
.audio-player {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 220px;
  padding: 4px 2px;
}

.play-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: #25d366;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s;
}

.play-btn:hover {
  background: #1fb855;
}

.play-btn i {
  font-size: 18px;
}

.audio-track {
  flex: 1;
  min-width: 0;
  cursor: pointer;
  padding: 8px 0;
}

.audio-bars {
  display: flex;
  align-items: center;
  gap: 2px;
  height: 24px;
}

.audio-bar {
  flex: 1;
  min-width: 2px;
  border-radius: 2px;
  background: #c8c8c8;
  transition: background 0.1s;
}

.audio-bar.played {
  background: #25d366;
}

.audio-time {
  flex-shrink: 0;
  font-size: 11px;
  color: #888;
  min-width: 32px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
