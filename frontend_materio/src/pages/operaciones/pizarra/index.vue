<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { driversService } from '@/services/personnelService'
import { carrierDriversService, carriersService, carrierVehiclesService } from '@/services/carriersService'
import {
  fetchPizarra, pizarraAddCarrierRow, pizarraAssign, pizarraEdit, pizarraMove,
  pizarraRemoveCarrierRow, pizarraUnassign,
} from '@/services/pizarraService'
import ServiceViewDialog from '@/pages/atencion/bandeja-entrada/components/ServiceViewDialog.vue'

const PX_PER_MIN = 2.4
const ROW_H = 90
const SNAP = 15
const HOURS = Array.from({ length: 25 }, (_, i) => i)
const HOURS_H = 28
const CHIP_W = 160
const CHIP_H = 58
const PEEK = 22 // desfase de las barras superpuestas
const FOOT_H = 46 // fila "Agregar vehículo" al pie del carril

const frontId = ref(null) // barra superpuesta traída al frente por clic

// Nomenclatura de colores (única para toda la pizarra).
// Estado operativo de la programación → punto de color en la barra.
const STATE = {
  programado: { label: 'Programado', color: '#64748b' },
  en_ruta: { label: 'En ruta', color: '#f59e0b' },
  en_servicio: { label: 'En servicio', color: '#8b5cf6' },
  finalizado: { label: 'Finalizado', color: '#10b981' },
  cancelado: { label: 'Cancelado', color: '#cbd5e1' },
}
// Quién ejecuta el servicio → color del borde izquierdo de la barra.
const MODE = {
  propio: { label: 'Nuestro equipo', color: '#2563eb' },
  tercerizado: { label: 'Transportista', color: '#d97706' },
}
// Servicios que todavía no están en un vehículo → color de la tarjeta.
const UNASSIGNED = {
  por_asignar: { label: 'Por asignar', color: '#dc2626' },
  publicada: { label: 'Publicada a transportistas', color: '#d97706' },
}

const HIDDEN_KEY = 'pizarra:hidden-resources'
const readHidden = () => {
  try { return new Set(JSON.parse(localStorage.getItem(HIDDEN_KEY) || '[]')) } catch { return new Set() }
}
const hidden = ref(readHidden())
const persistHidden = () => {
  try { localStorage.setItem(HIDDEN_KEY, JSON.stringify([...hidden.value])) } catch { /* */ }
}

// Fecha/hora de Lima, no del navegador ni UTC.
const LIMA = 'America/Lima'
const limaDate = () => new Intl.DateTimeFormat('en-CA', { timeZone: LIMA }).format(new Date())
const limaNowMin = () => {
  const p = new Intl.DateTimeFormat('en-GB', { timeZone: LIMA, hour: '2-digit', minute: '2-digit', hour12: false })
    .formatToParts(new Date())
  return +p.find(x => x.type === 'hour').value * 60 + +p.find(x => x.type === 'minute').value
}

const date = ref(limaDate())
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

// silent = refresco en segundo plano: no desmonta el tablero (así no se pierde
// el scroll ni "salta" al inicio tras asignar/mover/quitar).
let loadToken = 0
let loadCtl = null
const load = async (silent = false) => {
  const token = ++loadToken
  loadCtl?.abort()
  if (!silent) loading.value = true
  error.value = ''
  const ctl = new AbortController()
  loadCtl = ctl
  const timer = setTimeout(() => ctl.abort(), 20000)
  try {
    const data = await fetchPizarra(date.value, ctl.signal)
    if (token === loadToken) board.value = data
  } catch (e) {
    if (token !== loadToken) return
    const msg = e.name === 'AbortError'
      ? 'La pizarra tardó demasiado en responder. Reintentá.'
      : (e.message || 'No se pudo cargar la pizarra.')
    if (silent) notify(msg, 'error')
    else error.value = msg
  } finally {
    clearTimeout(timer)
    if (token === loadToken) loading.value = false
  }
}
const reload = () => load()

const onKeydown = e => {
  if (e.key !== 'Escape') return
  if (picker.show) picker.show = false
  else if (panel.value) panel.value = false
  else if (detailLeadId.value) detailLeadId.value = null
}

onMounted(async () => {
  try { drivers.value = (await driversService.list({ pageSize: 200, status: 'active' })).results } catch { /* */ }
  await load()
  await nextTick()
  if (scroller.value) scroller.value.scrollLeft = 5.5 * 60 * PX_PER_MIN
  syncView()
  window.addEventListener('resize', syncView)
  window.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', syncView)
  window.removeEventListener('keydown', onKeydown)
  stopEdge()
})
watch(() => board.value, () => nextTick(syncView), { deep: false })

const shiftDay = n => {
  const d = new Date(`${date.value}T12:00:00`)
  d.setDate(d.getDate() + n)
  date.value = new Intl.DateTimeFormat('en-CA').format(d)
  load()
}
const today = () => { date.value = limaDate(); load() }

const hasAssignment = rid => board.value.assignments.some(a => a.resourceId === rid)
// Vehículos propios siempre visibles salvo que se oculten; ocultos vuelven si tienen servicio.
// Las filas de transportista son server-driven: nunca se filtran por localStorage.
const resources = computed(() =>
  board.value.resources.filter(r =>
    r.kind === 'tercerizado' || !hidden.value.has(r.id) || hasAssignment(r.id)))

const barsByResource = computed(() => {
  const map = {}
  for (const r of resources.value) map[r.id] = []
  for (const a of board.value.assignments) {
    if (!map[a.resourceId]) continue
    const start = toMin(a.start) ?? 0
    const end = toMin(a.end) ?? start + 60
    map[a.resourceId].push({ ...a, start, end, dur: Math.max(30, end - start) })
  }
  // Servicios que se superponen en un vehículo: se apilan con un pequeño
  // desfase para poder alternar entre ellos con un clic.
  for (const rid of Object.keys(map)) {
    const bars = map[rid].sort((x, y) => x.start - y.start || x.end - y.end)
    let i = 0
    while (i < bars.length) {
      let j = i + 1
      let end = bars[i].end
      while (j < bars.length && bars[j].start < end) { end = Math.max(end, bars[j].end); j += 1 }
      const grp = bars.slice(i, j)
      grp.forEach((b, k) => { b._stack = k; b._stackCount = grp.length })
      i = j
    }
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
  if (date.value !== limaDate()) return null
  return limaNowMin() * PX_PER_MIN
})

const dayLabel = computed(() =>
  new Date(`${date.value}T12:00:00`).toLocaleDateString('es-PE', {
    weekday: 'long', day: 'numeric', month: 'short',
  }))

const summary = computed(() => {
  const sum = arr => arr.reduce((t, x) => t + (x.price || 0), 0)
  const a = board.value.assignments
  const u = board.value.unassigned
  return {
    total: a.length + u.length,
    monto: sum(a) + sum(u),
    asignados: a.length,
    montoAsignados: sum(a),
    sinAsignar: u.length,
    montoSinAsignar: sum(u),
  }
})
const addHour = hhmm => toHHMM(Math.min(24 * 60 - 15, (toMin(hhmm) ?? 480) + 60))
const driverNameOf = id => drivers.value.find(d => d.id === id)?.name || null

// Vehículo + hora bajo el cursor, listos para asignar/mover (scroll-safe).
const targetFromPoint = (cx, cy, durMin) => {
  const lane = document.elementFromPoint(cx, cy)?.closest('.pz-lane')
  if (!lane) return null
  const rect = lane.getBoundingClientRect()
  const raw = Math.max(0, Math.min(24 * 60, (cx - rect.left) / PX_PER_MIN))
  let mins = Math.round(raw / SNAP) * SNAP
  mins = Math.max(0, Math.min(24 * 60 - (durMin || 60), mins))
  return { rid: lane.dataset.resourceId, startMin: mins, rawMin: raw }
}

// Rango del bloque de una hora (formato 12h), p. ej. "3:00 – 4:00 pm".
const hour12 = m => {
  let h = Math.floor(m / 60)
  const ap = h >= 12 && h < 24 ? 'pm' : 'am'
  h = h % 12 || 12
  return `${h}:${String(m % 60).padStart(2, '0')} ${ap}`
}
const hourBlockLabel = rawMin => {
  const hs = Math.floor(Math.min(23 * 60, Math.max(0, rawMin)) / 60) * 60
  return `${hour12(hs)} – ${hour12(hs + 60)}`
}

// Etiqueta flotante con el día + horario de destino mientras se arrastra.
const dragHint = reactive({ show: false, x: 0, y: 0, text: '' })
const setHint = (x, y, text) => Object.assign(dragHint, { show: true, x, y, text })
const hideHint = () => { dragHint.show = false }

// Auto-scroll del tablero al arrastrar cerca de un borde (llegar a horas/filas
// fuera de la vista).
let edgeRAF = null
let lastPointer = { x: 0, y: 0 }
const EDGE = 60
const edgeStep = () => {
  const el = scroller.value
  if (!el) { edgeRAF = null; return }
  const r = el.getBoundingClientRect()
  const { x, y } = lastPointer
  const railR = r.left + 190
  if (x > railR && x < railR + EDGE) el.scrollLeft -= Math.ceil((railR + EDGE - x) / 3)
  else if (x < r.right && x > r.right - EDGE) el.scrollLeft += Math.ceil((x - r.right + EDGE) / 3)
  const topB = r.top + headH.value
  if (y > topB && y < topB + EDGE) el.scrollTop -= Math.ceil((topB + EDGE - y) / 4)
  else if (y < r.bottom && y > r.bottom - EDGE) el.scrollTop += Math.ceil((y - r.bottom + EDGE) / 4)
  if (dragStart?.armed) refreshBarPreview()
  else if (chipStart) refreshChipHint()
  edgeRAF = requestAnimationFrame(edgeStep)
}
const startEdge = () => { if (!edgeRAF) edgeRAF = requestAnimationFrame(edgeStep) }
const stopEdge = () => { if (edgeRAF) cancelAnimationFrame(edgeRAF); edgeRAF = null }

// ── Drag de una barra asignada ─────────────────────────────────────────
// La barra se "levanta" al mantenerla presionada un instante. Si en cambio se
// mueve el dedo enseguida, el gesto se toma como navegación (pan).
const ARM_MS = 160
const drag = reactive({ id: null, mode: null, rid: null, startMin: null, durMin: 60 })
const barDrag = reactive({ bar: null, x: 0, y: 0 })
let dragStart = null
let armTimer = null
const resetDrag = () => {
  Object.assign(drag, { id: null, mode: null, rid: null, startMin: null, durMin: 60 })
  barDrag.bar = null
}
const endBarGesture = () => {
  window.removeEventListener('pointermove', onBarMove)
  window.removeEventListener('pointerup', onBarUp)
  clearTimeout(armTimer)
  stopEdge()
  hideHint()
}
const onBarDown = (e, bar) => {
  if (e.button !== 0 || e.target.closest('button')) return
  dragStart = { px: e.clientX, py: e.clientY, bar, armed: false, moved: false }
  resetDrag()
  lastPointer = { x: e.clientX, y: e.clientY }
  window.addEventListener('pointermove', onBarMove)
  window.addEventListener('pointerup', onBarUp)
  armTimer = setTimeout(() => {
    if (dragStart) {
      dragStart.armed = true
      drag.id = bar.id
      drag.durMin = bar.dur
      Object.assign(barDrag, { bar, x: lastPointer.x, y: lastPointer.y })
      startEdge()
    }
  }, ARM_MS)
}
const refreshBarPreview = () => {
  if (!dragStart?.armed) return
  const { x, y } = lastPointer
  const bar = dragStart.bar
  if (document.elementFromPoint(x, y)?.closest('.pz-unassigned, .pz-rail-head')) {
    drag.mode = 'unassign'
    setHint(x, y, 'Soltar aquí → dejar sin asignar')
    return
  }
  const t = targetFromPoint(x, y, bar.dur)
  if (!t) { drag.mode = null; hideHint(); return }
  drag.mode = 'move'
  drag.rid = t.rid
  drag.startMin = t.startMin
  setHint(x, y, hourBlockLabel(t.rawMin))
}
const onBarMove = e => {
  if (!dragStart) return
  if (!dragStart.armed) {
    if (Math.abs(e.clientX - dragStart.px) > 6 || Math.abs(e.clientY - dragStart.py) > 6) {
      const { px, py } = dragStart
      endBarGesture()
      dragStart = null
      resetDrag()
      beginPan(px, py)
      onBoardPan(e)
    }
    return
  }
  dragStart.moved = true
  lastPointer = { x: e.clientX, y: e.clientY }
  barDrag.x = e.clientX
  barDrag.y = e.clientY
  refreshBarPreview()
}
const onBarUp = async () => {
  endBarGesture()
  const ds = dragStart
  dragStart = null
  if (!ds) { resetDrag(); return }
  if (!ds.armed || !ds.moved) {
    resetDrag()
    // clic en una barra superpuesta que no está al frente → traerla al frente
    if ((ds.bar._stackCount || 1) > 1 && frontId.value !== ds.bar.id) { frontId.value = ds.bar.id; return }
    openPanel(ds.bar)
    return
  }
  if (drag.mode === 'unassign') { resetDrag(); await releaseBar(ds.bar); return }
  if (drag.mode !== 'move' || drag.rid == null || drag.startMin == null) { resetDrag(); return }
  // Deja la barra previsualizada en su destino y pide la hora exacta.
  openTimePicker({ kind: 'move', bar: ds.bar, rid: drag.rid }, lastPointer.x, lastPointer.y, drag.startMin)
}
const commitMove = async (bar, rid, mins) => {
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
// La barra que se está arrastrando se queda en su sitio, translúcida (referencia
// de "de dónde salió"). El destino se marca con un recuadro fantasma aparte.
const barLiveStyle = bar => (drag.id === bar.id
  ? { opacity: 0.22, pointerEvents: 'none', transition: 'none' }
  : {})

// ── Drag de un servicio sin asignar → soltar sobre la fila de un vehículo ─
const chipDrag = reactive({ item: null, x: 0, y: 0 })
let chipStart = null
const CHIP_MOVE_X = 60 // si el movimiento horizontal es menor, se usa la hora programada
const onChipDown = (e, s) => {
  if (e.button !== 0 || s.published) return
  e.preventDefault()
  chipStart = { px: e.clientX, py: e.clientY, s }
  Object.assign(chipDrag, { item: s, x: e.clientX, y: e.clientY })
  lastPointer = { x: e.clientX, y: e.clientY }
  window.addEventListener('pointermove', onChipMove)
  window.addEventListener('pointerup', onChipUp)
  startEdge()
}
const chipTargetMin = (x, y) => {
  const sched = toMin(chipStart.s.start)
  if (Math.abs(x - chipStart.px) < CHIP_MOVE_X && sched != null) return sched
  return targetFromPoint(x, y, 60)?.startMin ?? sched ?? 0
}
const refreshChipHint = () => {
  if (!chipStart) return
  const { x, y } = lastPointer
  if (!document.elementFromPoint(x, y)?.closest('.pz-lane')) { hideHint(); return }
  const mins = chipTargetMin(x, y)
  const sched = toMin(chipStart.s.start)
  const isSched = Math.abs(x - chipStart.px) < CHIP_MOVE_X && sched != null
  setHint(x, y, `${toHHMM(mins)}–${toHHMM(mins + 60)}${isSched ? ' · programado' : ''}`)
}
const onChipMove = e => {
  if (!chipStart) return
  chipDrag.x = e.clientX
  chipDrag.y = e.clientY
  lastPointer = { x: e.clientX, y: e.clientY }
  refreshChipHint()
}
const onChipUp = e => {
  window.removeEventListener('pointermove', onChipMove)
  window.removeEventListener('pointerup', onChipUp)
  stopEdge()
  hideHint()
  const st = chipStart
  chipStart = null
  chipDrag.item = null
  if (!st) return
  if (Math.abs(e.clientX - st.px) + Math.abs(e.clientY - st.py) < 6) { openAssignPanel(st.s); return }

  const t = targetFromPoint(e.clientX, e.clientY, 60)
  if (!t) { notify('Soltá el servicio sobre la fila de un vehículo.', 'warning'); return }
  const s = st.s
  const sched = toMin(s.start)
  // Sin confirmación: se asigna directo en la hora indicada (programada o la del punto).
  const mins = (Math.abs(e.clientX - st.px) < CHIP_MOVE_X && sched != null) ? sched : t.startMin
  commitAssign(s, t.rid, mins)
}
const commitAssign = async (s, rid, mins) => {
  const startHHMM = toHHMM(mins)
  const tempId = -Date.now()
  board.value.assignments.push({
    id: tempId, resourceId: rid, serviceId: s.serviceId, leadId: s.leadId,
    serviceCode: s.serviceCode, customer: s.customer,
    originDistrict: s.originDistrict, destDistrict: s.destDistrict, route: s.route,
    start: startHHMM, end: toHHMM(mins + 60), state: 'programado',
    price: s.price, mode: rid.startsWith('t') ? 'tercerizado' : s.mode,
    assignedAuto: false, driverName: null, helpers: [],
  })
  board.value.unassigned = board.value.unassigned.filter(x => x.serviceId !== s.serviceId)
  try {
    await pizarraAssign({ serviceId: s.serviceId, resourceId: rid, start: startHHMM })
    notify(`${s.serviceCode} asignado a las ${startHHMM}.`)
    await load(true)
  } catch (err) {
    board.value.assignments = board.value.assignments.filter(a => a.id !== tempId)
    board.value.unassigned = [...board.value.unassigned, s]
    notify(err.message || 'No se pudo asignar.', 'error')
  }
}

// ── Selector de hora exacta al soltar (radios :00 :15 :30 :45) ─────────
const picker = reactive({ show: false, x: 0, y: 0, code: '', options: [], selected: null, ctx: null })
const openTimePicker = (ctx, x, y, dropMin) => {
  const hs = Math.floor(dropMin / 60) * 60
  picker.options = [hs, hs + 15, hs + 30, hs + 45].map(v => ({ value: v, label: toHHMM(v) }))
  picker.selected = null // el usuario elige la hora explícitamente
  picker.code = ctx.kind === 'assign' ? ctx.service.serviceCode : ctx.bar.serviceCode
  picker.ctx = ctx
  picker.x = Math.min(x, window.innerWidth - 230)
  picker.y = Math.min(y, window.innerHeight - 230)
  picker.show = true
}
watch(() => picker.selected, v => {
  if (picker.ctx?.kind === 'move' && v != null) drag.startMin = v
})
watch(() => picker.show, v => { if (!v) { picker.ctx = null; resetDrag() } })
const confirmPicker = async () => {
  const c = picker.ctx
  const mins = picker.selected
  picker.show = false
  if (!c || mins == null) return
  if (c.kind === 'move') await commitMove(c.bar, c.rid, mins)
  else await commitAssign(c.service, c.rid, mins)
}

// ── Conductor del vehículo (clic en la placa) ─────────────────────────
const driverDialog = ref(null) // recurso o null
const externalDriverInput = ref('') // para filas de transportista
const setResourceDriver = async (r, driverId) => {
  const asgs = board.value.assignments.filter(a => a.resourceId === r.id)
  if (!asgs.length) {
    notify('Este vehículo no tiene servicios este día. Asigná el conductor al asignar un servicio.', 'warning')
    driverDialog.value = null
    return
  }
  try {
    await Promise.all(asgs.map(a => pizarraEdit({ assignmentId: a.id, driverId: driverId ?? null })))
    notify(driverId ? 'Conductor asignado a los servicios del vehículo.' : 'Conductor quitado.')
    driverDialog.value = null
    await load(true)
  } catch (e) { notify(e.message || 'No se pudo cambiar el conductor.', 'error') }
}
const setCarrierDriver = async r => {
  const nombre = (externalDriverInput.value || '').trim()
  try {
    await pizarraAddCarrierRow({ date: date.value, carrierVehicleId: r.carrierVehicleId, driverName: nombre })
    const asgs = board.value.assignments.filter(a => a.resourceId === r.id)
    await Promise.all(asgs.map(a => pizarraEdit({ assignmentId: a.id, externalDriverName: nombre })))
    notify('Conductor actualizado.')
    driverDialog.value = null
    await load(true)
  } catch (e) { notify(e.message || 'No se pudo actualizar el conductor.', 'error') }
}
watch(driverDialog, r => { externalDriverInput.value = r?.driverName || '' })

// ── Panel lateral: editar una barra o asignar un servicio ──────────────
const panel = ref(false)
const panelKind = ref('assigned')
const sel = ref(null)
const form = reactive({ resourceId: null, driverId: null, start: '', end: '', state: '' })
const driverOptions = computed(() => drivers.value.map(d => ({ title: d.name, value: d.id })))
const resourceOptions = computed(() =>
  resources.value.map(r => ({
    title: `${r.kind === 'tercerizado' ? '🚚 ' : ''}${r.label}${r.driverName ? ` · ${r.driverName}` : ''}`,
    value: r.id,
  })))
const openPanel = bar => {
  panelKind.value = 'assigned'
  sel.value = bar
  Object.assign(form, {
    resourceId: bar.resourceId, driverId: null,
    start: toHHMM(bar.start), end: bar.end ? toHHMM(bar.end) : '', state: bar.state,
  })
  panel.value = true
}
const openAssignPanel = s => {
  panelKind.value = 'unassigned'
  sel.value = s
  const raw = s.start || s.scheduleText || ''
  const st = /^\d{1,2}:\d{2}$/.test(raw) ? raw.padStart(5, '0') : '08:00'
  Object.assign(form, {
    resourceId: null, driverId: null, start: st, end: addHour(st), state: 'programado',
  })
  panel.value = true
}
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
    await load(true)
  } catch (e) { notify(e.message || 'No se pudo guardar.', 'error') }
}
const doAssignPanel = async () => {
  if (!form.resourceId) { notify('Elegí un vehículo.', 'warning'); return }
  const s = sel.value
  panel.value = false
  const tempId = -Date.now()
  board.value.assignments.push({
    id: tempId, resourceId: form.resourceId, serviceId: s.serviceId, leadId: s.leadId,
    serviceCode: s.serviceCode, customer: s.customer,
    originDistrict: s.originDistrict, destDistrict: s.destDistrict, route: s.route,
    start: form.start, end: form.end || addHour(form.start), state: 'programado',
    price: s.price, mode: s.mode, assignedAuto: false, driverName: driverNameOf(form.driverId), helpers: [],
  })
  board.value.unassigned = board.value.unassigned.filter(x => x.serviceId !== s.serviceId)
  try {
    await pizarraAssign({
      serviceId: s.serviceId, resourceId: form.resourceId, start: form.start,
      end: form.end || undefined, driverId: form.driverId || undefined,
    })
    notify(`${s.serviceCode} asignado.`)
    await load(true)
  } catch (e) {
    board.value.assignments = board.value.assignments.filter(a => a.id !== tempId)
    board.value.unassigned = [...board.value.unassigned, s]
    notify(e.message || 'No se pudo asignar.', 'error')
  }
}
// Devuelve el servicio a "Sin asignar" quedando en su hora y con su color.
const releaseBar = async bar => {
  const orig = board.value.assignments.find(a => a.id === bar.id)
  const snap = orig ? { ...orig } : null
  board.value.assignments = board.value.assignments.filter(a => a.id !== bar.id)
  board.value.unassigned = [...board.value.unassigned, {
    serviceId: bar.serviceId, leadId: bar.leadId, serviceCode: bar.serviceCode,
    customer: bar.customer, originDistrict: bar.originDistrict, destDistrict: bar.destDistrict,
    route: bar.route, mode: bar.mode, price: bar.price, published: false, scheduleText: '',
    start: typeof bar.start === 'number' ? toHHMM(bar.start) : bar.start,
  }]
  panel.value = false
  ctx.show = false
  try {
    await pizarraUnassign(bar.id)
    notify(`${bar.serviceCode} vuelve a "Sin asignar".`)
    await load(true)
  } catch (e) {
    board.value.unassigned = board.value.unassigned.filter(x => x.serviceId !== bar.serviceId)
    if (snap) board.value.assignments = [...board.value.assignments, snap]
    notify(e.message || 'No se pudo quitar.', 'error')
  }
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


// ── Ocultar / agregar vehículos ────────────────────────────────────────
const hideResource = rid => { hidden.value.add(rid); hidden.value = new Set(hidden.value); persistHidden() }
const showResource = rid => { hidden.value.delete(rid); hidden.value = new Set(hidden.value); persistHidden() }
const addDialog = ref(false)
const hiddenResources = computed(() =>
  board.value.resources.filter(r =>
    r.kind !== 'tercerizado' && hidden.value.has(r.id) && !hasAssignment(r.id)))

// Quitar de la pizarra: propios → localStorage; transportistas → server.
const removeResource = async r => {
  if (r.kind === 'tercerizado') {
    try {
      await pizarraRemoveCarrierRow({ date: date.value, resourceId: r.id })
      await load(true)
    } catch (e) { notify(e.message || 'No se pudo quitar la fila.', 'error') }
  } else {
    hideResource(r.id)
  }
}

// ── Agregar transportista a la pizarra ─────────────────────────────────
const addTab = ref('propio')
const carrierOpts = ref([])
const carrierVehOpts = ref([])
const carrierDriverOpts = ref([])
const carrierForm = reactive({ carrierId: null, carrierVehicleId: null, driverName: '' })
const addBusy = ref(false)

watch(addDialog, open => {
  if (!open) return
  addTab.value = 'propio'
  Object.assign(carrierForm, { carrierId: null, carrierVehicleId: null, driverName: '' })
})
watch(addTab, async tab => {
  if (tab === 'tercerizado' && !carrierOpts.value.length) {
    try {
      const d = await carriersService.list({ status: 'active', pageSize: 200 })
      carrierOpts.value = d.results.map(c => ({ title: c.name, value: c.id }))
    } catch { carrierOpts.value = [] }
  }
})
watch(() => carrierForm.carrierId, async id => {
  carrierForm.carrierVehicleId = null
  carrierForm.driverName = ''
  carrierVehOpts.value = []
  carrierDriverOpts.value = []
  if (!id) return
  try {
    const [veh, drv] = await Promise.all([
      carrierVehiclesService.list({ carrierId: id, status: 'active', pageSize: 200 }),
      carrierDriversService.list({ carrierId: id, status: 'active', pageSize: 200 }).catch(() => ({ results: [] })),
    ])
    carrierVehOpts.value = veh.results.map(v => ({
      title: [v.plate, [v.brand, v.model].filter(Boolean).join(' ')].filter(Boolean).join(' · '),
      value: v.id,
    }))
    carrierDriverOpts.value = drv.results.map(x => x.name)
    if (carrierVehOpts.value.length === 1) carrierForm.carrierVehicleId = carrierVehOpts.value[0].value
  } catch { /* */ }
})
const submitCarrierRow = async () => {
  if (!carrierForm.carrierVehicleId) { notify('Elegí un vehículo del transportista.', 'warning'); return }
  addBusy.value = true
  try {
    await pizarraAddCarrierRow({
      date: date.value,
      carrierVehicleId: carrierForm.carrierVehicleId,
      driverName: carrierForm.driverName || undefined,
    })
    addDialog.value = false
    await load(true)
  } catch (e) { notify(e.message || 'No se pudo agregar el transportista.', 'error') } finally { addBusy.value = false }
}

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
      published: s.published,
      label: `${s.serviceCode} · ${routeOf(s)} · ${s.start || s.scheduleText || 's/h'}`,
    })
  }
  return out.sort((x, y) => x.min - y.min)
})

const rowsAbove = computed(() => Math.max(0, Math.floor((view.y + 2) / ROW_H)))
const rowsBelow = computed(() =>
  Math.max(0, resources.value.length - Math.ceil((view.y + view.h) / ROW_H)))

const scrollToMin = m => {
  const el = scroller.value
  if (!el) return
  el.scrollTo({ left: Math.max(0, m * PX_PER_MIN - view.w / 2), behavior: 'smooth' })
}
const scrollTop = () => scroller.value?.scrollTo({ top: 0, behavior: 'smooth' })
const scrollBottom = () => scroller.value?.scrollTo({ top: 999999, behavior: 'smooth' })

// Navegación por servicio: salta al más cercano fuera de la vista.
const nextStopMin = (mins, dir) => (dir > 0
  ? mins.find(m => m * PX_PER_MIN > view.x + view.w + 4)
  : [...mins].reverse().find(m => m * PX_PER_MIN < view.x - 4))
const unassignedMins = computed(() =>
  board.value.unassigned.map(s => toMin(s.start) ?? 0).sort((a, b) => a - b))
const unPrev = computed(() => nextStopMin(unassignedMins.value, -1) != null)
const unNext = computed(() => nextStopMin(unassignedMins.value, 1) != null)
const goUn = dir => { const m = nextStopMin(unassignedMins.value, dir); if (m != null) scrollToMin(m) }
const barMins = rid => (barsByResource.value[rid] || []).map(b => b.start).sort((a, b) => a - b)
const barNav = (rid, dir) => nextStopMin(barMins(rid), dir) != null
const goBar = (rid, dir) => { const m = nextStopMin(barMins(rid), dir); if (m != null) scrollToMin(m) }

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
      <h1 class="text-h4 font-weight-bold">Pizarra</h1>
      <div class="d-flex flex-wrap align-center justify-end ga-y-2">
        <div v-if="!loading && !error" class="text-end me-10">
          <div class="text-caption text-medium-emphasis">{{ dayLabel }}</div>
          <div>
            <span class="text-h6 font-weight-bold">{{ summary.total }}</span>
            <span class="text-body-2 text-medium-emphasis"> servicios</span>
            <span class="text-h6 font-weight-bold ms-4">{{ soles(summary.monto) }}</span>
          </div>
        </div>
        <div class="d-flex align-center ga-1">
          <VBtn icon="ri-arrow-left-s-line" variant="tonal" @click="shiftDay(-1)" />
          <AppDateField v-model="date" hide-details style="flex: 0 0 180px; width: 180px;" @update:model-value="reload" />
          <VBtn icon="ri-arrow-right-s-line" variant="tonal" @click="shiftDay(1)" />
          <VBtn variant="text" @click="today">Hoy</VBtn>
        </div>
      </div>
    </div>

    <VAlert v-if="error" type="error" variant="tonal" class="mb-4">
      {{ error }}
      <template #append><VBtn size="small" variant="text" @click="reload">Reintentar</VBtn></template>
    </VAlert>

    <VCard>
      <div v-if="!loading && resources.length" class="pz-minimap-wrap px-4 pt-3 pb-1">
        <div ref="minimap" class="pz-minimap" @click="onMinimapClick">
          <div v-for="h in [3, 6, 9, 12, 15, 18, 21]" :key="h" class="pz-mm-tick" :style="{ left: (h / 24 * 100) + '%' }" />
          <div
            v-for="s in allStops" :key="s.key"
            class="pz-mm-mark" :class="{ 'pz-mm-mark--un': s.kind === 'unassigned' }"
            :style="{
              left: (s.min / 1440 * 100) + '%',
              background: s.kind === 'unassigned'
                ? (s.published ? UNASSIGNED.publicada.color : UNASSIGNED.por_asignar.color)
                : (MODE[s.mode]?.color || '#64748b'),
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
              <div class="d-flex align-center justify-space-between ga-1" style="inline-size: 100%;">
                <div class="d-flex align-center ga-1">
                  <span class="text-caption text-medium-emphasis">Sin asignar</span>
                  <VChip size="x-small" color="warning" variant="flat">{{ board.unassigned.length }}</VChip>
                </div>
                <div class="d-flex flex-shrink-0">
                  <VBtn icon="ri-arrow-left-s-line" size="x-small" variant="text" :disabled="!unPrev" title="Servicio sin asignar anterior" @click="goUn(-1)" />
                  <VBtn icon="ri-arrow-right-s-line" size="x-small" variant="text" :disabled="!unNext" title="Siguiente servicio sin asignar" @click="goUn(1)" />
                </div>
              </div>
            </div>
            <div
              v-for="r in resources" :key="r.id" class="pz-rail-row"
              :class="{ 'pz-rail-row--carrier': r.kind === 'tercerizado' }"
              :style="{ height: ROW_H + 'px' }"
              @contextmenu.prevent="openCtx($event, 'resource', r)"
            >
              <div class="d-flex align-center justify-space-between ga-1">
                <div class="d-flex align-center ga-1" style="min-inline-size: 0;">
                  <VIcon v-if="r.kind === 'tercerizado'" icon="ri-truck-line" size="13" class="flex-shrink-0 text-warning" />
                  <button
                    type="button" class="pz-plate text-truncate"
                    title="Asignar o quitar conductor" @click="driverDialog = r"
                  >
                    {{ r.label }}
                  </button>
                  <VChip size="x-small" variant="tonal" class="flex-shrink-0">{{ (barsByResource[r.id] || []).length }}</VChip>
                </div>
                <div class="d-flex flex-shrink-0">
                  <VBtn
                    icon="ri-arrow-left-s-line" size="x-small" variant="text"
                    :disabled="!barNav(r.id, -1)" title="Servicio anterior de este vehículo"
                    @click="goBar(r.id, -1)"
                  />
                  <VBtn
                    icon="ri-arrow-right-s-line" size="x-small" variant="text"
                    :disabled="!barNav(r.id, 1)" title="Siguiente servicio de este vehículo"
                    @click="goBar(r.id, 1)"
                  />
                </div>
              </div>
              <button
                type="button" class="pz-driver text-caption text-truncate"
                :class="r.driverName ? 'text-medium-emphasis' : 'text-primary'"
                title="Asignar o quitar conductor" @click="driverDialog = r"
              >
                {{ r.driverName || '+ asignar conductor' }}<span v-if="r.sublabel" class="text-medium-emphasis"> · {{ r.sublabel }}</span>
              </button>
            </div>
            <div class="pz-rail-foot" :style="{ height: FOOT_H + 'px' }">
              <VBtn size="small" variant="text" prepend-icon="ri-add-line" @click="addDialog = true">
                Agregar vehículo
              </VBtn>
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
                  class="pz-chip"
                  :class="{
                    'pz-chip--pub': s.published,
                    'pz-chip--todo': !s.published,
                    'pz-chip--src': chipDrag.item && chipDrag.item.serviceId === s.serviceId,
                  }"
                  :style="{
                    left: s._left + 'px',
                    top: (s._row * (CHIP_H + 6) + 4) + 'px',
                    width: CHIP_W + 'px',
                    borderInlineStartColor: s.published ? UNASSIGNED.publicada.color : UNASSIGNED.por_asignar.color,
                  }"
                  @pointerdown="onChipDown($event, s)"
                  @contextmenu.prevent="openCtx($event, 'unassigned', s)"
                >
                  <div class="pz-l1">
                    <span class="text-truncate">{{ s.serviceCode }}</span>
                    <span v-if="s.published" class="text-caption">· pub.</span>
                    <span class="pz-amt">{{ soles(s.price) }}</span>
                  </div>
                  <div class="pz-l2 text-truncate">{{ routeOf(s) }}</div>
                  <div class="pz-l3 text-truncate">
                    <strong>{{ s.start || s.scheduleText || 's/h' }}</strong>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="nowLeft != null" class="pz-now" :style="{ left: nowLeft + 'px' }" />

            <div
              v-for="r in resources" :key="r.id" class="pz-lane"
              :class="{ 'pz-lane--carrier': r.kind === 'tercerizado' }"
              :data-resource-id="r.id" :style="{ height: ROW_H + 'px' }"
            >
              <div v-for="h in HOURS" :key="h" class="pz-tick" :style="{ left: (h * 60 * PX_PER_MIN) + 'px' }" />
              <div
                v-for="bar in (barsByResource[r.id] || [])" :key="bar.id"
                class="pz-bar"
                :style="{
                  left: (bar.start * PX_PER_MIN) + 'px',
                  width: (bar.dur * PX_PER_MIN) + 'px',
                  top: (5 + (bar._stack || 0) * PEEK) + 'px',
                  height: (ROW_H - 10 - ((bar._stackCount || 1) - 1) * PEEK) + 'px',
                  bottom: 'auto',
                  zIndex: frontId === bar.id ? 60 : undefined,
                  borderLeftColor: (MODE[bar.mode]?.color || '#64748b'),
                  ...barLiveStyle(bar),
                }"
                @pointerdown="onBarDown($event, bar)"
                @contextmenu.prevent="openCtx($event, 'bar', bar)"
              >
                <div class="pz-l1">
                  <span class="pz-state-dot" :style="{ background: STATE[bar.state]?.color }" />
                  <span class="text-truncate">{{ bar.serviceCode }}</span>
                  <span v-if="bar.assignedAuto" title="Asignación automática">⚡</span>
                  <span class="pz-amt">{{ soles(bar.price) }}</span>
                </div>
                <div v-if="(bar._stackCount || 1) < 3" class="pz-l2 text-truncate">{{ routeOf(bar) }}</div>
                <div class="pz-l3 text-truncate">
                  <strong>{{ toHHMM(bar.start) }}</strong><span v-if="bar.end" class="pz-dim">–{{ toHHMM(bar.end) }}</span>
                </div>
              </div>
            </div>
            <div class="pz-lane-foot" :style="{ height: FOOT_H + 'px' }" />
          </div>
        </div>
        </div>
      </div>

      <VDivider />
      <VCardText class="d-flex flex-wrap ga-x-8 ga-y-2 text-caption">
        <div class="d-flex align-center flex-wrap ga-x-3 ga-y-1">
          <span class="text-medium-emphasis font-weight-medium">Sin asignar (tarjeta):</span>
          <span v-for="(u, k) in UNASSIGNED" :key="k" class="d-inline-flex align-center ga-1">
            <span class="pz-bar-swatch" :style="{ background: u.color }" /> {{ u.label }}
          </span>
        </div>
        <div class="d-flex align-center flex-wrap ga-x-3 ga-y-1">
          <span class="text-medium-emphasis font-weight-medium">Ejecuta (borde de la barra):</span>
          <span v-for="(m, k) in MODE" :key="k" class="d-inline-flex align-center ga-1">
            <span class="pz-bar-swatch" :style="{ background: m.color }" /> {{ m.label }}
          </span>
        </div>
        <div class="d-flex align-center flex-wrap ga-x-3 ga-y-1">
          <span class="text-medium-emphasis font-weight-medium">Estado (punto):</span>
          <span v-for="(s, k) in STATE" :key="k" class="d-inline-flex align-center ga-1">
            <span class="pz-state-dot" :style="{ background: s.color }" /> {{ s.label }}
          </span>
        </div>
        <span class="text-medium-emphasis">⚡ = asignación automática (bot)</span>
      </VCardText>
    </VCard>

    <!-- servicio sin asignar "fantasma" mientras se arrastra -->
    <div
      v-if="chipDrag.item" class="pz-chip pz-chip--ghost"
      :style="{ left: chipDrag.x + 'px', top: chipDrag.y + 'px', width: CHIP_W + 'px' }"
    >
      <div class="pz-l1">
        <span class="text-truncate">{{ chipDrag.item.serviceCode }}</span>
        <span class="pz-amt">{{ soles(chipDrag.item.price) }}</span>
      </div>
      <div class="pz-l2 text-truncate">{{ routeOf(chipDrag.item) }}</div>
      <div class="pz-l3 text-truncate">
        <strong>{{ chipDrag.item.start || chipDrag.item.scheduleText || 's/h' }}</strong>
      </div>
    </div>

    <!-- barra "fantasma" mientras se arrastra una barra asignada -->
    <div
      v-if="barDrag.bar" class="pz-chip pz-chip--ghost"
      :style="{
        left: barDrag.x + 'px', top: barDrag.y + 'px', width: '176px',
        borderInlineStartColor: (MODE[barDrag.bar.mode]?.color || '#64748b'),
      }"
    >
      <div class="pz-l1">
        <span class="text-truncate">{{ barDrag.bar.serviceCode }}</span>
        <span class="pz-amt">{{ soles(barDrag.bar.price) }}</span>
      </div>
      <div class="pz-l2 text-truncate">{{ routeOf(barDrag.bar) }}</div>
      <div class="pz-l3 text-truncate"><strong>{{ toHHMM(barDrag.bar.start) }}</strong></div>
    </div>

    <!-- menú contextual -->
    <VMenu v-model="ctx.show" :target="[ctx.x, ctx.y]" location="bottom start">
      <VList density="compact" min-width="200">
        <template v-if="ctx.kind === 'bar'">
          <VListItem prepend-icon="ri-file-list-3-line" title="Ver detalle del servicio" @click="openDetail(ctx.item.leadId)" />
          <VListItem prepend-icon="ri-edit-line" title="Editar rápido (hora, conductor…)" @click="openPanel(ctx.item)" />
          <VDivider />
          <VListItem prepend-icon="ri-close-circle-line" title="Quitar asignación" base-color="error" @click="releaseBar(ctx.item)" />
        </template>
        <template v-else-if="ctx.kind === 'unassigned'">
          <VListItem
            prepend-icon="ri-calendar-check-line" title="Asignar a un vehículo"
            :disabled="ctx.item.published" @click="openAssignPanel(ctx.item)"
          />
          <VListItem prepend-icon="ri-file-list-3-line" title="Ver detalle del servicio" @click="openDetail(ctx.item.leadId)" />
        </template>
        <template v-else-if="ctx.kind === 'resource'">
          <VListItem prepend-icon="ri-eye-off-line" title="Quitar de la pizarra" @click="removeResource(ctx.item)" />
        </template>
      </VList>
    </VMenu>

    <!-- selector de hora exacta al soltar -->
    <template v-if="picker.show">
      <div class="pz-picker-backdrop" @pointerdown="picker.show = false" />
      <VCard
        class="pz-picker pa-2" min-width="200"
        :style="{ left: picker.x + 'px', top: picker.y + 'px' }"
      >
        <div class="text-caption text-medium-emphasis px-1 pb-1">
          {{ picker.code }} · {{ dayLabel }}<br>Elegí la hora de inicio
        </div>
        <VRadioGroup v-model="picker.selected" density="compact" hide-details class="px-1">
          <VRadio v-for="o in picker.options" :key="o.value" :value="o.value" :label="o.label" />
        </VRadioGroup>
        <div class="d-flex justify-end ga-1 mt-1">
          <VBtn size="small" variant="text" @click="picker.show = false">Cancelar</VBtn>
          <VBtn size="small" color="primary" :disabled="picker.selected == null" @click="confirmPicker">Confirmar</VBtn>
        </div>
      </VCard>
    </template>

    <!-- panel lateral: editar una barra o asignar un servicio -->
    <VNavigationDrawer v-model="panel" location="right" temporary width="360">
      <div v-if="sel" class="pa-4">
        <div class="d-flex align-center justify-space-between mb-3">
          <h3 class="text-h6">{{ sel.serviceCode }}</h3>
          <VBtn icon="ri-close-line" variant="text" size="small" @click="panel = false" />
        </div>
        <p class="text-body-2 mb-1">{{ sel.customer }}</p>
        <p class="text-caption text-medium-emphasis mb-1">{{ routeOf(sel) }}</p>
        <VChip
          size="x-small" label class="mb-3"
          :style="{ borderInlineStart: `3px solid ${MODE[sel.mode]?.color || '#64748b'}` }"
        >
          {{ MODE[sel.mode]?.label || 'Ejecución sin definir' }}
        </VChip>
        <VBtn variant="tonal" size="small" prepend-icon="ri-file-list-3-line" class="mb-4 d-block" @click="openDetail(sel.leadId)">
          Ver detalle completo
        </VBtn>

        <VSelect
          v-if="panelKind === 'unassigned'"
          v-model="form.resourceId" :items="resourceOptions" label="Vehículo"
          placeholder="Elegí un vehículo" class="mb-3"
        />
        <VSelect v-model="form.driverId" :items="driverOptions" label="Conductor" clearable class="mb-3" />
        <div class="d-flex ga-2 mb-3">
          <VTextField v-model="form.start" type="time" label="Inicio" density="compact" hide-details />
          <VTextField v-model="form.end" type="time" label="Fin" density="compact" hide-details />
        </div>
        <VSelect
          v-if="panelKind === 'assigned'"
          v-model="form.state" label="Estado" class="mb-4"
          :items="Object.entries(STATE).map(([value, s]) => ({ title: s.label, value }))"
        />

        <template v-if="panelKind === 'assigned'">
          <VBtn block color="primary" class="mb-2" @click="saveEdit">Guardar</VBtn>
          <VBtn block variant="text" color="error" @click="releaseBar(sel)">Quitar asignación</VBtn>
        </template>
        <VBtn
          v-else block color="primary" class="mt-2"
          :disabled="!form.resourceId" @click="doAssignPanel"
        >
          Asignar
        </VBtn>
      </div>
    </VNavigationDrawer>

    <!-- etiqueta flotante con el día + hora de destino mientras se arrastra -->
    <div v-if="dragHint.show" class="pz-hint" :style="{ left: dragHint.x + 'px', top: dragHint.y + 'px' }">
      {{ dragHint.text }}
    </div>

    <!-- agregar vehículo a la pizarra -->
    <VDialog v-model="addDialog" max-width="460">
      <VCard>
        <VCardTitle>Agregar a la pizarra</VCardTitle>
        <VCardText class="pt-2">
          <VBtnToggle v-model="addTab" mandatory density="comfortable" class="mb-4" color="primary">
            <VBtn value="propio" prepend-icon="ri-team-line">Nuestro equipo</VBtn>
            <VBtn value="tercerizado" prepend-icon="ri-truck-line">Transportistas</VBtn>
          </VBtnToggle>

          <template v-if="addTab === 'propio'">
            <VList density="compact">
              <VListItem v-for="r in hiddenResources" :key="r.id" :title="r.label" :subtitle="r.sublabel">
                <template #append>
                  <VBtn size="small" variant="tonal" @click="showResource(r.id)">Agregar</VBtn>
                </template>
              </VListItem>
              <VListItem v-if="!hiddenResources.length" title="No hay vehículos ocultos." class="text-medium-emphasis" />
            </VList>
          </template>

          <template v-else>
            <VAutocomplete
              v-model="carrierForm.carrierId" :items="carrierOpts"
              label="Transportista" prepend-inner-icon="ri-building-line" class="mb-3"
              no-data-text="Sin transportistas afiliados"
            />
            <VSelect
              v-model="carrierForm.carrierVehicleId" :items="carrierVehOpts"
              label="Vehículo" prepend-inner-icon="ri-car-line" class="mb-3"
              :disabled="!carrierForm.carrierId"
              no-data-text="Este transportista no tiene vehículos"
            />
            <VCombobox
              v-model="carrierForm.driverName" :items="carrierDriverOpts"
              label="Conductor (opcional)" prepend-inner-icon="ri-user-line"
              :disabled="!carrierForm.carrierId"
            />
          </template>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="addDialog = false">Cerrar</VBtn>
          <VBtn
            v-if="addTab === 'tercerizado'" color="primary" :loading="addBusy"
            :disabled="!carrierForm.carrierVehicleId" @click="submitCarrierRow"
          >
            Agregar
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- conductor del vehículo -->
    <VDialog :model-value="!!driverDialog" max-width="380" @update:model-value="driverDialog = null">
      <VCard v-if="driverDialog">
        <VCardTitle class="text-body-1">Conductor · {{ driverDialog.label }}</VCardTitle>
        <VCardText>
          <div class="text-caption text-medium-emphasis mb-3">
            <template v-if="(barsByResource[driverDialog.id] || []).length">
              Se aplica a los {{ (barsByResource[driverDialog.id] || []).length }} servicio(s) de este vehículo en la fecha.
            </template>
            <template v-else>Este vehículo no tiene servicios este día.</template>
          </div>

          <VCombobox
            v-if="driverDialog.kind === 'tercerizado'"
            v-model="externalDriverInput" :items="[]"
            label="Conductor del transportista" prepend-inner-icon="ri-user-line" hide-details clearable
          />
          <VAutocomplete
            v-else
            :items="driverOptions" :model-value="driverDialog.driverId"
            label="Conductor" prepend-inner-icon="ri-user-line" hide-details
            :disabled="!(barsByResource[driverDialog.id] || []).length"
            @update:model-value="v => setResourceDriver(driverDialog, v)"
          />
        </VCardText>
        <VCardActions>
          <VBtn
            v-if="driverDialog.kind !== 'tercerizado' && driverDialog.driverId" variant="text" color="error"
            @click="setResourceDriver(driverDialog, null)"
          >
            Quitar conductor
          </VBtn>
          <VSpacer />
          <VBtn v-if="driverDialog.kind === 'tercerizado'" color="primary" variant="text" @click="setCarrierDriver(driverDialog)">
            Guardar
          </VBtn>
          <VBtn variant="text" @click="driverDialog = null">Cerrar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <ServiceViewDialog
      v-if="detailLeadId"
      :lead-id="detailLeadId"
      context="bookings"
      @close="detailLeadId = null"
      @changed="() => load(true)"
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
.pz-rail-row--carrier {
  border-inline-start: 3px solid #d97706;
  background: rgb(217 119 6 / 5%);
}
.pz-rail-foot {
  display: flex;
  align-items: center;
  padding-inline: 6px;
  background: rgb(var(--v-theme-surface));
}
.pz-plate {
  font-weight: 600;
  cursor: pointer;
  border-radius: 4px;
  padding: 0 2px;
}
.pz-plate:hover { background: rgba(var(--v-theme-primary), 0.1); }
.pz-driver {
  cursor: pointer;
  text-align: start;
  border-radius: 4px;
  padding: 0 2px;
  max-inline-size: 100%;
}
.pz-driver:hover { text-decoration: underline; }
.pz-lane-foot {
  border-block-start: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
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
.pz-lane--carrier { background: rgb(217 119 6 / 4%); }
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
.pz-chip--todo { background: rgb(220 38 38 / 6%); }
.pz-chip--pub { opacity: 0.7; cursor: not-allowed; background: rgb(217 119 6 / 8%); }
.pz-chip--src { opacity: 0.3; }
.pz-chip--ghost {
  position: fixed;
  z-index: 3000;
  pointer-events: none;
  opacity: 0.95;
  transform: translate(-50%, -50%);
  box-shadow: 0 6px 20px rgb(0 0 0 / 25%);
}

.pz-hint {
  position: fixed;
  z-index: 3200;
  pointer-events: none;
  transform: translate(-50%, calc(-100% - 18px));
  padding: 6px 16px;
  font-size: 17px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  white-space: nowrap;
  color: #fff;
  background: rgb(17 24 39 / 94%);
  border-radius: 8px;
  box-shadow: 0 6px 18px rgb(0 0 0 / 34%);
}

.pz-picker-backdrop { position: fixed; inset: 0; z-index: 2500; }
.pz-picker {
  position: fixed;
  z-index: 2600;
  box-shadow: 0 8px 30px rgb(0 0 0 / 28%);
}

.pz-l1 {
  font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 5px;
  min-inline-size: 0;
}
.pz-l1 .text-truncate { min-inline-size: 0; }
.pz-amt {
  margin-inline-start: auto;
  padding-inline-start: 6px;
  font-weight: 700;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
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
