<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'

import { driversService } from '@/services/personnelService'
import {
  fetchPizarra, pizarraAssign, pizarraEdit, pizarraMove, pizarraUnassign,
} from '@/services/pizarraService'
import ServiceViewDialog from '@/pages/atencion/bandeja-entrada/components/ServiceViewDialog.vue'

const PX_PER_MIN = 2.2
const ROW_H = 76
const SNAP = 15
const HOURS = Array.from({ length: 25 }, (_, i) => i)

const STATE = {
  programado: { label: 'Programado', color: '#3b82f6' },
  en_ruta: { label: 'En ruta', color: '#f59e0b' },
  en_servicio: { label: 'En servicio', color: '#8b5cf6' },
  finalizado: { label: 'Finalizado', color: '#10b981' },
  cancelado: { label: 'Cancelado', color: '#94a3b8' },
}
// Color de la barra según quién ejecuta.
const MODE = {
  propio: { label: 'Nuestro equipo', color: '#2563eb' },
  tercerizado: { label: 'Transportista', color: '#d97706' },
}

const HIDDEN_KEY = 'pizarra:hidden-resources'
const readHidden = () => {
  try { return new Set(JSON.parse(localStorage.getItem(HIDDEN_KEY) || '[]')) } catch { return new Set() }
}
const hidden = ref(readHidden())
const persistHidden = () => {
  try { localStorage.setItem(HIDDEN_KEY, JSON.stringify([...hidden.value])) } catch { /* */ }
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
const routeOf = x => (x.originDistrict || x.destDistrict
  ? `${x.originDistrict || '?'} → ${x.destDistrict || '?'}` : (x.route || ''))

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

const hasAssignment = rid => board.value.assignments.some(a => a.resourceId === rid)
// Vehículos propios siempre visibles salvo que se oculten; ocultos vuelven si tienen servicio.
const resources = computed(() =>
  board.value.resources.filter(r => !hidden.value.has(r.id) || hasAssignment(r.id)))

const barsByResource = computed(() => {
  const map = {}
  for (const r of resources.value) map[r.id] = []
  for (const a of board.value.assignments) {
    if (!map[a.resourceId]) continue
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

// ── Drag de una barra ────────────────────────────────────────────────────
const drag = reactive({ id: null, dx: 0, dy: 0 })
let dragStart = null
const onBarDown = (e, bar) => {
  if (e.button !== 0 || e.target.closest('button')) return
  dragStart = { px: e.clientX, py: e.clientY, bar }
  drag.id = bar.id
  drag.dx = 0
  drag.dy = 0
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
  const ds = dragStart
  const dx = drag.dx
  const dy = drag.dy
  dragStart = null
  drag.id = null
  drag.dx = 0
  drag.dy = 0
  if (!ds) return
  const { bar } = ds
  if (Math.abs(dx) < 6 && Math.abs(dy) < 6) { openPanel(bar); return }

  const deltaMin = Math.round((dx / PX_PER_MIN) / SNAP) * SNAP
  const newStart = Math.max(0, Math.min(24 * 60 - bar.dur, bar.start + deltaMin))
  const rs = resources.value
  const idx = rs.findIndex(r => r.id === bar.resourceId)
  const newIdx = Math.max(0, Math.min(rs.length - 1, idx + Math.round(dy / ROW_H)))
  const newResourceId = rs[newIdx].id
  if (newStart === bar.start && newResourceId === bar.resourceId) return

  const a = board.value.assignments.find(x => x.id === bar.id)
  if (!a) return
  const prev = { start: a.start, end: a.end, resourceId: a.resourceId }
  a.start = toHHMM(newStart)
  a.end = toHHMM(newStart + bar.dur)
  a.resourceId = newResourceId
  try {
    await pizarraMove({ assignmentId: bar.id, resourceId: newResourceId, start: toHHMM(newStart) })
  } catch (e) {
    Object.assign(a, prev)
    notify(e.message || 'No se pudo mover.', 'error')
  }
}
const barLiveStyle = bar => (drag.id === bar.id
  ? { transform: `translate(${drag.dx}px, ${drag.dy}px)`, zIndex: 30, opacity: 0.92 } : {})

// ── Panel de edición rápida ─────────────────────────────────────────────
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
  } catch (e) { notify(e.message || 'No se pudo guardar.', 'error') }
}
const unassignBar = async bar => {
  try {
    await pizarraUnassign(bar.id)
    panel.value = false
    notify('Servicio devuelto a "Sin asignar".')
    await load()
  } catch (e) { notify(e.message || 'No se pudo quitar.', 'error') }
}

// ── Detalle del servicio (modal compartido) ─────────────────────────────
const detailLeadId = ref(null)
const openDetail = leadId => {
  if (!leadId) { notify('Este servicio no tiene lead asociado.', 'warning'); return }
  detailLeadId.value = leadId
}

// ── Menú contextual (clic derecho) ─────────────────────────────────────
const ctx = reactive({ show: false, x: 0, y: 0, kind: null, item: null })
const openCtx = (e, kind, item) => {
  Object.assign(ctx, { show: false, x: e.clientX, y: e.clientY, kind, item })
  nextTick(() => { ctx.show = true })
}

// ── Asignar un servicio sin asignar ────────────────────────────────────
const assignDialog = ref(false)
const assignForm = reactive({ service: null, resourceId: null, start: '' })
const openAssign = svc => {
  Object.assign(assignForm, { service: svc, resourceId: null, start: svc.start || '08:00' })
  assignDialog.value = true
}
const resourceOptions = computed(() =>
  resources.value.map(r => ({ title: `${r.label}${r.driverName ? ` · ${r.driverName}` : ''}`, value: r.id })))
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
  } catch (e) { notify(e.message || 'No se pudo asignar.', 'error') }
}

// ── Ocultar / agregar vehículos ────────────────────────────────────────
const hideResource = rid => { hidden.value.add(rid); hidden.value = new Set(hidden.value); persistHidden() }
const showResource = rid => { hidden.value.delete(rid); hidden.value = new Set(hidden.value); persistHidden() }
const addDialog = ref(false)
const hiddenResources = computed(() =>
  board.value.resources.filter(r => hidden.value.has(r.id) && !hasAssignment(r.id)))
</script>

<template>
  <section>
    <div class="d-flex flex-wrap align-center justify-space-between ga-4 mb-4">
      <div>
        <h1 class="text-h4 font-weight-bold mb-1">Pizarra</h1>
        <p class="text-body-1 text-medium-emphasis mb-0">
          Servicios del día por vehículo. Arrastrá una barra para cambiar hora o vehículo · clic edita · clic derecho más opciones.
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
          :color="s.published ? 'warning' : (MODE[s.mode]?.color ? undefined : 'primary')"
          :style="!s.published && MODE[s.mode] ? { borderInlineStart: `3px solid ${MODE[s.mode].color}` } : {}"
          variant="tonal"
          @click="openDetail(s.leadId)"
          @contextmenu.prevent="openCtx($event, 'unassigned', s)"
        >
          <VIcon start :icon="s.published ? 'ri-loader-4-line' : 'ri-time-line'" size="14" />
          {{ s.serviceCode }} · {{ routeOf(s) }} · {{ s.start || s.scheduleText || 's/h' }}
          <span v-if="s.published" class="ms-1 text-caption">(publicada)</span>
        </VChip>
      </VCardText>
    </VCard>

    <VCard>
      <div class="d-flex align-center justify-space-between px-4 py-2">
        <span class="text-caption text-medium-emphasis">{{ resources.length }} vehículo(s) en pizarra</span>
        <VBtn v-if="hiddenResources.length" size="small" variant="tonal" prepend-icon="ri-add-line" @click="addDialog = true">
          Agregar vehículo
        </VBtn>
      </div>
      <VDivider />
      <div v-if="loading" class="text-center py-12"><VProgressCircular indeterminate color="primary" /></div>
      <div v-else-if="!resources.length" class="text-center text-medium-emphasis py-12">
        No hay vehículos en la pizarra.
        <VBtn v-if="hiddenResources.length" variant="text" @click="addDialog = true">Agregar</VBtn>
      </div>
      <div v-else class="pz-wrap">
        <div class="pz-rail">
          <div class="pz-rail-head" />
          <div
            v-for="r in resources" :key="r.id" class="pz-rail-row" :style="{ height: ROW_H + 'px' }"
            @contextmenu.prevent="openCtx($event, 'resource', r)"
          >
            <div class="font-weight-medium text-truncate">{{ r.label }}</div>
            <div class="text-caption text-medium-emphasis text-truncate">
              {{ r.driverName || 'sin conductor' }}<span v-if="r.sublabel"> · {{ r.sublabel }}</span>
            </div>
          </div>
        </div>

        <div ref="scroller" class="pz-scroll">
          <div class="pz-grid" :style="{ width: (24 * 60 * PX_PER_MIN) + 'px' }">
            <div class="pz-hours">
              <div v-for="h in HOURS" :key="h" class="pz-hour" :style="{ left: (h * 60 * PX_PER_MIN) + 'px' }">
                {{ String(h).padStart(2, '0') }}:00
              </div>
            </div>
            <div v-if="nowLeft != null" class="pz-now" :style="{ left: nowLeft + 'px' }" />
            <div v-for="r in resources" :key="r.id" class="pz-lane" :style="{ height: ROW_H + 'px' }">
              <div v-for="h in HOURS" :key="h" class="pz-tick" :style="{ left: (h * 60 * PX_PER_MIN) + 'px' }" />
              <div
                v-for="bar in (barsByResource[r.id] || [])" :key="bar.id"
                class="pz-bar"
                :style="{
                  left: (bar.start * PX_PER_MIN) + 'px',
                  width: (bar.dur * PX_PER_MIN) + 'px',
                  borderLeftColor: (MODE[bar.mode]?.color || '#64748b'),
                  ...barLiveStyle(bar),
                }"
                @pointerdown="onBarDown($event, bar)"
                @contextmenu.prevent="openCtx($event, 'bar', bar)"
              >
                <div class="pz-bar-title text-truncate">
                  <span class="pz-state-dot" :style="{ background: STATE[bar.state]?.color }" />
                  {{ bar.serviceCode }} · {{ routeOf(bar) }}
                </div>
                <div class="pz-bar-sub text-truncate">
                  {{ toHHMM(bar.start) }}<span v-if="bar.end">–{{ toHHMM(bar.end) }}</span>
                  · {{ soles(bar.price) }}
                  <span v-if="bar.assignedAuto" title="Asignación automática"> · ⚡</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <VDivider />
      <VCardText class="d-flex flex-wrap ga-6 text-caption">
        <div class="d-flex align-center ga-3">
          <span class="text-medium-emphasis">Ejecuta:</span>
          <span v-for="(m, k) in MODE" :key="k" class="d-inline-flex align-center ga-1">
            <span class="pz-bar-swatch" :style="{ background: m.color }" /> {{ m.label }}
          </span>
        </div>
        <div class="d-flex align-center ga-3">
          <span class="text-medium-emphasis">Estado:</span>
          <span v-for="(s, k) in STATE" :key="k" class="d-inline-flex align-center ga-1">
            <span class="pz-state-dot" :style="{ background: s.color }" /> {{ s.label }}
          </span>
        </div>
        <span class="text-medium-emphasis">⚡ = asignación automática</span>
      </VCardText>
    </VCard>

    <!-- menú contextual -->
    <VMenu v-model="ctx.show" :target="[ctx.x, ctx.y]" location="bottom start">
      <VList density="compact" min-width="200">
        <template v-if="ctx.kind === 'bar'">
          <VListItem prepend-icon="ri-file-list-3-line" title="Ver detalle del servicio" @click="openDetail(ctx.item.leadId)" />
          <VListItem prepend-icon="ri-edit-line" title="Editar rápido (hora, conductor…)" @click="openPanel(ctx.item)" />
          <VDivider />
          <VListItem prepend-icon="ri-close-circle-line" title="Quitar asignación" base-color="error" @click="unassignBar(ctx.item)" />
        </template>
        <template v-else-if="ctx.kind === 'unassigned'">
          <VListItem
            prepend-icon="ri-calendar-check-line" title="Asignar a un vehículo"
            :disabled="ctx.item.published" @click="openAssign(ctx.item)"
          />
          <VListItem prepend-icon="ri-file-list-3-line" title="Ver detalle del servicio" @click="openDetail(ctx.item.leadId)" />
        </template>
        <template v-else-if="ctx.kind === 'resource'">
          <VListItem prepend-icon="ri-eye-off-line" title="Quitar de la pizarra" @click="hideResource(ctx.item.id)" />
        </template>
      </VList>
    </VMenu>

    <!-- panel editar barra -->
    <VNavigationDrawer v-model="panel" location="right" temporary width="360">
      <div v-if="sel" class="pa-4">
        <div class="d-flex align-center justify-space-between mb-3">
          <h3 class="text-h6">{{ sel.serviceCode }}</h3>
          <VBtn icon="ri-close-line" variant="text" size="small" @click="panel = false" />
        </div>
        <p class="text-body-2 mb-1">{{ sel.customer }}</p>
        <p class="text-caption text-medium-emphasis mb-3">{{ routeOf(sel) }}</p>
        <VBtn variant="tonal" size="small" prepend-icon="ri-file-list-3-line" class="mb-4" @click="openDetail(sel.leadId)">
          Ver detalle completo
        </VBtn>

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
        <VBtn block variant="text" color="error" @click="unassignBar(sel)">Quitar asignación</VBtn>
      </div>
    </VNavigationDrawer>

    <!-- asignar servicio -->
    <VDialog v-model="assignDialog" max-width="440">
      <VCard v-if="assignForm.service">
        <VCardTitle>Asignar {{ assignForm.service.serviceCode }}</VCardTitle>
        <VCardText>
          <p class="text-body-2 mb-3">{{ routeOf(assignForm.service) }} · {{ assignForm.service.customer }}</p>
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

    <!-- agregar vehículo a la pizarra -->
    <VDialog v-model="addDialog" max-width="420">
      <VCard>
        <VCardTitle>Agregar vehículo a la pizarra</VCardTitle>
        <VList>
          <VListItem
            v-for="r in hiddenResources" :key="r.id"
            :title="r.label" :subtitle="r.sublabel"
          >
            <template #append>
              <VBtn size="small" variant="tonal" @click="showResource(r.id)">Agregar</VBtn>
            </template>
          </VListItem>
          <VListItem v-if="!hiddenResources.length" title="No hay vehículos ocultos." class="text-medium-emphasis" />
        </VList>
        <VCardActions>
          <VSpacer /><VBtn variant="text" @click="addDialog = false">Cerrar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <ServiceViewDialog
      v-if="detailLeadId"
      :lead-id="detailLeadId"
      context="bookings"
      @close="detailLeadId = null"
      @changed="load"
    />

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
  cursor: context-menu;
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
.pz-bar-title { font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 5px; }
.pz-bar-sub { font-size: 11px; color: rgb(var(--v-theme-on-surface), 0.6); }
.pz-state-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex: 0 0 auto; }
.pz-bar-swatch { width: 14px; height: 8px; border-radius: 2px; display: inline-block; }
</style>
