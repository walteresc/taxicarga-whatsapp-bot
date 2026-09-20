<script setup>
// "¿Para cuándo?" — reemplaza un simple campo de fecha por accesos rápidos
// (Urgente/Hoy/Mañana), fecha fija vs. flexible, y franja horaria. Todo se
// guarda en los mismos campos de siempre (date = YYYY-MM-DD, schedule =
// texto libre) — no hace falta ningún cambio de backend.
import { computed, ref, watch } from 'vue'

const props = defineProps({
  date: { type: String, default: '' },       // v-model:date
  schedule: { type: String, default: '' },    // v-model:schedule
})
const emit = defineEmits(['update:date', 'update:schedule'])

const todayIso = () => new Date().toISOString().slice(0, 10)
const tomorrowIso = () => { const d = new Date(); d.setDate(d.getDate() + 1); return d.toISOString().slice(0, 10) }

const quickPick = ref('')   // 'urgente' | 'hoy' | 'manana' | '' (custom)
const flexibility = ref('fija')   // 'fija' | 'flex'
const hourMode = ref('flexible')   // 'flexible' | 'exacta'
const window_ = ref('manana')
const exactTime = ref('')

const WINDOWS = [
  { value: 'manana', title: 'Por la mañana', range: '6:00 a 12:00' },
  { value: 'tarde', title: 'Por la tarde', range: '12:00 a 18:00' },
  { value: 'noche', title: 'Por la noche', range: '18:00 a 00:00' },
  { value: 'dia', title: 'Durante el día', range: '6:00 a 00:00' },
]

const buildSchedule = () => {
  if (quickPick.value === 'urgente') return 'Urgente — lo antes posible'
  const parts = []
  parts.push(flexibility.value === 'flex' ? 'Flexible ± 2 días' : 'Fecha fija')
  if (hourMode.value === 'exacta' && exactTime.value) parts.push(`Hora exacta ${exactTime.value}`)
  else if (hourMode.value === 'flexible') {
    const w = WINDOWS.find(x => x.value === window_.value)
    if (w) parts.push(`${w.title} (${w.range})`)
  }

  return parts.join(' · ')
}

const pickQuick = value => {
  quickPick.value = value
  if (value === 'hoy') emit('update:date', todayIso())
  else if (value === 'manana') emit('update:date', tomorrowIso())
  else if (value === 'urgente') emit('update:date', '')
  emit('update:schedule', buildSchedule())
}

watch([flexibility, hourMode, window_, exactTime], () => emit('update:schedule', buildSchedule()))

const onDateInput = v => {
  quickPick.value = ''
  emit('update:date', v)
  emit('update:schedule', buildSchedule())
}

const showWindows = computed(() => quickPick.value !== 'urgente' && hourMode.value === 'flexible')
const showExact = computed(() => quickPick.value !== 'urgente' && hourMode.value === 'exacta')
const showFlexRow = computed(() => quickPick.value !== 'urgente')
</script>

<template>
  <div>
    <div class="text-h6 font-weight-bold mb-3">¿Para cuándo?</div>
    <VRow dense class="mb-2">
      <VCol v-for="q in [{ v: 'urgente', t: 'Urgente', s: 'Lo antes posible' }, { v: 'hoy', t: 'Hoy', s: 'En el transcurso de hoy' }, { v: 'manana', t: 'Mañana', s: 'Mañana' }]" :key="q.v" cols="4">
        <VCard
          :variant="quickPick === q.v ? 'tonal' : 'outlined'" :color="quickPick === q.v ? 'primary' : undefined"
          class="pa-2 text-center h-100" style="cursor: pointer;" @click="pickQuick(q.v)"
        >
          <div class="text-body-2 font-weight-bold">{{ q.t }}</div>
          <div class="text-caption text-medium-emphasis">{{ q.s }}</div>
        </VCard>
      </VCol>
    </VRow>

    <VTextField
      :model-value="date" label="Fecha" type="date" density="comfortable" class="mb-2"
      clearable @update:model-value="onDateInput" @click:clear="onDateInput('')"
    />

    <template v-if="showFlexRow">
      <VBtnToggle
        v-model="flexibility" color="primary" variant="outlined" divided
        density="comfortable" mandatory class="schedule-toggle mb-4"
      >
        <VBtn value="fija" class="px-6">Fecha fija</VBtn>
        <VBtn value="flex" class="px-6">Flexible ± 2 días</VBtn>
      </VBtnToggle>

      <div class="text-subtitle-2 font-weight-bold mb-2">¿A qué hora?</div>
      <VBtnToggle
        v-model="hourMode" color="primary" variant="outlined" divided
        density="comfortable" mandatory class="schedule-toggle mb-4"
      >
        <VBtn value="flexible" class="px-6">Horario flexible</VBtn>
        <VBtn value="exacta" class="px-6">Hora exacta</VBtn>
      </VBtnToggle>

      <VRow v-if="showWindows" dense class="mb-2">
        <VCol v-for="w in WINDOWS" :key="w.value" cols="6" sm="3">
          <VCard
            :variant="window_ === w.value ? 'tonal' : 'outlined'" :color="window_ === w.value ? 'primary' : undefined"
            class="pa-2 text-center h-100" style="cursor: pointer;" @click="window_ = w.value"
          >
            <div class="text-caption font-weight-bold">{{ w.title }}</div>
            <div class="text-caption text-medium-emphasis">{{ w.range }}</div>
          </VCard>
        </VCol>
      </VRow>
      <VTextField v-if="showExact" v-model="exactTime" label="Hora exacta (ej. 09:00)" type="time" density="comfortable" class="mb-2" />
    </template>
  </div>
</template>

<style scoped>
/* El tema (Materio) fuerza en .v-btn-toggle un ancho fijo de 44/52px por
   botón (pensado para toggles de solo ícono) — con texto ("Fecha fija" /
   "Flexible ± 2 días") eso los aplasta y superpone. Se anula ese ancho fijo
   acá; la especificidad extra (dos clases en el mismo elemento) es
   necesaria para ganarle al !important del tema — mismo fix que
   ContinueModePicker.vue (.price-btn-toggle) y cotizar.vue (.load-mode-toggle). */
:deep(.schedule-toggle.v-btn-toggle .v-btn) {
  inline-size: auto !important;
  block-size: 40px !important;
}
</style>
