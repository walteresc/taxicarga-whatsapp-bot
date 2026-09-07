<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { driversService } from '@/services/personnelService'
import {
  fetchPizarra, pizarraAssign, pizarraEdit, pizarraMove, pizarraUnassign,
} from '@/services/pizarraService'
import ServiceViewDialog from '@/pages/atencion/bandeja-entrada/components/ServiceViewDialog.vue'

const PX_PER_MIN = 2.4
const ROW_H = 84
const SNAP = 15
const HOURS = Array.from({ length: 25 }, (_, i) => i)
const HOURS_H = 28
const CHIP_W = 160
const CHIP_H = 58

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
const routeOf = x => `${x.originDistrict || '?'} → ${x.destDistrict || '?'}`

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
  if (scroller.value) scroller.value.scrollLeft = 5.5 * 60 * PX_PER_MIN
  syncView()
  window.addEventListener('resize', syncView)
})
onBeforeUnmount(() => window.removeEventListener('resize', syncView))
watch(() => board.value, () => nextTick(syncView), { deep: false })

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

// Servicios sin asignar, ubicados sobre la línea de tiempo por su hora + apilados si chocan.
const unassignedPlaced = computed(() => {
  const maxLeft = 24 * 60 * PX_PER_MIN - CHIP_W
  const items = board.value.unassigned
    .map(s => ({ ...s, _left: Math.min(maxLeft, Math.max(0, (toMin(s.start) ?? 0) * PX_PER_MIN)) }))
    .sort((a, b) => a._left - b._left)
  const rowRight = []
  for (const it of items) {
    let r = rowRight.findIndex(right => right <= it._left)
    if (r === -1) { r = rowRight.length; rowRight.push(0) }
    rowRight[r] = it._left + CHIP_W
    it._row = r
  }
  return items
})
const unassignedRows = computed(() =>
  Math.max(1, ...unassignedPlaced.value.map(i => i._row + 1)))
const unLaneH = computed(() =>
  Math.max(46, board.value.unassigned.length ? unassignedRows.value * (CHIP_H + 6) + 8 : 0))
const headH = computed(() => HOURS_H + unLaneH.value)

const nowLeft = computed(() => {
  const now = new Date()
  if (date.value !== now.toISOString().slice(0, 10)) return null
  return (now.getHours() * 60 + now.getMinutes()) * PX_PER_MIN
})

// ── Drag de una barra asignada ─────────────────────────────────────────
// La barra se "levanta" al mantenerla presionada un instante. Si en cambio se
// mueve el dedo enseguida, el gesto se toma como navegación (pan) y la barra
// no se toca — así un clic al vuelo mientras se navega no mueve el servicio.
const ARM_MS = 160
const drag = reactive({ id: null, dx: 0, dy: 0 })
let dragStart = null
let armTimer = null
const endBarGesture = () => {
  window.removeEventListener('pointermove', onBarMove)
  window.removeEventListener('pointerup', onBarUp)
  clearTimeout(armTimer)
}
const onBarDown = (e, bar) => {
  if (e.button !== 0 || e.target.closest('button')) return
  dragStart = { px: e.clientX, py: e.clientY, bar, armed: false }
  drag.id = null
  drag.dx = 0
  drag.dy = 0
  window.addEventListener('pointermove', onBarMove)
  window.addEventListener('pointerup', onBarUp)
  armTimer = setTimeout(() => {
    if (dragStart) { dragStart.armed = true; drag.id = bar.id }
  }, ARM_MS)
}
const onBarMove = e => {
  if (!dragStart) return
  const dx = e.clientX - dragStart.px
  const dy = e.clientY - dragStart.py
  if (!dragStart.armed) {
    if (Math.abs(dx) > 6 || Math.abs(dy) > 6) {
      // se movió antes de "levantar" la barra → es un gesto para navegar
      const { px, py } = dragStart
      endBarGesture()
      dragStart = null
      drag.id = null
      beginPan(px, py)
      onBoardPan(e)
    }
    return
  }
  drag.dx = dx
  drag.dy = dy
}
const onBarUp = async e => {
  endBarGesture()
  const ds = dragStart
  const dx = drag.dx
  const dy = drag.dy
  dragStart = null
  drag.id = null
  drag.dx = 0
  drag.dy = 0
  if (!ds) return
  if (!ds.armed || (Math.abs(dx) < 6 && Math.abs(dy) < 6)) { openPanel(ds.bar); return }

  const bar = ds.bar
  const dropEl = document.elementFromPoint(e.clientX, e.clientY)

  // Soltar sobre la zona "sin asignar" → quitar la asignación.
  if (dropEl?.closest('.pz-unassigned, .pz-rail-head')) {
    try {
      await pizarraUnassign(bar.id)
      notify(`${bar.serviceCode} vuelve a "Sin asignar".`)
      await load()
    } catch (err) { notify(err.message || 'No se pudo quitar.', 'error') }
    return
  }

  const lane = dropEl?.closest('.pz-lane')
  if (!lane) return
  const rid = lane.dataset.resourceId
  const rect = lane.getBoundingClientRect()
  let mins = Math.round(((e.clientX - rect.left) / PX_PER_MIN) / SNAP) * SNAP
  mins = Math.max(0, Math.min(24 * 60 - bar.dur, mins))
  if (mins === bar.start && rid === bar.resourceId) return

  const a = board.value.assignments.find(x => x.id === bar.id)
  if (!a) return
  const prev = { start: a.start, end: a.end, resourceId: a.resourceId }
  a.start = toHHMM(mins)
  a.end = toHHMM(mins + bar.dur)
  a.resourceId = rid
  try {
    await pizarraMove({ assignmentId: bar.id, resourceId: rid, start: toHHMM(mins) })
  } catch (err) {
    Object.assign(a, prev)
    notify(err.message || 'No se pudo mover.', 'error')
  }
}
const barLiveStyle = bar => (drag.id === bar.id
  ? {
    transform: `translate(${drag.dx}px, ${drag.dy}px) scale(1.02)`,
    zIndex: 30,
    opacity: 0.95,
    pointerEvents: 'none',
    boxShadow: '0 10px 26px rgb(0 0 0 / 30%)',
  }
  : {})

// ── Drag de un servicio sin asignar → soltar sobre la fila de un vehículo ─
const chipDrag = reactive({ item: null, x: 0, y: 0 })
let chipStart = null
const onChipDown = (e, s) => {
  if (e.button !== 0 || s.published) return
  e.preventDefault()
  chipStart = { px: e.clientX, py: e.clientY, s }
  Object.assign(chipDrag, { item: s, x: e.clientX, y: e.clientY })
  window.addEventListener('pointermove', onChipMove)
  window.addEventListener('pointerup', onChipUp)
}
const onChipMove = e => {
  if (!chipStart) return
  chipDrag.x = e.clientX
  chipDrag.y = e.clientY
}
const onChipUp = async e => {
  window.removeEventListener('pointermove', onChipMove)
  window.removeEventListener('pointerup', onChipUp)
  const st = chipStart
  chipStart = null
  chipDrag.item = null
  if (!st) return
  if (Math.abs(e.clientX - st.px) + Math.abs(e.clientY - st.py) < 6) { openDetail(st.s.leadId); return }

  const lane = document.elementFromPoint(e.clientX, e.clientY)?.closest('.pz-lane')
  if (!lane) { notify('Soltá el servicio sobre la fila de un vehículo.', 'warning'); return }
  const rid = lane.dataset.resourceId
  const rect = lane.getBoundingClientRect()
  let mins = Math.round(((e.clientX - rect.left) / PX_PER_MIN) / SNAP) * SNAP
  mins = Math.max(0, Math.min(23 * 60 + 45, mins))
  try {
    await pizarraAssign({ serviceId: st.s.serviceId, resourceId: rid, start: toHHMM(mins) })
    notify(`${st.s.serviceCode} asignado a las ${toHHMM(mins)}.`)
    await load()
  } catch (err) {
    notify(err.message || 'No se pudo asignar.', 'error')
  }
}

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

// ── Asignar un servicio sin asignar (diálogo) ──────────────────────────
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

// ── Vista general: minimapa + navegación entre servicios fuera de pantalla ─
const TOTAL_W = 24 * 60 * PX_PER_MIN
const minimap = ref(null)
const view = reactive({ x: 0, w: 1, y: 0, h: 1 })
const syncView = () => {
  const el = scroller.value
  if (!el) return
  view.x = el.scrollLeft
  view.w = Math.max(1, el.clientWidth - 190)
  view.y = el.scrollTop
  view.h = Math.max(1, el.clientHeight - headH.value)
}

// Todos los servicios del día (asignados + sin asignar) ordenados por hora.
const allStops = computed(() => {
  const out = []
  for (const a of board.value.assignments) {
    const m = toMin(a.start)
    if (m == null) continue
    out.push({ key: `a${a.id}`, min: m, kind: 'assigned', mode: a.mode, label: `${a.serviceCode} · ${routeOf(a)} · ${a.start}` })
  }
  for (const s of board.value.unassigned) {
    const m = toMin(s.start)
    out.push({
      key: `u${s.serviceId}`, min: m ?? 0, kind: 'unassigned', mode: s.mode, noTime: m == null,
      label: `${s.serviceCode} · ${routeOf(s)} · ${s.start || s.scheduleText || 's/h'}`,
    })
  }
  return out.sort((x, y) => x.min - y.min)
})

const leftHidden = computed(() => allStops.value.filter(s => s.min * PX_PER_MIN < view.x - 4))
const rightHidden = computed(() => allStops.value.filter(s => s.min * PX_PER_MIN > view.x + view.w + 4))
const leftUn = computed(() => leftHidden.value.filter(s => s.kind === 'unassigned').length)
const rightUn = computed(() => rightHidden.value.filter(s => s.kind === 'unassigned').length)
const rowsAbove = computed(() => Math.max(0, Math.floor((view.y + 2) / ROW_H)))
const rowsBelow = computed(() =>
  Math.max(0, resources.value.length - Math.ceil((view.y + view.h) / ROW_H)))

const scrollToMin = m => {
  const el = scroller.value
  if (!el) return
  el.scrollTo({ left: Math.max(0, m * PX_PER_MIN - view.w / 2), behavior: 'smooth' })
}
const goPrev = () => { const s = leftHidden.value[leftHidden.value.length - 1]; if (s) scrollToMin(s.min) }
const goNext = () => { const s = rightHidden.value[0]; if (s) scrollToMin(s.min) }
const scrollTop = () => scroller.value?.scrollTo({ top: 0, behavior: 'smooth' })
const scrollBottom = () => scroller.value?.scrollTo({ top: 999999, behavior: 'smooth' })

const onMinimapClick = e => {
  const el = minimap.value
  if (!el) return
  const frac = (e.clientX - el.getBoundingClientRect().left) / el.clientWidth
  scrollToMin(Math.min(1440, Math.max(0, frac)) * 1440)
}
// Arrastrar el tablero (zona vacía) para navegar.
const panning = ref(false)
let panStart = null
const beginPan = (px, py) => {
  const el = scroller.value
  if (!el) return
  panStart = { px, py, sl: el.scrollLeft, st: el.scrollTop }
  panning.value = true
  window.addEventListener('pointermove', onBoardPan)
  window.addEventListener('pointerup', onBoardPanUp)
}
const onBoardDown = e => {
  if (e.button !== 0 || e.target.closest('.pz-bar, .pz-chip, .v-btn, button, a, input')) return
  e.preventDefault()
  beginPan(e.clientX, e.clientY)
}
const onBoardPan = e => {
  const el = scroller.value
  if (!panStart || !el) return
  el.scrollLeft = panStart.sl - (e.clientX - panStart.px)
  el.scrollTop = panStart.st - (e.clientY - panStart.py)
}
const onBoardPanUp = () => {
  window.removeEventListener('pointermove', onBoardPan)
  window.removeEventListener('pointerup', onBoardPanUp)
  panning.value = false
  panStart = null
}

let mmDrag = null
const onMmRectDown = e => {
  e.stopPropagation()
  mmDrag = { px: e.clientX, sx: view.x }
  window.addEventListener('pointermove', onMmRectMove)
  window.addEventListener('pointerup', onMmRectUp)
}
const onMmRectMove = e => {
  const el = minimap.value
  const sc = scroller.value
  if (!el || !sc) return
  sc.scrollLeft = Math.max(0, mmDrag.sx + ((e.clientX - mmDrag.px) / el.clientWidth) * TOTAL_W)
}
const onMmRectUp = () => {
  window.removeEventListener('pointermove', onMmRectMove)
  window.removeEventListener('pointerup', onMmRectUp)
  mmDrag = null
}
</script>

<template>
  <section>
    <div class="d-flex flex-wrap align-center justify-space-between ga-4 mb-4">
      <div>
        <h1 class="text-h4 font-weight-bold mb-1">Pizarra</h1>
        <p class="text-body-1 text-medium-emphasis mb-0">
          Arrastrá el tablero para navegar · mantené presionada una barra para moverla (o soltala en "Sin asignar" para liberarla) · clic edita · clic derecho más opciones.
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

    <VCard>
      <div class="d-flex flex-wrap align-center justify-space-between ga-2 px-4 py-2">
        <span class="text-caption text-medium-emphasis">
          {{ resources.length }} vehículo(s) · {{ board.unassigned.length }} sin asignar
        </span>
        <div class="d-flex align-center ga-1">
          <VBtn
            size="small" variant="tonal" :disabled="!leftHidden.length"
            :color="leftUn ? 'warning' : undefined" prepend-icon="ri-arrow-left-s-line"
            :title="leftHidden.length ? `${leftHidden.length} servicio(s) antes de la vista` : ''"
            @click="goPrev"
          >
            {{ leftHidden.length || '·' }}<span v-if="leftUn" class="text-caption"> ⚠</span>
          </VBtn>
          <VBtn
            size="small" variant="tonal" :disabled="!rightHidden.length"
            :color="rightUn ? 'warning' : undefined" append-icon="ri-arrow-right-s-line"
            :title="rightHidden.length ? `${rightHidden.length} servicio(s) después de la vista` : ''"
            @click="goNext"
          >
            <span v-if="rightUn" class="text-caption">⚠ </span>{{ rightHidden.length || '·' }}
          </VBtn>
          <VBtn v-if="hiddenResources.length" size="small" variant="tonal" prepend-icon="ri-add-line" @click="addDialog = true">
            Agregar vehículo
          </VBtn>
        </div>
      </div>
      <VDivider />

      <div v-if="!loading && resources.length" class="pz-minimap-wrap px-4 pt-3 pb-1">
        <div ref="minimap" class="pz-minimap" @click="onMinimapClick">
          <div v-for="h in [3, 6, 9, 12, 15, 18, 21]" :key="h" class="pz-mm-tick" :style="{ left: (h / 24 * 100) + '%' }" />
          <div
            v-for="s in allStops" :key="s.key"
            class="pz-mm-mark" :class="{ 'pz-mm-mark--un': s.kind === 'unassigned' }"
            :style="{
              left: (s.min / 1440 * 100) + '%',
              background: s.kind === 'unassigned' ? '#d97706' : (MODE[s.mode]?.color || '#64748b'),
            }"
            :title="s.label"
          />
          <div
            class="pz-mm-view"
            :style="{ left: (view.x / TOTAL_W * 100) + '%', width: (view.w / TOTAL_W * 100) + '%' }"
            @pointerdown="onMmRectDown"
          />
        </div>
        <div class="d-flex justify-space-between text-caption text-disabled px-1">
          <span>00h</span><span>06h</span><span>12h</span><span>18h</span><span>24h</span>
        </div>
      </div>

      <div v-if="loading" class="text-center py-12"><VProgressCircular indeterminate color="primary" /></div>
      <div v-else-if="!resources.length" class="text-center text-medium-emphasis py-12">
        No hay vehículos en la pizarra.
        <VBtn v-if="hiddenResources.length" variant="text" @click="addDialog = true">Agregar</VBtn>
      </div>

      <div v-else class="pz-boardwrap">
        <div v-if="rowsAbove" class="pz-vedge pz-vedge--t" @click="scrollTop">▲ {{ rowsAbove }} vehículo(s)</div>
        <div v-if="rowsBelow" class="pz-vedge pz-vedge--b" @click="scrollBottom">▼ {{ rowsBelow }} vehículo(s)</div>
        <div
          ref="scroller" class="pz-board" :class="{ 'pz-board--pan': panning }"
          @scroll="syncView" @pointerdown="onBoardDown"
        >
        <div class="pz-inner">
          <!-- carril de vehículos (fijo a la izquierda) -->
          <div class="pz-rail">
            <div class="pz-rail-head" :style="{ height: headH + 'px' }">
              <span class="text-caption text-medium-emphasis">Sin asignar</span>
            </div>
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

          <!-- línea de tiempo -->
          <div class="pz-grid" :style="{ width: (24 * 60 * PX_PER_MIN) + 'px' }">
            <div class="pz-head" :style="{ height: headH + 'px' }">
              <div class="pz-hours" :style="{ height: HOURS_H + 'px' }">
                <div v-for="h in HOURS" :key="h" class="pz-hour" :style="{ left: (h * 60 * PX_PER_MIN) + 'px' }">
                  {{ String(h).padStart(2, '0') }}:00
                </div>
              </div>
              <div
                class="pz-unassigned" :class="{ 'pz-unassigned--drop': drag.id }"
                :style="{ height: unLaneH + 'px' }"
              >
                <span v-if="!board.unassigned.length" class="pz-un-hint">
                  Soltá una barra aquí para dejarla sin asignar
                </span>
                <div
                  v-for="s in unassignedPlaced" :key="s.serviceId"
                  class="pz-chip" :class="{ 'pz-chip--pub': s.published }"
                  :style="{
                    left: s._left + 'px',
                    top: (s._row * (CHIP_H + 6) + 4) + 'px',
                    width: CHIP_W + 'px',
                    borderInlineStartColor: (MODE[s.mode]?.color || '#64748b'),
                  }"
                  @pointerdown="onChipDown($event, s)"
                  @contextmenu.prevent="openCtx($event, 'unassigned', s)"
                >
                  <div class="pz-l1 text-truncate">
                    {{ s.serviceCode }}<span v-if="s.published" class="text-caption"> · publicada</span>
                  </div>
                  <div class="pz-l2 text-truncate">{{ routeOf(s) }}</div>
                  <div class="pz-l3 text-truncate">
                    <strong>{{ s.start || s.scheduleText || 's/h' }}</strong> · <strong>{{ soles(s.price) }}</strong>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="nowLeft != null" class="pz-now" :style="{ left: nowLeft + 'px' }" />

            <div
              v-for="r in resources" :key="r.id" class="pz-lane"
              :data-resource-id="r.id" :style="{ height: ROW_H + 'px' }"
            >
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
                <div class="pz-l1 text-truncate">
                  <span class="pz-state-dot" :style="{ background: STATE[bar.state]?.color }" />
                  {{ bar.serviceCode }}
                  <span v-if="bar.assignedAuto" title="Asignación automática">⚡</span>
                </div>
                <div class="pz-l2 text-truncate">{{ routeOf(bar) }}</div>
                <div class="pz-l3 text-truncate">
                  <strong>{{ toHHMM(bar.start) }}</strong><span v-if="bar.end" class="pz-dim">–{{ toHHMM(bar.end) }}</span>
                  · <strong>{{ soles(bar.price) }}</strong>
                </div>
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

    <!-- servicio sin asignar "fantasma" mientras se arrastra -->
    <div
      v-if="chipDrag.item" class="pz-chip pz-chip--ghost"
      :style="{ left: chipDrag.x + 'px', top: chipDrag.y + 'px', width: CHIP_W + 'px' }"
    >
      <div class="pz-l1 text-truncate">{{ chipDrag.item.serviceCode }}</div>
      <div class="pz-l2 text-truncate">{{ routeOf(chipDrag.item) }}</div>
      <div class="pz-l3 text-truncate">
        <strong>{{ chipDrag.item.start || chipDrag.item.scheduleText || 's/h' }}</strong> ·
        <strong>{{ soles(chipDrag.item.price) }}</strong>
      </div>
    </div>

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

    <!-- asignar servicio (diálogo) -->
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
          <VListItem v-for="r in hiddenResources" :key="r.id" :title="r.label" :subtitle="r.sublabel">
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
.pz-board {
  position: relative;
  max-block-size: 72vh;
  overflow: auto;
  overscroll-behavior: contain;
  cursor: grab;
}
.pz-board--pan { cursor: grabbing; user-select: none; }
.pz-board--pan .pz-bar,
.pz-board--pan .pz-chip { cursor: grabbing; }
.pz-inner { display: flex; inline-size: min-content; }

.pz-rail {
  position: sticky;
  inset-inline-start: 0;
  z-index: 4;
  flex: 0 0 190px;
  background: rgb(var(--v-theme-surface));
  border-inline-end: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
}
.pz-rail-head {
  position: sticky;
  inset-block-start: 0;
  z-index: 5;
  display: flex;
  align-items: flex-end;
  padding: 6px 12px;
  background: rgb(var(--v-theme-surface));
  border-block-end: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
}
.pz-rail-row {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding-inline: 12px;
  background: rgb(var(--v-theme-surface));
  border-block-end: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
  cursor: context-menu;
}

.pz-grid { position: relative; }
.pz-head {
  position: sticky;
  inset-block-start: 0;
  z-index: 3;
  background: rgb(var(--v-theme-surface));
  border-block-end: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
}
.pz-hours { position: relative; }
.pz-hour {
  position: absolute;
  inset-block-start: 7px;
  font-size: 11px;
  color: rgb(var(--v-theme-on-surface), 0.6);
  transform: translateX(-50%);
}
.pz-unassigned { position: relative; transition: background 0.15s; }
.pz-unassigned--drop {
  background: rgb(var(--v-theme-warning), 0.12);
  outline: 2px dashed rgb(var(--v-theme-warning));
  outline-offset: -3px;
}
.pz-un-hint {
  position: absolute;
  inset-inline-start: 12px;
  inset-block-start: 50%;
  transform: translateY(-50%);
  font-size: 11px;
  color: rgb(var(--v-theme-on-surface), 0.45);
}

.pz-lane { position: relative; border-block-end: 1px solid rgb(var(--v-border-color), var(--v-border-opacity)); }
.pz-tick { position: absolute; inset-block: 0; inline-size: 1px; background: rgb(var(--v-border-color), 0.5); }
.pz-now { position: absolute; inset-block: 0; inline-size: 2px; background: rgb(var(--v-theme-error)); z-index: 1; }

.pz-bar {
  position: absolute;
  inset-block: 5px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 1px;
  padding: 4px 8px;
  overflow: hidden;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-left: 4px solid #64748b;
  border-radius: 6px;
  box-shadow: 0 1px 3px rgb(0 0 0 / 12%);
  cursor: grab;
  user-select: none;
}
.pz-bar:active { cursor: grabbing; }

.pz-chip {
  position: absolute;
  block-size: 58px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 1px;
  padding: 4px 8px;
  overflow: hidden;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-inline-start: 4px solid #64748b;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgb(0 0 0 / 14%);
  cursor: grab;
  user-select: none;
  touch-action: none;
}
.pz-chip:active { cursor: grabbing; }
.pz-chip--pub { opacity: 0.6; cursor: not-allowed; }
.pz-chip--ghost {
  position: fixed;
  z-index: 3000;
  pointer-events: none;
  opacity: 0.95;
  transform: translate(-50%, -50%);
  box-shadow: 0 6px 20px rgb(0 0 0 / 25%);
}

.pz-l1 { font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 5px; }
.pz-l2 { font-size: 12px; color: rgb(var(--v-theme-on-surface), 0.82); }
.pz-l3 { font-size: 12px; color: rgb(var(--v-theme-on-surface), 0.7); }
.pz-l3 strong { color: rgb(var(--v-theme-on-surface), 0.95); }
.pz-dim { color: rgb(var(--v-theme-on-surface), 0.5); font-weight: 400; }
.pz-state-dot { inline-size: 8px; block-size: 8px; border-radius: 50%; display: inline-block; flex: 0 0 auto; }
.pz-bar-swatch { inline-size: 14px; block-size: 8px; border-radius: 2px; display: inline-block; }

/* minimapa: vista general de las 24h */
.pz-minimap {
  position: relative;
  block-size: 34px;
  border-radius: 6px;
  background: rgb(var(--v-theme-on-surface), 0.05);
  border: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
  cursor: pointer;
}
.pz-mm-tick { position: absolute; inset-block: 0; inline-size: 1px; background: rgb(var(--v-border-color), 0.6); }
.pz-mm-mark {
  position: absolute;
  inset-block-end: 0;
  inline-size: 3px;
  block-size: 60%;
  border-radius: 1px;
  transform: translateX(-50%);
}
.pz-mm-mark--un { inset-block-start: 0; inset-block-end: auto; block-size: 55%; inline-size: 4px; }
.pz-mm-view {
  position: absolute;
  inset-block: -1px;
  min-inline-size: 8px;
  border: 2px solid rgb(var(--v-theme-primary));
  border-radius: 4px;
  background: rgb(var(--v-theme-primary), 0.12);
  cursor: grab;
}
.pz-mm-view:active { cursor: grabbing; }

.pz-boardwrap { position: relative; }
.pz-vedge {
  position: absolute;
  inset-inline-start: 50%;
  transform: translateX(-50%);
  z-index: 6;
  padding: 2px 10px;
  font-size: 11px;
  font-weight: 600;
  color: rgb(var(--v-theme-on-primary));
  background: rgb(var(--v-theme-primary));
  border-radius: 999px;
  cursor: pointer;
  box-shadow: 0 2px 8px rgb(0 0 0 / 25%);
}
.pz-vedge--t { inset-block-start: 6px; }
.pz-vedge--b { inset-block-end: 6px; }
</style>
