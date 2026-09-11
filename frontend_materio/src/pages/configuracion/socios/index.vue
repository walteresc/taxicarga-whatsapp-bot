<script setup>
import { onMounted, reactive, ref } from 'vue'

import {
  partnerCreate, partnerDetail, partnerKeyCreate, partnerKeyRevoke, partnerList, partnerUpdate,
} from '@/services/partnersService'

const soles = n => `S/ ${Number(n || 0).toLocaleString('es-PE', { minimumFractionDigits: 2 })}`
const snack = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snack, { show: true, text: t, color: c })

const partners = ref([])
const loading = ref(true)
const busy = ref(false)

const load = async () => {
  loading.value = true
  try { partners.value = (await partnerList()).results }
  catch (e) { notify(e.message || 'No se pudo cargar.', 'error') } finally { loading.value = false }
}
onMounted(load)

const form = reactive({ open: false, name: '', contactName: '', contactEmail: '', contactPhone: '', webhookUrl: '' })
const openNew = () => Object.assign(form, { open: true, name: '', contactName: '', contactEmail: '', contactPhone: '', webhookUrl: '' })
const submitNew = async () => {
  busy.value = true
  try {
    const { open, ...body } = form
    const p = await partnerCreate(body)
    form.open = false
    notify('Socio creado.')
    await load()
    openDetail(p.id)
  } catch (e) { notify(e.message || 'No se pudo crear.', 'error') } finally { busy.value = false }
}

const detail = ref(null)
const openDetail = async id => { detail.value = null; try { detail.value = await partnerDetail(id) } catch (e) { notify(e.message, 'error') } }
const toggleActive = async () => {
  busy.value = true
  try { detail.value = await partnerUpdate(detail.value.id, { active: !detail.value.active }); await load() }
  catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}
const webhookEdit = ref('')
const startEditWebhook = () => { webhookEdit.value = detail.value.webhookUrl }
const saveWebhook = async () => {
  busy.value = true
  try { detail.value = await partnerUpdate(detail.value.id, { webhookUrl: webhookEdit.value }); notify('Guardado.') }
  catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}

const newKey = reactive({ open: false, environment: 'test', token: '' })
const openNewKey = () => Object.assign(newKey, { open: true, environment: 'test', token: '' })
const createKey = async () => {
  busy.value = true
  try {
    const k = await partnerKeyCreate(detail.value.id, { environment: newKey.environment })
    newKey.token = k.token
    await openDetail(detail.value.id)
  } catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}
const copyToken = () => { try { navigator.clipboard?.writeText(newKey.token); notify('Copiada.') } catch { /* noop */ } }
const revokeKey = async k => {
  if (!confirm(`¿Revocar la llave ${k.prefix}? Dejará de funcionar de inmediato.`)) return
  busy.value = true
  try { await partnerKeyRevoke(detail.value.id, k.id); notify('Revocada.'); await openDetail(detail.value.id) }
  catch (e) { notify(e.message, 'error') } finally { busy.value = false }
}

const curlExample = id => `curl -X POST https://tudominio.pe/api/partners/v1/quotes \\
  -H "Authorization: Bearer ${id}" -H "Content-Type: application/json" \\
  -d '{"originDistrict":"Miraflores","destDistrict":"Los Olivos","weightKg":2}'`
</script>

<template>
  <section>
    <div class="d-flex align-center flex-wrap ga-2 mb-1">
      <h1 class="text-h4 font-weight-bold">Socios (API de envíos)</h1>
      <VSpacer />
      <VBtn color="primary" prepend-icon="ri-add-line" @click="openNew">Nuevo socio</VBtn>
    </div>
    <p class="text-body-2 text-medium-emphasis mb-4" style="max-width: 70ch;">
      Tiendas y plataformas que integran la API de envíos para mandar sus pedidos con tu marca y tu tarifa.
    </p>

    <VRow>
      <VCol cols="12" md="5">
        <VProgressLinear v-if="loading" indeterminate />
        <div v-else-if="!partners.length" class="text-center text-medium-emphasis py-10 text-body-2">Sin socios todavía.</div>
        <VCard v-else>
          <VList density="compact" lines="two">
            <VListItem v-for="p in partners" :key="p.id" :active="detail?.id === p.id" @click="openDetail(p.id)">
              <VListItemTitle class="d-flex align-center ga-2">
                <span class="font-weight-medium">{{ p.name }}</span>
                <VChip v-if="!p.active" size="x-small">inactivo</VChip>
              </VListItemTitle>
              <VListItemSubtitle>{{ p.shipmentCount }} envíos · saldo {{ soles(p.balance) }}</VListItemSubtitle>
            </VListItem>
          </VList>
        </VCard>
      </VCol>

      <VCol cols="12" md="7">
        <VCard v-if="!detail" class="d-flex align-center justify-center" style="min-height: 40vh;">
          <span class="text-medium-emphasis">Elegí un socio.</span>
        </VCard>
        <VCard v-else>
          <VCardText class="d-flex align-center flex-wrap ga-2">
            <span class="text-h6">{{ detail.name }}</span>
            <VChip size="small" :color="detail.active ? 'success' : 'default'">{{ detail.active ? 'Activo' : 'Inactivo' }}</VChip>
            <VSpacer />
            <VBtn size="small" variant="text" @click="toggleActive">{{ detail.active ? 'Desactivar' : 'Activar' }}</VBtn>
          </VCardText>
          <VCardText class="pt-0">
            <VTable density="compact" class="text-body-2">
              <tbody>
                <tr><td>Contacto</td><td>{{ detail.contactName || '—' }} {{ detail.contactEmail }} {{ detail.contactPhone }}</td></tr>
                <tr><td>Envíos</td><td>{{ detail.shipmentCount }}</td></tr>
                <tr><td>Saldo</td><td>{{ soles(detail.balance) }}</td></tr>
                <tr>
                  <td>Webhook</td>
                  <td>
                    <VTextField v-model="webhookEdit" density="compact" hide-details placeholder="https://tu-tienda.com/webhooks/limaexpress"
                      @focus="startEditWebhook" @blur="saveWebhook" />
                  </td>
                </tr>
              </tbody>
            </VTable>
          </VCardText>

          <VDivider />
          <VCardText>
            <div class="d-flex align-center mb-2">
              <span class="text-overline">Llaves de API</span>
              <VSpacer />
              <VBtn size="small" variant="tonal" prepend-icon="ri-key-2-line" @click="openNewKey">Generar llave</VBtn>
            </div>
            <VTable density="compact" class="text-body-2">
              <tbody>
                <tr v-for="k in detail.keys" :key="k.id">
                  <td><VChip size="x-small" :color="k.environment === 'live' ? 'success' : 'warning'">{{ k.environment }}</VChip></td>
                  <td class="font-mono">{{ k.prefix }}…</td>
                  <td>{{ k.active ? 'activa' : 'revocada' }}</td>
                  <td class="text-right">
                    <VBtn v-if="k.active" size="x-small" variant="text" color="error" @click="revokeKey(k)">Revocar</VBtn>
                  </td>
                </tr>
              </tbody>
            </VTable>
          </VCardText>

          <VExpansionPanels class="px-4 pb-4">
            <VExpansionPanel title="Cómo integrar (ejemplo)">
              <template #text>
                <pre class="text-caption" style="white-space: pre-wrap;">{{ curlExample('pk_test_xxx.secreto') }}</pre>
                <p class="text-caption text-medium-emphasis mt-2">
                  Endpoints: <code>POST /quotes</code>, <code>POST /shipments</code> (con header
                  <code>Idempotency-Key</code>), <code>GET /shipments/&lt;id&gt;</code>,
                  <code>POST /shipments/&lt;id&gt;/cancel</code>, <code>GET /coverage</code>.
                  Recibís webhooks de <code>shipment.*</code> firmados en <code>X-Signature</code> (HMAC-SHA256).
                </p>
              </template>
            </VExpansionPanel>
          </VExpansionPanels>
        </VCard>
      </VCol>
    </VRow>

    <VDialog v-model="form.open" max-width="480">
      <VCard>
        <VCardTitle>Nuevo socio</VCardTitle>
        <VCardText>
          <VTextField v-model="form.name" label="Nombre de la tienda *" density="compact" class="mb-2" />
          <VTextField v-model="form.contactName" label="Contacto" density="compact" class="mb-2" />
          <VTextField v-model="form.contactEmail" label="Email" density="compact" class="mb-2" />
          <VTextField v-model="form.contactPhone" label="Teléfono" density="compact" class="mb-2" />
          <VTextField v-model="form.webhookUrl" label="URL de webhook (opcional)" density="compact" />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="form.open = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="busy" :disabled="!form.name" @click="submitNew">Crear</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="newKey.open" max-width="480" persistent>
      <VCard>
        <VCardTitle>Nueva llave de API</VCardTitle>
        <VCardText>
          <template v-if="!newKey.token">
            <VSelect v-model="newKey.environment" label="Entorno" density="compact"
              :items="[{ title: 'Test', value: 'test' }, { title: 'Live', value: 'live' }]" />
          </template>
          <template v-else>
            <VAlert type="warning" variant="tonal" class="mb-3">
              Copiala ahora — no se vuelve a mostrar.
            </VAlert>
            <VTextField :model-value="newKey.token" readonly density="compact" append-inner-icon="ri-file-copy-line"
              @click:append-inner="copyToken" />
          </template>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn v-if="!newKey.token" variant="text" @click="newKey.open = false">Cancelar</VBtn>
          <VBtn v-if="!newKey.token" color="primary" :loading="busy" @click="createKey">Generar</VBtn>
          <VBtn v-else color="primary" @click="newKey.open = false">Listo</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snack.show" :color="snack.color" timeout="3000">{{ snack.text }}</VSnackbar>
  </section>
</template>
