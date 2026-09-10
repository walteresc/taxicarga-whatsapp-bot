// Pagos por pasarela (P3). El checkout público vive en /pagar/<token>.
import { apiClient } from './apiClient'

// Público (sin sesión)
export const payOrder = token => apiClient.get(`/api/v2/pay/${token}`)
export const payCharge = (token, body) => apiClient.post(`/api/v2/pay/${token}/charge`, body)

// Interno: el asesor genera un link de pago para una reserva
export const bookingPaymentLink = (id, body) =>
  apiClient.post(`/api/v2/pipeline/bookings/${id}/payment-link`, body || {})
