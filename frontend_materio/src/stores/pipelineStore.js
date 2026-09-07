// Contadores del pipeline comercial para los badges del menú.
// Se refresca al montar el layout, cada 60 s, y tras cada acción (bump()).
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { pipelineCounts } from '@/services/commercialService'

export const usePipelineStore = defineStore('pipeline', () => {
  const counts = ref({
    potentials: 0, review: 0, quoting: 0, quotes: 0, bookings: 0,
    unseen: { potentials: 0, review: 0, quoting: 0, quotes: 0, bookings: 0 },
  })
  let timer = null

  const refresh = async () => {
    try {
      counts.value = await pipelineCounts()
    } catch { /* silencioso: es solo el badge */ }
  }

  const start = () => {
    refresh()
    if (!timer) timer = setInterval(refresh, 60000)
  }
  const stop = () => { if (timer) { clearInterval(timer); timer = null } }

  // Tras una acción que cambia de bandeja.
  const bump = () => refresh()

  return { counts, refresh, start, stop, bump }
})
