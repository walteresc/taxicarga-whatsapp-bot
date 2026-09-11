<script setup>
import { reactive, ref } from 'vue'

import { trackingLookup } from '@/services/trackingService'

const STATE = {
  registrado: 'default', asignado: 'info', recogido: 'info', en_ruta: 'warning',
  en_destino: 'warning', en_reparto_destino: 'warning', entregado: 'success',
  fallido: 'error', devuelto: 'default', cancelado: 'default',
  pendiente: 'default', programado: 'default', en_servicio: 'warning', finalizado: 'success',
}

const form = reactive({ code: '', phone: '' })
const loading = ref(false)
const error = ref('')
const result = ref(null)

const submit = async () => {
  loading.value = true
  error.value = ''
  try { result.value = await trackingLookup(form.code.trim(), form.phone.trim()) }
  catch (e) { error.value = e.message || 'No se pudo rastrear.' }
  finally { loading.value = false }
}
const buscarOtro = () => { result.value = null; error.value = ''; form.code = ''; form.phone = '' }
</script>

<template>
  <div class="track-wrap">
    <VCard max-width="480" class="mx-auto" elevation="3">
      <VCardText class="pa-6">
        <div class="text-h6 font-weight-bold mb-1">Lima Express</div>
        <div class="text-body-2 text-medium-emphasis mb-4">Rastrea tu carga o envío</div>

        <template v-if="!result">
          <p class="text-body-2 text-medium-emphasis mb-4">
            Ingresá el código que te dimos (por ejemplo <strong>ENC-00042</strong> o <strong>CRG-0031</strong>)
            y tu teléfono, para ver el estado sin necesidad de iniciar sesión.
          </p>
          <VTextField v-model="form.code" label="Código" density="comfortable" class="mb-3" />
          <VTextField
            v-model="form.phone" label="Teléfono" density="comfortable" class="mb-1"
            hint="Con los últimos 4 dígitos alcanza." persistent-hint
          />
          <VAlert v-if="error" type="error" variant="tonal" class="mt-4" density="compact">{{ error }}</VAlert>
          <VBtn
            color="primary" block class="mt-4" :loading="loading"
            :disabled="!form.code || form.phone.length < 4" @click="submit"
          >
            Rastrear
          </VBtn>
          <div class="text-center text-caption text-medium-emphasis mt-4">
            ¿Ya tenés el link que te mandamos por WhatsApp? Con eso alcanza — no necesitás este formulario.
          </div>
        </template>

        <template v-else>
          <div class="d-flex align-center ga-2 mb-1">
            <span class="text-h6">{{ result.code }}</span>
            <VChip size="small" :color="STATE[result.state]">{{ result.stateLabel }}</VChip>
          </div>
          <div class="text-body-2 text-medium-emphasis mb-4">{{ result.route }}</div>

          <!-- Encomienda: alertas + timeline de eventos -->
          <template v-if="result.type === 'shipment'">
            <VAlert v-if="result.state === 'en_destino' && result.pickupPoint" type="warning" variant="tonal" class="mb-4">
              Tu paquete está en <strong>{{ result.pickupPoint }}</strong>, esperando que lo recojas.
            </VAlert>
            <VAlert v-if="result.deliveredAt" type="success" variant="tonal" class="mb-4">
              Entregado{{ result.deliveredTo ? ` a ${result.deliveredTo}` : '' }} el
              {{ new Date(result.deliveredAt).toLocaleString('es-PE') }}
            </VAlert>
            <VTimeline density="compact" side="end" truncate-line="both">
              <VTimelineItem v-for="(ev, i) in result.events" :key="i" size="x-small" :dot-color="STATE[ev.state]">
                <div class="text-body-2 font-weight-medium">{{ ev.label }}</div>
                <div class="text-caption text-medium-emphasis">
                  {{ ev.detail }}<span v-if="ev.detail"> · </span>{{ new Date(ev.at).toLocaleString('es-PE') }}
                </div>
              </VTimelineItem>
            </VTimeline>
          </template>

          <!-- Carga (mudanza / carga general): estado actual, todavía sin timeline -->
          <template v-else>
            <VList density="compact" class="mb-2">
              <VListItem v-if="result.date" prepend-icon="ri-calendar-line" :title="result.date" :subtitle="result.schedule || undefined" />
              <VListItem
                v-if="result.assignee" prepend-icon="ri-truck-line"
                :title="result.assignee.name" :subtitle="[result.assignee.plate, result.assignee.driver].filter(Boolean).join(' · ')"
              />
              <VListItem v-if="!result.assignee" prepend-icon="ri-time-line" title="Todavía no se asignó transportista." />
            </VList>
          </template>

          <VBtn variant="text" block class="mt-4" @click="buscarOtro">Rastrear otro código</VBtn>
        </template>
      </VCardText>
    </VCard>
    <p class="text-center text-caption text-medium-emphasis mt-3">Lima Express</p>
  </div>
</template>

<style scoped>
.track-wrap {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 24px 16px;
  background: rgb(var(--v-theme-background));
}
</style>
