<script setup>
import { computed, reactive, ref } from 'vue'

import { apiClient } from '@/services/apiClient'
import { usePipelineStore } from '@/stores/pipelineStore'

const pipelineStore = usePipelineStore()

// Vista del servicio (estilo Materio / Vuetify). Se alimenta de `serviceData`
// (lo que arma la bandeja en _service_data) + `stageExtra` (precios frescos del
// endpoint /stage). El asesor edita todo con PATCH pipeline/leads/{id}/service.
const props = defineProps({
  serviceData: { type: Object, default: () => ({}) },
  stageExtra: { type: Object, default: () => ({}) },
  interactive: { type: Boolean, default: false },
  leadId: { type: Number, default: null },
  // El padre (modal Ver) controla el botón Editar desde su barra de título.
  externalEditControl: { type: Boolean, default: false },
  // Modo formulario para Reservar: siempre en edición, sin botones propios;
  // el padre lee los datos con buildPayload() y confirma la reserva.
  bookingMode: { type: Boolean, default: false },
})
const emit = defineEmits(['use-suggested', 'saved', 'edit-change'])

const localOverride = reactive({})
const svc = computed(() => ({ ...(props.serviceData || {}), ...localOverride }))
const ext = computed(() => props.stageExtra || {})
const _money = v => (v != null && v !== '' && !Number.isNaN(Number(v)) ? `S/ ${Number(v).toFixed(2)}` : null)
const _val = v => (v === null || v === undefined || v === '' ? '—' : String(v))

const floorTxt = n => {
  if (n === 0) return 'Planta baja'
  if (n < 0) return `Sótano ${Math.abs(n)}`
  return n != null && n !== '' ? `Piso ${n}` : '—'
}
const accessTxt = b => (b === true ? 'Ascensor' : b === false ? 'Escaleras' : '—')

const typeVal = computed(() => _val(svc.value.type))
const dateVal = computed(() => svc.value.date || 'Por confirmar')
const scheduleVal = computed(() => _val(svc.value.schedule))
const customerName = computed(() => _val(props.serviceData?.customer_name || svc.value.customer_name))
const customerPhone = computed(() => _val(props.serviceData?.customer_phone || svc.value.customer_phone))
const contactName = computed(() => _val(svc.value.contact_name))
const contactPhone = computed(() => _val(svc.value.contact_phone))

const CLAMP_LEN = 140
const itemsExpanded = ref(false)
const heavyExpanded = ref(false)
const itemsLong = computed(() => (svc.value.items || '').length > CLAMP_LEN)
const heavyLong = computed(() => (svc.value.heavy_items || '').length > CLAMP_LEN)
const weightVol = computed(() => {
  const s = svc.value
  const p = []
  if (s.weight_kg) p.push(`${s.weight_kg} kg`)
  if (s.volume_m3) p.push(`${s.volume_m3} m³`)
  return p.join(' · ')
})
const extraServices = computed(() => svc.value.extra_services || [])

const suggestedNum = computed(() => ext.value.suggestedPrice ?? svc.value.suggested_price ?? null)
const suggestedPrice = computed(() => _money(suggestedNum.value))
const currentQuoted = computed(() => ext.value.quotedPrice ?? svc.value.quoted_price ?? null)
const quotedPrice = computed(() => _money(currentQuoted.value))
const quotedPlaceholder = computed(() =>
  currentQuoted.value != null ? String(Number(currentQuoted.value)) : 'Monto',
)

const chatPriceNum = computed(() => ext.value.chatPrice ?? svc.value.chat_price ?? null)
const chatPrice = computed(() => _money(chatPriceNum.value))
const chatIncludes = computed(() => ext.value.chatPriceIncludes || svc.value.chat_price_includes || '')
const chatNote = computed(() => ext.value.chatPriceNote || svc.value.chat_price_note || '')
const chatAccepted = computed(() => ext.value.chatPriceAccepted || svc.value.chat_price_accepted || false)

// ── Edición ────────────────────────────────────────────────────────────────
const FLOOR_OPTS = [
  { v: '', t: '—' },
  ...Array.from({ length: 7 }, (_, i) => ({ v: -(7 - i), t: `Sótano ${7 - i}` })),
  { v: 0, t: 'Planta baja' },
  ...Array.from({ length: 25 }, (_, i) => ({ v: i + 1, t: `Piso ${i + 1}` })),
]
const ACCESS_OPTS = [
  { v: '', t: '—' },
  { v: 'si', t: 'Ascensor' },
  { v: 'no', t: 'Escaleras' },
  { v: 'ambos', t: 'Ascensor y escaleras' },
]
const floorItems = FLOOR_OPTS.map(o => ({ title: o.t, value: o.v }))
const accessItems = ACCESS_OPTS.map(o => ({ title: o.t, value: o.v }))
// El modal de la bandeja usa z-index alto; el menú del combo tiene que ganarle.
const menuProps = { zIndex: 100060 }

const editing = ref(false)
const showMore = ref(false)
const saving = ref(false)
const editErr = ref('')
const form = reactive({})
const isoDate = v => (v && /^\d{4}-\d{2}-\d{2}/.test(String(v)) ? String(v).slice(0, 10) : '')
const numFloor = v => (v != null && v !== '' ? Number(v) : '')

const startEdit = () => {
  const s = svc.value
  Object.assign(form, {
    customerName: props.serviceData?.customer_name || s.customer_name || '',
    contactName: s.contact_name || '',
    contactPhone: s.contact_phone || '',
    type: s.type || '',
    origin: s.origin || '',
    destination: s.destination || '',
    addressOrigin: s.address_origin || '',
    addressDestination: s.address_destination || '',
    floorOrigin: numFloor(s.floor_origin),
    floorDestination: numFloor(s.floor_destination),
    elevatorOrigin: s.elevator_origin === true ? 'si' : s.elevator_origin === false ? 'no' : '',
    elevatorDestination: s.elevator_destination === true ? 'si' : s.elevator_destination === false ? 'no' : '',
    serviceDate: isoDate(s.date),
    schedule: s.schedule || '',
    items: s.items || '',
    heavyItems: s.heavy_items || '',
    weightKg: s.weight_kg ?? '',
    volumeM3: s.volume_m3 ?? '',
    // En Reservar precargamos el precio; en Editar va vacío (placeholder).
    quotedPrice: props.bookingMode
      ? String(ext.value.quotedPrice ?? s.quoted_price ?? s.suggested_price ?? '')
      : '',
  })
  editErr.value = ''
  editing.value = true
  emit('edit-change', true)
}
const cancelEdit = () => {
  editing.value = false
  emit('edit-change', false)
}

const _b3 = v => (v === 'si' || v === 'ambos' ? true : v === 'no' ? false : null)
const buildPayload = () => ({
  customerName: form.customerName,
  contactName: form.contactName, contactPhone: form.contactPhone,
  type: form.type, origin: form.origin, destination: form.destination,
  addressOrigin: form.addressOrigin, addressDestination: form.addressDestination,
  floorOrigin: form.floorOrigin, floorDestination: form.floorDestination,
  elevatorOrigin: _b3(form.elevatorOrigin), elevatorDestination: _b3(form.elevatorDestination),
  serviceDate: form.serviceDate, schedule: form.schedule,
  items: form.items, heavyItems: form.heavyItems,
  weightKg: String(form.weightKg).replace(',', '.'),
  volumeM3: String(form.volumeM3).replace(',', '.'),
  quotedPrice: String(form.quotedPrice || '').replace(',', '.').trim(),
})

defineExpose({ startEdit, buildPayload })
if (props.bookingMode) startEdit()

const save = async () => {
  if (!props.leadId) { editErr.value = 'No hay lead asociado.'; return }
  saving.value = true
  editErr.value = ''
  const b3 = _b3
  const payload = buildPayload()
  try {
    const resp = await apiClient.patch(`pipeline/leads/${props.leadId}/service`, payload)
    const num = v => (v === '' || v == null ? null : Number(v))
    if (resp && resp.quotedPrice != null) {
      localOverride.quoted_price = resp.quotedPrice
      pipelineStore.bump()
      window.dispatchEvent(new Event('pipeline:stage-refresh'))
    }
    Object.assign(localOverride, {
      customer_name: form.customerName || null,
      contact_name: form.contactName || null,
      contact_phone: form.contactPhone || null,
      type: form.type || null,
      origin: form.origin || null,
      destination: form.destination || null,
      address_origin: form.addressOrigin || null,
      address_destination: form.addressDestination || null,
      floor_origin: num(form.floorOrigin),
      floor_destination: num(form.floorDestination),
      elevator_origin: b3(form.elevatorOrigin),
      elevator_destination: b3(form.elevatorDestination),
      date: form.serviceDate || null,
      schedule: form.schedule || null,
      items: form.items || null,
      heavy_items: form.heavyItems || null,
      weight_kg: num(form.weightKg),
      volume_m3: num(form.volumeM3),
    })
    editing.value = false
    emit('edit-change', false)
    emit('saved', payload)
  } catch (e) {
    editErr.value = e.message || 'No se pudo guardar.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div>
    <div
      v-if="!externalEditControl && !bookingMode"
      class="d-flex align-center justify-space-between mb-2"
    >
      <span class="text-caption text-uppercase font-weight-bold text-medium-emphasis">Resumen del servicio</span>
      <VBtn
        v-if="leadId && !editing"
        size="x-small"
        variant="tonal"
        color="primary"
        prepend-icon="ri-pencil-line"
        @click="startEdit"
      >
        Editar
      </VBtn>
    </div>

    <!-- ══ LECTURA ══ -->
    <template v-if="!editing">
      <VRow dense>
        <!-- Datos de cliente: primero -->
        <VCol cols="12">
          <VCard variant="outlined">
            <div class="ss-hd">
              <VIcon
                icon="ri-user-3-line"
                size="14"
              /> Datos de cliente
            </div>
            <VRow no-gutters>
              <VCol
                cols="6"
                class="pa-3"
              >
                <div class="ss-align">
                  <i>Cliente:</i><b>{{ customerName }}</b>
                  <i>Teléfono:</i><b>{{ customerPhone }}</b>
                </div>
              </VCol>
              <VCol
                cols="6"
                class="pa-3 ss-col2"
              >
                <div class="ss-align">
                  <i>Contacto:</i><b>{{ contactName }}</b>
                  <i>Tel. contacto:</i><b>{{ contactPhone }}</b>
                </div>
              </VCol>
            </VRow>
          </VCard>
        </VCol>

        <!-- Origen y Destino: tarjetas verticales lado a lado -->
        <VCol cols="6">
          <VCard
            variant="outlined"
            class="h-100"
          >
            <div class="ss-hd">
              <VIcon
                icon="ri-map-pin-line"
                size="14"
              /> Origen
              <span
                v-if="svc.origin"
                class="ss-hd-sub"
              >· {{ svc.origin }}</span>
            </div>
            <VCardText class="pa-3">
              <div class="ss-align">
                <i>Dirección:</i><b>{{ _val(svc.address_origin) }}</b>
                <i>Piso:</i><b>{{ floorTxt(svc.floor_origin) }}</b>
                <i>Acceso:</i><b>{{ accessTxt(svc.elevator_origin) }}</b>
              </div>
            </VCardText>
          </VCard>
        </VCol>
        <VCol cols="6">
          <VCard
            variant="outlined"
            class="h-100"
          >
            <div class="ss-hd">
              <VIcon
                icon="ri-map-pin-2-line"
                size="14"
              /> Destino
              <span
                v-if="svc.destination"
                class="ss-hd-sub"
              >· {{ svc.destination }}</span>
            </div>
            <VCardText class="pa-3">
              <div class="ss-align">
                <i>Dirección:</i><b>{{ _val(svc.address_destination) }}</b>
                <i>Piso:</i><b>{{ floorTxt(svc.floor_destination) }}</b>
                <i>Acceso:</i><b>{{ accessTxt(svc.elevator_destination) }}</b>
              </div>
            </VCardText>
          </VCard>
        </VCol>

        <!-- Detalle de carga (con subdivisión "otros detalles") -->
        <VCol cols="12">
          <VCard variant="outlined">
            <div class="ss-hd">
              <VIcon
                icon="ri-archive-line"
                size="14"
              /> Detalle de carga
            </div>
            <div class="ss-blk pa-3">
              <p
                class="ss-txt"
                :class="{ 'ss-txt--clamp': itemsLong && !itemsExpanded, 'text-disabled': !svc.items }"
              >
                {{ svc.items || '—' }}
              </p>
              <VBtn
                v-if="itemsLong"
                size="x-small"
                variant="text"
                color="primary"
                @click="itemsExpanded = !itemsExpanded"
              >
                {{ itemsExpanded ? 'Ver menos' : 'Ver más' }}
              </VBtn>
            </div>
            <VDivider />
            <VRow no-gutters>
              <VCol
                cols="6"
                class="px-3 py-2"
              >
                <div class="ss-align ss-align--sm">
                  <i>Tipo:</i><b>{{ typeVal }}</b>
                  <i>Peso / Volumen:</i><b>{{ weightVol || '—' }}</b>
                </div>
              </VCol>
              <VCol
                cols="6"
                class="px-3 py-2 ss-col2"
              >
                <div class="ss-align ss-align--sm">
                  <i>Objetos pesados:</i><b>{{ svc.heavy_items || '—' }}</b>
                  <i>Servicios:</i>
                  <span>
                    <template v-if="extraServices.length">
                      <VChip
                        v-for="(sv, i) in extraServices"
                        :key="i"
                        size="x-small"
                        color="primary"
                        variant="tonal"
                        class="mr-1 mb-1"
                      >
                        {{ sv }}
                      </VChip>
                    </template>
                    <template v-else>—</template>
                  </span>
                </div>
              </VCol>
            </VRow>
          </VCard>
        </VCol>

        <!-- Reserva | Precios: paralelas -->
        <VCol cols="6">
          <VCard
            variant="outlined"
            class="h-100"
          >
            <div class="ss-hd">
              <VIcon
                icon="ri-calendar-check-line"
                size="14"
              /> Reserva
            </div>
            <VCardText class="pa-3 ss-when">
              <div class="ss-align">
                <i>Fecha:</i><b>{{ dateVal }}</b>
                <i>Horario:</i><b>{{ scheduleVal }}</b>
              </div>
            </VCardText>
          </VCard>
        </VCol>
        <VCol cols="6">
          <VCard
            variant="outlined"
            class="h-100"
          >
            <div class="ss-hd">
              <VIcon
                icon="ri-money-dollar-circle-line"
                size="14"
              /> Precios
            </div>
            <div class="ss-price">
              <span class="text-caption text-disabled">Precio sugerido</span>
              <div class="d-flex align-center ga-2">
                <span class="text-body-2 text-disabled">{{ suggestedPrice || '—' }}</span>
                <VBtn
                  v-if="interactive && suggestedNum != null"
                  size="x-small"
                  variant="tonal"
                  color="primary"
                  @click="emit('use-suggested', suggestedNum)"
                >
                  Usar
                </VBtn>
              </div>
            </div>
            <VDivider />
            <div class="ss-price bg-success-lighten">
              <span class="text-caption font-weight-bold text-success">Precio cotizado</span>
              <span class="text-subtitle-1 font-weight-bold text-success">{{ quotedPrice || '—' }}</span>
            </div>
          </VCard>
        </VCol>

        <!-- Detectado en el chat: fila completa -->
        <VCol
          v-if="chatPrice"
          cols="12"
        >
          <VAlert
            color="info"
            variant="tonal"
            density="compact"
          >
            <div class="d-flex align-center ga-2 flex-wrap">
              <span class="text-caption font-weight-bold">
                <VIcon
                  icon="ri-robot-2-line"
                  size="13"
                /> Detectado en el chat
              </span>
              <strong class="text-subtitle-1">{{ chatPrice }}</strong>
              <VChip
                v-if="chatAccepted"
                size="x-small"
                color="success"
                variant="flat"
              >
                aceptado por el cliente
              </VChip>
            </div>
            <div
              v-if="chatIncludes || chatNote"
              class="text-caption mt-1"
            >
              <div v-if="chatIncludes">
                <b>Incluye:</b> {{ chatIncludes }}
              </div>
              <div v-if="chatNote">
                <b>Pago:</b> {{ chatNote }}
              </div>
            </div>
          </VAlert>
        </VCol>
      </VRow>
    </template>

    <!-- ══ EDICIÓN (misma estructura que la vista de lectura) ══ -->
    <template v-else>
      <VRow dense>
        <!-- Datos de cliente: primero -->
        <VCol cols="12">
          <VCard variant="outlined">
            <div class="ss-hd">
              <VIcon
                icon="ri-user-3-line"
                size="14"
              /> Datos de cliente
            </div>
            <VRow no-gutters>
              <VCol
                cols="6"
                class="pa-3"
              >
                <VTextField
                  v-model="form.customerName"
                  label="Cliente"
                  density="compact"
                />
              </VCol>
              <VCol
                cols="6"
                class="pa-3 ss-col2"
              >
                <VTextField
                  v-model="form.contactName"
                  label="Nombre de contacto (opcional)"
                  density="compact"
                  class="mb-3"
                />
                <VTextField
                  v-model="form.contactPhone"
                  label="Teléfono de contacto (opcional)"
                  type="text"
                  inputmode="tel"
                  density="compact"
                />
              </VCol>
            </VRow>
          </VCard>
        </VCol>

        <!-- Origen | Destino -->
        <VCol cols="6">
          <VCard
            variant="outlined"
            class="h-100"
          >
            <div class="ss-hd">
              <VIcon
                icon="ri-map-pin-line"
                size="14"
              /> Origen
            </div>
            <VCardText class="pa-3">
              <VTextField
                v-model="form.addressOrigin"
                label="Dirección"
                density="compact"
                class="mb-3"
              />
              <VTextField
                v-model="form.origin"
                label="Distrito"
                density="compact"
                class="mb-3"
              />
              <VSelect
                v-model="form.floorOrigin"
                :items="floorItems"
                :menu-props="menuProps"
                label="Piso"
                density="compact"
                class="mb-3"
              />
              <VSelect
                v-model="form.elevatorOrigin"
                :items="accessItems"
                :menu-props="menuProps"
                label="Acceso"
                density="compact"
              />
            </VCardText>
          </VCard>
        </VCol>
        <VCol cols="6">
          <VCard
            variant="outlined"
            class="h-100"
          >
            <div class="ss-hd">
              <VIcon
                icon="ri-map-pin-2-line"
                size="14"
              /> Destino
            </div>
            <VCardText class="pa-3">
              <VTextField
                v-model="form.addressDestination"
                label="Dirección"
                density="compact"
                class="mb-3"
              />
              <VTextField
                v-model="form.destination"
                label="Distrito"
                density="compact"
                class="mb-3"
              />
              <VSelect
                v-model="form.floorDestination"
                :items="floorItems"
                :menu-props="menuProps"
                label="Piso"
                density="compact"
                class="mb-3"
              />
              <VSelect
                v-model="form.elevatorDestination"
                :items="accessItems"
                :menu-props="menuProps"
                label="Acceso"
                density="compact"
              />
            </VCardText>
          </VCard>
        </VCol>

        <!-- Detalle de carga -->
        <VCol cols="12">
          <VCard variant="outlined">
            <div class="ss-hd">
              <VIcon
                icon="ri-archive-line"
                size="14"
              /> Detalle de carga
            </div>
            <VCardText class="pa-3">
              <VTextarea
                v-model="form.items"
                label="Detalle de carga"
                rows="2"
                auto-grow
                density="compact"
              />
            </VCardText>
            <VDivider />
            <VBtn
              variant="text"
              size="small"
              color="primary"
              block
              class="justify-start"
              @click="showMore = !showMore"
            >
              <VIcon
                :icon="showMore ? 'ri-arrow-up-s-line' : 'ri-arrow-down-s-line'"
                size="18"
              />
              {{ showMore ? 'Menos detalles' : 'Más detalles (tipo, peso, objetos…)' }}
            </VBtn>
            <VExpandTransition>
              <VRow
                v-show="showMore"
                no-gutters
              >
                <VCol
                  cols="6"
                  class="pa-3"
                >
                  <VTextField
                    v-model="form.type"
                    label="Tipo"
                    placeholder="mudanza / carga / oficina"
                    density="compact"
                    class="mb-3"
                  />
                  <VTextField
                    v-model="form.weightKg"
                    label="Peso (kg)"
                    type="text"
                    inputmode="decimal"
                    density="compact"
                    class="mb-3"
                  />
                  <VTextField
                    v-model="form.volumeM3"
                    label="Volumen (m³)"
                    type="text"
                    inputmode="decimal"
                    density="compact"
                  />
                </VCol>
                <VCol
                  cols="6"
                  class="pa-3 ss-col2"
                >
                  <VTextarea
                    v-model="form.heavyItems"
                    label="Objetos pesados / especiales"
                    rows="3"
                    auto-grow
                    density="compact"
                  />
                </VCol>
              </VRow>
            </VExpandTransition>
          </VCard>
        </VCol>

        <!-- Reserva | Precios -->
        <VCol cols="6">
          <VCard
            variant="outlined"
            class="h-100"
          >
            <div class="ss-hd">
              <VIcon
                icon="ri-calendar-check-line"
                size="14"
              /> Reserva
            </div>
            <VCardText class="pa-3 ss-when">
              <VTextField
                v-model="form.serviceDate"
                label="Fecha"
                type="date"
                density="compact"
                bg-color="surface"
                class="mb-3"
              />
              <VTextField
                v-model="form.schedule"
                label="Horario"
                placeholder="9:30 am"
                density="compact"
                bg-color="surface"
              />
            </VCardText>
          </VCard>
        </VCol>
        <VCol cols="6">
          <VCard
            variant="outlined"
            class="h-100"
          >
            <div class="ss-hd">
              <VIcon
                icon="ri-money-dollar-circle-line"
                size="14"
              /> Precios
            </div>
            <div class="ss-price ss-price--suggested">
              <span>Precio sugerido</span>
              <span class="ss-suggested-val">{{ suggestedPrice || '—' }}</span>
            </div>
            <VDivider />
            <div class="ss-price ss-price--quoted">
              <span class="text-caption font-weight-bold text-success">
                {{ bookingMode ? 'Precio de la reserva' : 'Precio cotizado' }}
              </span>
              <VTextField
                v-model="form.quotedPrice"
                type="text"
                inputmode="decimal"
                prefix="S/"
                :placeholder="quotedPlaceholder"
                persistent-placeholder
                density="compact"
                hide-details
                bg-color="surface"
                class="ss-price-input"
              />
            </div>
          </VCard>
        </VCol>
      </VRow>

      <VAlert
        v-if="editErr && !bookingMode"
        type="error"
        variant="tonal"
        density="compact"
        class="mb-3"
      >
        {{ editErr }}
      </VAlert>
      <div
        v-if="!bookingMode"
        class="d-flex justify-end ga-2 mt-3"
      >
        <VBtn
          variant="text"
          :disabled="saving"
          @click="cancelEdit"
        >
          Cancelar
        </VBtn>
        <VBtn
          color="primary"
          :loading="saving"
          @click="save"
        >
          Guardar
        </VBtn>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ss-hd {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 7px 12px;
  background: rgb(var(--v-theme-on-surface), 0.04);
  border-bottom: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-on-surface), 0.6);
}

.ss-pair > i {
  font-style: normal;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-on-surface), 0.55);
}

/* Etiqueta y valor alineados en columnas (origen, destino, carga, reserva). */
.ss-align {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 3px 8px;
  align-items: baseline;
  font-size: 0.8rem;
}

.ss-align > i {
  font-style: normal;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-on-surface), 0.55);
}

/* Datos secundarios (Tipo / Peso / Objetos / Servicios): más discretos. */
.ss-align--sm {
  gap: 2px 6px;
  font-size: 0.72rem;
}

.ss-align--sm > i {
  font-size: 0.6rem;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface), 0.45);
}

.ss-align--sm > b,
.ss-align--sm > span {
  font-weight: 400;
  color: rgb(var(--v-theme-on-surface), 0.6);
}

.ss-align > b,
.ss-align > span {
  color: rgb(var(--v-theme-on-surface), 0.87);
  overflow-wrap: anywhere;
}

.ss-col2 {
  border-left: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.ss-when {
  background: rgb(var(--v-theme-warning), 0.08);
}

.ss-when .ss-align > i {
  color: rgb(var(--v-theme-warning));
}

.ss-when .ss-align > b {
  font-weight: 700;
}

.ss-hd-sub {
  margin-left: 2px;
  font-weight: 600;
  text-transform: none;
  letter-spacing: 0;
  color: rgb(var(--v-theme-on-surface), 0.75);
}

.ss-subhd {
  padding: 5px 12px;
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-on-surface), 0.5);
  background: rgb(var(--v-theme-on-surface), 0.02);
}

.ss-blk {
  padding: 4px 0;
  font-size: 0.8rem;
}

.ss-blk > i {
  display: block;
  font-style: normal;
  margin-bottom: 2px;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-on-surface), 0.55);
}

.ss-txt {
  margin: 0;
  line-height: 1.45;
  font-weight: 700;
  white-space: pre-line;
  overflow-wrap: anywhere;
  color: rgb(var(--v-theme-on-surface), 0.87);
}

.ss-txt.text-disabled {
  font-weight: 400;
}

.ss-txt--clamp {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ss-price {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 12px;
}

.ss-price-input {
  max-width: 150px;
  flex-shrink: 0;
}

.ss-price-input :deep(input) {
  text-align: right;
  font-weight: 700;
}

.bg-success-lighten {
  background: rgb(var(--v-theme-success), 0.09);
  padding-block: 8px 12px;
}
</style>
