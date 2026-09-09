// Negociaciones (F2): mesas de precio cliente↔TaxiCarga (venta) y TaxiCarga↔transportista (compra).
// API v2, inglés canónico. El asesor mueve todo; puede pausar la mesa.
import { apiClient } from './apiClient'

const N = '/api/v2/negotiations'

export const negotiationList = params => apiClient.get(`${N}/`, params)
export const negotiationDetail = id => apiClient.get(`${N}/${id}/`)
export const negotiationPostMessage = (id, body) => apiClient.post(`${N}/${id}/messages`, body)
export const negotiationRespond = (messageId, body) => apiClient.post(`${N}/messages/${messageId}/respond`, body)
export const negotiationPause = (id, reason) => apiClient.post(`${N}/${id}/pause`, { reason })
export const negotiationResume = id => apiClient.post(`${N}/${id}/resume`, {})
export const negotiationClose = (id, agreement) => apiClient.post(`${N}/${id}/close`, { agreement })
