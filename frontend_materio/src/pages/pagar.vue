<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { payCharge, payOrder } from '@/services/paymentsService'

const route = useRoute()
const token = route.params.token

const order = ref(null)
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const done = ref(false)

const soles = n => `S/ ${Number(n || 0).toLocaleString('es-PE', { minimumFractionDigits: 2 })}`
const isFake = computed(() => order.value?.gateway?.provider === 'fake')

const email = ref('')
const cardToken = ref('') // Culqi.js pondría acá el token de la tarjeta

const refresh = async () => {
  try {
    order.value = await payOrder(token)
    if (order.value.state === 'pagada') done.value = true
  } catch (e) { error.value = e.message || 'No se encontró la orden de pago.' } finally { loading.value = false }
}
onMounted(refresh)

const pay = async () => {
  busy.value = true
  error.value = ''
  try {
    const r = await payCharge(token, {
      sourceToken: isFake.value ? 'ok' : cardToken.value,
      email: email.value,
    })
    order.value = r
    if (r.state === 'pagada') done.value = true
    else error.value = r.error || 'El pago no se pudo procesar. Intentá de nuevo.'
  } catch (e) { error.value = e.message || 'No se pudo procesar el pago.' } finally { busy.value = false }
}
</script>

<template>
  <div class="pay-wrap">
    <VCard max-width="440" class="mx-auto" elevation="3">
      <VCardText class="pa-6">
        <div class="text-h6 font-weight-bold mb-1">Lima Express</div>
        <div class="text-body-2 text-medium-emphasis mb-4">Pago de servicio</div>

        <VProgressLinear v-if="loading" indeterminate />
        <VAlert v-else-if="error && !order" type="error" variant="tonal">{{ error }}</VAlert>

        <template v-else-if="done">
          <VAlert type="success" variant="tonal" class="mb-2">
            <div class="font-weight-medium">¡Pago registrado!</div>
            <div class="text-body-2">{{ soles(order.amount) }} · {{ order.serviceCode }}</div>
          </VAlert>
          <p class="text-body-2 text-medium-emphasis">Ya podés cerrar esta ventana.</p>
        </template>

        <template v-else-if="order">
          <VTable density="compact" class="text-body-2 mb-4">
            <tbody>
              <tr><td>Servicio</td><td>{{ order.serviceCode }}</td></tr>
              <tr><td>Ruta</td><td>{{ order.route }}</td></tr>
              <tr v-if="order.customerName"><td>Cliente</td><td>{{ order.customerName }}</td></tr>
              <tr><td>Concepto</td><td class="text-capitalize">{{ order.concept }}</td></tr>
              <tr><td class="text-h6">Total</td><td class="text-h6">{{ soles(order.amount) }}</td></tr>
            </tbody>
          </VTable>

          <VAlert v-if="!order.payable" type="warning" variant="tonal" class="mb-3">
            Esta orden de pago ya no está vigente. Pedí un nuevo link.
          </VAlert>

          <template v-else>
            <VTextField v-model="email" label="Tu correo (para el comprobante)" type="email" density="compact" class="mb-3" />
            <VAlert v-if="isFake" type="info" variant="tonal" density="compact" class="mb-3">
              Pasarela en modo prueba: el botón simula un pago aprobado.
            </VAlert>
            <div v-else id="culqi-checkout" class="mb-3">
              <VTextField v-model="cardToken" label="Token de tarjeta (Culqi.js)" density="compact"
                hint="Se completará automático cuando se integre Culqi.js" persistent-hint />
            </div>
            <VAlert v-if="error" type="error" variant="tonal" density="compact" class="mb-3">{{ error }}</VAlert>
            <VBtn block color="primary" size="large" :loading="busy" @click="pay">
              Pagar {{ soles(order.amount) }}
            </VBtn>
          </template>
        </template>
      </VCardText>
    </VCard>
    <p class="text-center text-caption text-medium-emphasis mt-3">Pago seguro · Lima Express</p>
  </div>
</template>

<style scoped>
.pay-wrap {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 24px 16px;
  background: rgb(var(--v-theme-background));
}
</style>
