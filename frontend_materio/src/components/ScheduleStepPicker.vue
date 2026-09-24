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
  { value: 'manana', title: 'Por la mañana', range: '6:00 a 12:00', icon: 'ri-sun-line' },
  { value: 'tarde', title: 'Por la tarde', range: '12:00 a 18:00', icon: 'ri-cloudy-line' },
  { value: 'noche', title: 'Por la noche', range: '18:00 a 00:00', icon: 'ri-moon-clear-line' },
  { value: 'dia', title: 'Durante el día', range: '6:00 a 00:00', icon: 'ri-time-line' },
]

const QUICK_PICKS = [
  { v: 'urgente', t: 'Urgente', s: 'Lo antes posible', icon: 'ri-flashlight-line' },
  { v: 'hoy', t: 'Hoy', s: 'En el transcurso de hoy', icon: 'ri-calendar-event-line' },
  { v: 'manana', t: 'Mañana', s: 'Mañana', icon: 'ri-calendar-2-line' },
  { v: 'otro', t: 'Otro día', s: 'Elige la fecha', icon: 'ri-calendar-line' },
]

const buildSchedule = () => {
  if (quickPick.value === 'urgente') return 'Urgente — lo antes posible'
  const parts = []
  // Fija vs. flexible solo tiene sentido cuando la fecha la elige el
  // cliente a mano ("Otro día") — "Hoy"/"Mañana" ya son de por sí una
  // fecha fija, no hace falta preguntarlo de nuevo.
  if (quickPick.value === 'otro') parts.push(flexibility.value === 'flex' ? 'Flexible ± 2 días' : 'Fecha fija')
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
  else emit('update:date', '')   // urgente | otro — sin fecha automática
  emit('update:schedule', buildSchedule())
}

watch([flexibility, hourMode, window_, exactTime], () => emit('update:schedule', buildSchedule()))

const onDateInput = v => {
  emit('update:date', v)
  emit('update:schedule', buildSchedule())
}

const showWindows = computed(() => quickPick.value !== 'urgente' && hourMode.value === 'flexible')
const showExact = computed(() => quickPick.value !== 'urgente' && hourMode.value === 'exacta')
// Antes el campo de fecha se veía siempre, aunque ya estuviera resuelto por
// "Hoy"/"Mañana" — redundante. Ahora solo aparece si eligen "Otro día".
const showDateCustom = computed(() => quickPick.value === 'otro')
const showHourSection = computed(() => quickPick.value !== 'urgente')
</script>

<template>
  <div>
    <div class="text-h6 font-weight-bold mb-3">¿Para cuándo?</div>
    <VRow dense class="mb-4">
      <VCol v-for="q in QUICK_PICKS" :key="q.v" cols="6" sm="3">
        <VCard
          variant="outlined" class="pa-3 h-100 position-relative schedule-tile"
          :class="{ 'schedule-tile--selected': quickPick === q.v }"
          style="cursor: pointer;" @click="pickQuick(q.v)"
        >
          <VIcon
            v-if="quickPick === q.v" icon="ri-checkbox-circle-fill" color="primary" size="16"
            style="position:absolute; top:8px; right:8px;"
          />
          <VAvatar
            size="32" class="mb-2" :variant="quickPick === q.v ? 'elevated' : 'tonal'"
            :color="quickPick === q.v ? 'primary' : 'surface-variant'"
          >
            <VIcon :icon="q.icon" size="16" :color="quickPick === q.v ? 'white' : undefined" />
          </VAvatar>
          <div class="text-body-2 font-weight-bold">{{ q.t }}</div>
          <div class="text-caption text-medium-emphasis">{{ q.s }}</div>
        </VCard>
      </VCol>
    </VRow>

    <template v-if="showDateCustom">
      <VRow dense align="center" class="mb-3">
        <VCol cols="7">
          <VTextField
            :model-value="date" label="Fecha" type="date" density="comfortable"
            prepend-inner-icon="ri-calendar-line" variant="outlined"
            clearable @update:model-value="onDateInput" @click:clear="onDateInput('')"
          />
        </VCol>
        <VCol cols="5">
          <!-- Decisión secundaria (casi nadie se aparta de "fecha fija") — un
               checkbox chico en vez de un radio grande, para no competir en
               peso visual con "¿A qué hora?", que sí es una decisión
               central. Misma fila que Fecha, aprovecha el espacio libre. -->
          <VCheckbox
            :model-value="flexibility === 'flex'" color="primary" density="compact" hide-details
            label="Flexible ± 2 días"
            @update:model-value="v => flexibility = v ? 'flex' : 'fija'"
          />
        </VCol>
      </VRow>
    </template>

    <template v-if="showHourSection">
      <div class="text-subtitle-1 font-weight-bold mb-3">¿A qué hora?</div>
      <VRadioGroup v-model="hourMode" inline hide-details density="comfortable" class="radio-pill-group mb-4">
        <VRadio value="flexible" label="Horario flexible" />
        <VRadio value="exacta" label="Hora exacta" />
      </VRadioGroup>

      <VRow v-if="showWindows" dense class="mb-2">
        <VCol v-for="w in WINDOWS" :key="w.value" cols="6" sm="3">
          <VCard
            variant="outlined" class="pa-3 h-100 position-relative schedule-tile"
            :class="{ 'schedule-tile--selected': window_ === w.value }"
            style="cursor: pointer;" @click="window_ = w.value"
          >
            <VIcon
              v-if="window_ === w.value" icon="ri-checkbox-circle-fill" color="primary" size="14"
              style="position:absolute; top:6px; right:6px;"
            />
            <VIcon
              :icon="w.icon" size="18" class="mb-1"
              :color="window_ === w.value ? 'primary' : undefined"
            />
            <div class="text-body-2 font-weight-bold">{{ w.title }}</div>
            <div class="text-caption text-medium-emphasis">{{ w.range }}</div>
          </VCard>
        </VCol>
      </VRow>
      <AppTimeField v-if="showExact" v-model="exactTime" label="Hora exacta" density="comfortable" class="mb-2" />
    </template>
  </div>
</template>

<style scoped>
/* Radio "tipo Materio" en caja compartida — reemplaza el VBtnToggle (pill
   plano, sin punto de radio) por dos celdas con borde + radio nativo del
   tema (ya trae su propio ícono con sombra al elegir, ver _radio.scss). Más
   prolijo que el toggle y reusa el radio ya tematizado, no uno inventado. */
.radio-pill-group :deep(.v-selection-control-group) {
  display: flex;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  overflow: hidden;
}
.radio-pill-group :deep(.v-radio) {
  flex: 1 1 0;
  min-width: 0;
  margin: 0 !important;
  padding: 10px 14px;
  transition: background-color 0.15s ease;
}
.radio-pill-group :deep(.v-radio:not(:last-child)) {
  border-inline-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.radio-pill-group :deep(.v-radio.v-selection-control--dirty) {
  background: rgba(var(--v-theme-primary), 0.06);
}
.radio-pill-group :deep(.v-label) {
  font-size: 0.875rem;
  white-space: nowrap;
}

/* Mismo lenguaje visual que ContinueModePicker.vue (.price-tile) — tile
   seleccionable con acento a la izquierda + sombra suave al elegir, en vez
   del contraste plano variant="tonal"/"outlined" que dejaba el texto sin
   elegir casi ilegible. */
.schedule-tile {
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.schedule-tile:hover {
  border-color: rgb(var(--v-theme-primary));
}
.schedule-tile--selected {
  border-color: rgb(var(--v-theme-primary)) !important;
  border-inline-start: 3px solid rgb(var(--v-theme-primary)) !important;
  box-shadow: 0 4px 14px rgba(var(--v-theme-primary), 0.22);
}
</style>
