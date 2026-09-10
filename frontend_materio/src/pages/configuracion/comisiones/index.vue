<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import {
  commissionTierCreate, commissionTierDelete, commissionTierUpdate, commissionTiers,
} from '@/services/publicationService'

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snackbar, { show: true, text: t, color: c })

const tiers = ref([])
const categories = ref([])
const loading = ref(true)
const busy = ref(false)

const load = async () => {
  loading.value = true
  try {
    const r = await commissionTiers()
    tiers.value = r.tiers
    categories.value = r.categories
  } catch (e) { notify(e.message || 'No se pudo cargar.', 'error') } finally { loading.value = false }
}
onMounted(load)

const catLabel = value => (value === '' ? 'Tabla general' : (categories.value.find(c => c.value === value)?.label || value))
const soles = n => (n == null ? 'sin tope' : `S/ ${Math.round(n).toLocaleString('es-PE')}`)

// Agrupado: general primero, luego cada categoría con tramos.
const groups = computed(() => {
  const by = {}
  for (const t of tiers.value) (by[t.category] ??= []).push(t)
  for (const k in by) by[k].sort((a, b) => a.from - b.from)
  const keys = Object.keys(by).sort((a, b) => (a === '' ? -1 : b === '' ? 1 : a.localeCompare(b)))
  return keys.map(k => ({ category: k, rows: by[k] }))
})

// --- alta / edición ---
const form = reactive({ open: false, id: null, category: '', from: 0, to: null, percent: 15, active: true })
const openNew = cat => Object.assign(form, { open: true, id: null, category: cat ?? '', from: 0, to: null, percent: 15, active: true })
const openEdit = t => Object.assign(form, { open: true, id: t.id, category: t.category, from: t.from, to: t.to, percent: t.percent, active: t.active })
const save = async () => {
  busy.value = true
  const body = {
    category: form.category, from: form.from,
    to: form.to === '' || form.to == null ? null : form.to,
    percent: form.percent, active: form.active,
  }
  try {
    if (form.id) await commissionTierUpdate(form.id, body)
    else await commissionTierCreate(body)
    form.open = false
    notify('Tramo guardado.')
    await load()
  } catch (e) { notify(e.message || 'Revisá los datos.', 'error') } finally { busy.value = false }
}
const remove = async t => {
  if (!confirm(`Eliminar el tramo ${catLabel(t.category)} ${soles(t.from)}–${soles(t.to)}?`)) return
  busy.value = true
  try { await commissionTierDelete(t.id); notify('Tramo eliminado.'); await load() }
  catch (e) { notify(e.message || 'No se pudo eliminar.', 'error') } finally { busy.value = false }
}

// --- simulador ---
const sim = reactive({ amount: 2000, category: '' })
const simResult = computed(() => {
  const amount = Number(sim.amount)
  if (!amount) return null
  const pool = tiers.value.filter(t => t.active && (t.category === sim.category || (t.category === '' && !tiers.value.some(x => x.active && x.category === sim.category))))
  const list = pool.length ? pool : tiers.value.filter(t => t.active && t.category === '')
  const hit = list.find(t => amount >= t.from && (t.to == null || amount < t.to)) || list[list.length - 1]
  if (!hit) return null
  const commission = Math.round(amount * hit.percent / 100)
  return { percent: hit.percent, commission, payout: amount - commission }
})
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">Comisiones de tercerización</h1>
    <p class="text-body-2 text-medium-emphasis mb-4" style="max-width: 70ch;">
      Cuánto gana la plataforma en un servicio que ejecuta un transportista afiliado. La comisión se aplica
      sobre el precio del servicio y <strong>baja por tramos</strong> a medida que sube el monto. Cada categoría
      de carga puede tener su propia tabla (p. ej. mudanzas); si no la tiene, se usa la <em>tabla general</em>.
    </p>

    <VProgressLinear v-if="loading" indeterminate class="mb-4" />

    <VRow v-else>
      <VCol cols="12" md="8">
        <VCard v-for="g in groups" :key="g.category" class="mb-4">
          <VCardText class="d-flex align-center py-2">
            <span class="text-subtitle-1 font-weight-medium">{{ catLabel(g.category) }}</span>
            <VSpacer />
            <VBtn size="small" variant="text" prepend-icon="ri-add-line" @click="openNew(g.category)">Tramo</VBtn>
          </VCardText>
          <VDivider />
          <VTable density="compact">
            <thead>
              <tr><th>Desde</th><th>Hasta</th><th class="text-right">Comisión</th><th></th><th></th></tr>
            </thead>
            <tbody>
              <tr v-for="t in g.rows" :key="t.id" :class="{ 'text-disabled': !t.active }">
                <td>{{ soles(t.from) }}</td>
                <td>{{ soles(t.to) }}</td>
                <td class="text-right font-weight-medium">{{ t.percent }} %</td>
                <td><VChip v-if="!t.active" size="x-small">inactivo</VChip></td>
                <td class="text-right">
                  <VBtn icon="ri-pencil-line" size="x-small" variant="text" @click="openEdit(t)" />
                  <VBtn icon="ri-delete-bin-line" size="x-small" variant="text" color="error" @click="remove(t)" />
                </td>
              </tr>
            </tbody>
          </VTable>
        </VCard>

        <VBtn variant="tonal" prepend-icon="ri-add-line" @click="openNew('')">Agregar tramo</VBtn>
      </VCol>

      <VCol cols="12" md="4">
        <VCard>
          <VCardText>
            <p class="text-overline mb-2">Simulador</p>
            <VTextField v-model.number="sim.amount" label="Precio del servicio (S/)" type="number" density="compact" class="mb-2" />
            <VSelect
              v-model="sim.category" label="Categoría de carga" density="compact"
              :items="[{ title: 'General', value: '' }, ...categories.map(c => ({ title: c.label, value: c.value }))]"
            />
            <VDivider class="my-3" />
            <template v-if="simResult">
              <div class="d-flex justify-space-between text-body-2"><span>Comisión</span><span class="font-weight-medium">{{ simResult.percent }} %</span></div>
              <div class="d-flex justify-space-between text-body-2"><span>La plataforma cobra</span><span class="font-weight-medium">{{ soles(simResult.commission) }}</span></div>
              <div class="d-flex justify-space-between text-body-2"><span>El transportista recibe</span><span>{{ soles(simResult.payout) }}</span></div>
            </template>
            <p v-else class="text-body-2 text-medium-emphasis">Ingresá un monto.</p>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

    <VDialog v-model="form.open" max-width="440">
      <VCard>
        <VCardTitle>{{ form.id ? 'Editar tramo' : 'Nuevo tramo' }}</VCardTitle>
        <VCardText>
          <VSelect
            v-model="form.category" label="Categoría" density="compact" class="mb-2"
            :items="[{ title: 'Tabla general', value: '' }, ...categories.map(c => ({ title: c.label, value: c.value }))]"
          />
          <VTextField v-model.number="form.from" label="Desde (S/)" type="number" density="compact" class="mb-2" />
          <VTextField v-model.number="form.to" label="Hasta (S/) — vacío = sin tope" type="number" density="compact" class="mb-2" clearable />
          <VTextField v-model.number="form.percent" label="Comisión (%)" type="number" density="compact" suffix="%" class="mb-2" />
          <VCheckbox v-model="form.active" label="Activo" density="compact" hide-details />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="form.open = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="busy" @click="save">Guardar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
