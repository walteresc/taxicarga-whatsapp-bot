<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'

import {
  driversService,
} from '@/services/personnelService'
import {
  fetchPizarra, pizarraAssign, pizarraEdit, pizarraMove, pizarraUnassign,
} from '@/services/pizarraService'

const PX_PER_MIN = 2.2            // 1h = 132px
const ROW_H = 76
const SNAP = 15                   // min
const HOURS = Array.from({ length: 25 }, (_, i) => i)

const STATE = {
  programado: { label: 'Programado', color: '#3b82f6' },
  en_ruta: { label: 'En ruta', color: '#f59e0b' },
  en_servicio: { label: 'En servicio', color: '#8b5cf6' },
  finalizado: { label: 'Finalizado', color: '#10b981' },
  cancelado: { label: 'Cancelado', color: '#94a3b8' },
}

const date = ref(new Date().toISOString().slice(0, 10))
const board = ref({ resources: [], assignments: [], unassigned: [] })
const loading = ref(true)
const error = ref('')
const scroller = ref(null)
const drivers = ref([])

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

const toMin = hhmm => {
  if (!hhmm) return null
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}
const toHHMM = min => `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`
const soles = n => (n == null ? '—' : `S/ ${Math.round(n).toLocaleString('es-PE')}`)

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    board.value = await fetchPizarra(date.value)
  } catch (e) {
    error.value = e.message || 'No se pudo cargar la pizarra.'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try { drivers.value = (await driversService.list({ pageSize: 200, status: 'active' })).results } catch { /* */ }
  await load()
  await nextTick()
  if (scroller.value) scroller.value.scrollLeft = 6 * 60 * PX_PER_MIN
})

const shiftDay = n => {
  const d = new Date(date.value)
  d.setDate(d.getDate() + n)
  date.value = d.toISOString().slice(0, 10)
  load()
}
const today = () => { date.value = new Date().toISOString().slice(0, 10); load() }

// barras por recurso
const barsByResource = computed(() => {
  const map = {}
  for (const r of board.value.resources) map[r.id] = []
  for (const a of board.value.assignments) {
    if (!map[a.resourceId]) map[a.resourceId] = []
    const start = toMin(a.start) ?? 0
    const end = toMin(a.end) ?? start + 60
    map[a.resourceId].push({ ...a, start, end, dur: Math.max(30, end - start) })
  }
  return map
})

const nowLeft = computed(() => {
  const now = new Date()
  if (date.value !== now.toISOString().slice(0, 10)) return null
  return (now.getHours() * 60 + now.getMinutes()) * PX_PER_MIN
})

// ── Drag de una barra ─────────────────────────────────────────────────────
const drag = reactive({ id: null, dx: 0, dy: 0, orig: null })
let dragStart = null
const onBarDown = (e, bar) => {
  if (e.target.closest('button')) return
  dragStart = { px: e.clientX, py: e.clientY, bar }
  drag.id = bar.id
  drag.dx = 0
  drag.dy = 0
  drag.orig = bar
  window.addEventListener('pointermove', onBarMove)
  window.addEventListener('pointerup', onBarUp)
}
const onBarMove = e => {
  if (!dragStart) return
  drag.dx = e.clientX - dragStart.px
  drag.dy = e.clientY - dragStart.py
}
const onBarUp = async () => {
  window.removeEventListener('pointermove', onBarMove)
  window.removeEventListener('pointerup', onBarUp)
  const { bar } = dragStart
  const dx = drag.dx
  const dy = drag.dy
  dragStart = null
  drag.id = null
  if (Math.abs(dx) < 6 && Math.abs(dy) < 6) { openPanel(bar); return }

  const deltaMin = Math.round((dx / PX_PER_MIN) / SNAP) * SNAP
  let newStart = Math.max(0, Math.min(24 * 60 - bar.dur, bar.start + deltaMin))
  const resources = board.value.resources
  const idx = resources.findIndex(r => r.id === bar.resourceId)
  const rowDelta = Math.round(dy / ROW_H)
  const newIdx = Math.max(0, Math.min(resources.length - 1, idx + rowDelta))
  const newResourceId = resources[newIdx].id

  if (newStart === bar.start && newResourceId === bar.resourceId) return
  try {
    await pizarraMove({ assignmentId: bar.id, resourceId: newResourceId, start: toHHMM(newStart) })
    await load()
  } catch (e) {
    notify(e.message || 'No se pudo mover.', 'error')
    await load()
  }
}
const barLiveStyle = bar => {
  if (drag.id !== bar.id) return {}
  return { transform: `translate(${drag.dx}px, ${drag.dy}px)`, zIndex: 30, opacity: 0.9 }
}

// ── Panel lateral ────────────────────────────────────────────────────────
const panel = ref(false)
const sel = ref(null)
const form = reactive({ driverId: null, start: '', end: '', state: '' })
const openPanel = bar => {
  sel.value = bar
  Object.assign(form, {
    driverId: null, start: toHHMM(bar.start), end: bar.end ? toHHMM(bar.end) : '', state: bar.state,
  })
  panel.value = true
}
const driverOptions = computed(() => drivers.value.map(d => ({ title: d.name, value: d.id })))

const saveEdit = async () => {
  try {
    await pizarraEdit({
      assignmentId: sel.value.id,
      driverId: form.driverId ?? undefined,
      start: form.start || undefined,
      end: form.end || undefined,
      state: form.state || undefined,
    })
    panel.value = false
    notify('Guardado.')
    await load()
  } catch (e) {
    notify(e.message || 'No se pudo guardar.', 'error')
  }
}
const unassign = async () => {
  try {
    await pizarraUnassign(sel.value.id)
    panel.value = false
    notify('Servicio devuelto a "Sin asignar".')
    await load()
  } catch (e) {
    notify(e.message || 'No se pudo quitar.', 'error')
  }
}

// ── Asignar un servicio sin asignar ──────────────────────────────────────
const assignDialog = ref(false)
const assignForm = reactive({ service: null, resourceId: null, start: '' })
const openAssign = svc => {
  Object.assign(assignForm, { service: svc, resourceId: null, start: svc.start || '08:00' })
  assignDialog.value = true
}
const resourceOptions = computed(() =>
  board.value.resources.map(r => ({ title: `${r.label}${r.driverName ? ` · ${r.driverName}` : ''}`, value: r.id })))
const doAssign = async () => {
  try {
    await pizarraAssign({
      serviceId: assignForm.service.serviceId,
      resourceId: assignForm.resourceId,
      start: assignForm.start,
    })
    assignDialog.value = false
    notify('Servicio asignado.')
    await load()
  } catch (e) {
    notify(e.message || 'No se pudo asignar.', 'error')
  }
}
</script>

<template>
  <section>
    <div class="d-flex flex-wrap align-center justify-space-between ga-4 mb-4">
      <div>
        <h1 class="text-h4 font-weight-bold mb-1">Pizarra</h1>
        <p class="text-body-1 text-medium-emphasis mb-0">
          Servicios del día por vehículo. Arrastrá una barra para cambiar hora o vehículo; clic para editar.
        </p>
      </div>
      <div class="d-flex align-center ga-1">
        <VBtn icon="ri-arrow-left-s-line" variant="tonal" @click="shiftDay(-1)" />
        <VTextField v-model="date" type="date" density="compact" hide-details style="max-width: 175px;" @update:model-value="load" />
        <VBtn icon="ri-arrow-right-s-line" variant="tonal" @click="shiftDay(1)" />
        <VBtn variant="text" @click="today">Hoy</VBtn>
      </div>
    </div>

    <VAlert v-if="error" type="error" variant="tonal" class="mb-4">
      {{ error }}
      <template #append><VBtn size="small" variant="text" @click="load">Reintentar</VBtn></template>
    </VAlert>

    <!-- Sin asignar -->
    <VCard v-if="board.unassigned.length" class="mb-4">
      <VCardText class="d-flex flex-wrap align-center ga-2">
        <span class="text-overline text-medium-emphasis me-2">Sin asignar</span>
        <VChip
          v-for="s in board.unassigned" :key="s.serviceId"
          :color="s.published ? 'warning' : 'primary'" variant="tonal"
          @click="s.published ? null : openAssign(s)"
        >
          <VIcon start :icon="s.published ? 'ri-loader-4-line' : 'ri-add-line'" size="14" />
          {{ s.serviceCode }} · {{ s.customer }} · {{ s.start || s.scheduleText || 's/h' }}
          <span v-if="s.published" class="ms-1 text-caption">(publicada)</span>
        </VChip>
      </VCardText>
    </VCard>

    <VCard>
      <div v-if="loading" class="text-center py-12"><VProgressCircular indeterminate color="primary" /></div>
      <div v-else-if="!board.resources.length" class="text-center text-medium-emphasis py-12">
        No hay vehículos activos. Cargalos en Mi flota → Vehículos.
      </div>
      <div v-else class="pz-wrap">
        <!-- rail de recursos -->
        <div class="pz-rail">
          <div class="pz-rail-head" />
          <div v-for="r in board.resources" :key="r.id" class="pz-rail-row" :style="{ height: ROW_H + 'px' }">
            <div class="font-weight-medium text-truncate">{{ r.label }}</div>
            <div class="text-caption text-medium-emphasis text-truncate">
              {{ r.driverName || 'sin conductor' }}<span v-if="r.sublabel"> · {{ r.sublabel }}</span>
            </div>
          </div>
        </div>

        <!-- timeline -->
        <div ref="scroller" class="pz-scroll">
          <div class="pz-grid" :style="{ width: (24 * 60 * PX_PER_MIN) + 'px' }">
            <div class="pz-hours">
              <div
                v-for="h in HOURS" :key="h" class="pz-hour"
                :style="{ left: (h * 60 * PX_PER_MIN) + 'px' }"
              >
                {{ String(h).padStart(2, '0') }}:00
              </div>
            </div>
            <div
              v-if="nowLeft != null" class="pz-now" :style="{ left: nowLeft + 'px' }"
            />
            <div
              v-for="r in board.resources" :key="r.id" class="pz-lane"
              :style="{ height: ROW_H + 'px' }"
            >
              <div
                v-for="h in HOURS" :key="h" class="pz-tick"
                :style="{ left: (h * 60 * PX_PER_MIN) + 'px' }"
              />
              <div
                v-for="bar in (barsByResource[r.id] || [])" :key="bar.id"
                class="pz-bar"
                :style="{
                  left: (bar.start * PX_PER_MIN) + 'px',
                  width: (bar.dur * PX_PER_MIN) + 'px',
                  borderLeftColor: (STATE[bar.state]?.color || '#64748b'),
                  ...barLiveStyle(bar),
                }"
                @pointerdown="onBarDown($event, bar)"
              >
                <div class="pz-bar-title text-truncate">{{ bar.serviceCode }} · {{ bar.customer }}</div>
                <div class="pz-bar-sub text-truncate">
                  {{ toHHMM(bar.start) }}<span v-if="bar.end">–{{ toHHMM(bar.end) }}</span>
                  <span v-if="bar.mode === 'tercerizado'"> · 🚚</span>
                  · {{ soles(bar.price) }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <VDivider />
      <VCardText class="d-flex flex-wrap ga-4 text-caption">
        <span v-for="(s, k) in STATE" :key="k" class="d-inline-flex align-center ga-1">
          <span class="pz-dot" :style="{ background: s.color }" /> {{ s.label }}
        </span>
      </VCardText>
    </VCard>

    <!-- panel editar barra -->
    <VNavigationDrawer v-model="panel" location="right" temporary width="360">
      <div v-if="sel" class="pa-4">
        <div class="d-flex align-center justify-space-between mb-3">
          <h3 class="text-h6">{{ sel.serviceCode }}</h3>
          <VBtn icon="ri-close-line" variant="text" size="small" @click="panel = false" />
        </div>
        <p class="text-body-2 mb-1">{{ sel.customer }}</p>
        <p class="text-caption text-medium-emphasis mb-4">{{ sel.route }}</p>

        <VSelect v-model="form.driverId" :items="driverOptions" label="Conductor" clearable class="mb-3" />
        <div class="d-flex ga-2 mb-3">
          <VTextField v-model="form.start" type="time" label="Inicio" density="compact" hide-details />
          <VTextField v-model="form.end" type="time" label="Fin" density="compact" hide-details />
        </div>
        <VSelect
          v-model="form.state" label="Estado" class="mb-4"
          :items="Object.entries(STATE).map(([value, s]) => ({ title: s.label, value }))"
        />

        <VBtn block color="primary" class="mb-2" @click="saveEdit">Guardar</VBtn>
        <VBtn block variant="text" color="error" @click="unassign">Quitar asignación</VBtn>
      </div>
    </VNavigationDrawer>

    <!-- asignar servicio -->
    <VDialog v-model="assignDialog" max-width="440">
      <VCard v-if="assignForm.service">
        <VCardTitle>Asignar {{ assignForm.service.serviceCode }}</VCardTitle>
        <VCardText>
          <p class="text-body-2 mb-3">{{ assignForm.service.customer }} · {{ assignForm.service.route }}</p>
          <VSelect v-model="assignForm.resourceId" :items="resourceOptions" label="Vehículo" class="mb-3" />
          <VTextField v-model="assignForm.start" type="time" label="Hora de inicio" density="compact" hide-details />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="assignDialog = false">Cancelar</VBtn>
          <VBtn color="primary" :disabled="!assignForm.resourceId" @click="doAssign">Asignar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>

<style scoped>
.pz-wrap { display: flex; }
.pz-rail { flex: 0 0 200px; border-inline-end: 1px solid rgb(var(--v-border-color), var(--v-border-opacity)); }
.pz-rail-head { height: 32px; border-block-end: 1px solid rgb(var(--v-border-color), var(--v-border-opacity)); }
.pz-rail-row {
  display: flex; flex-direction: column; justify-content: center;
  padding-inline: 12px; border-block-end: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
}
.pz-scroll { flex: 1 1 auto; overflow-x: auto; }
.pz-grid { position: relative; }
.pz-hours { height: 32px; position: relative; border-block-end: 1px solid rgb(var(--v-border-color), var(--v-border-opacity)); }
.pz-hour {
  position: absolute; top: 8px; font-size: 11px; color: rgb(var(--v-theme-on-surface), 0.6);
  transform: translateX(-50%);
}
.pz-lane { position: relative; border-block-end: 1px solid rgb(var(--v-border-color), var(--v-border-opacity)); }
.pz-tick { position: absolute; top: 0; bottom: 0; width: 1px; background: rgb(var(--v-border-color), 0.5); }
.pz-now { position: absolute; top: 32px; bottom: 0; width: 2px; background: rgb(var(--v-theme-error)); z-index: 5; }
.pz-bar {
  position: absolute; top: 6px; bottom: 6px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-left: 4px solid #64748b;
  border-radius: 6px; padding: 4px 8px; cursor: grab; overflow: hidden;
  box-shadow: 0 1px 3px rgb(0 0 0 / 12%); user-select: none;
}
.pz-bar:active { cursor: grabbing; }
.pz-bar-title { font-size: 12px; font-weight: 600; }
.pz-bar-sub { font-size: 11px; color: rgb(var(--v-theme-on-surface), 0.6); }
.pz-dot { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
</style>
