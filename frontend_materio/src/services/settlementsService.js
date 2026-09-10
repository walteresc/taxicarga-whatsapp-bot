// Liquidaciones de tercerización (P1): lo que la plataforma le paga a cada
// transportista, neto de comisión. Vista de Finanzas + "Mis cobros" del portal.
import { apiClient } from './apiClient'

const S = '/api/v2/settlements'

export const settlementList = params => apiClient.get(`${S}/`, params)
export const settlementSummary = () => apiClient.get(`${S}/summary`)
export const settlementUpdate = (id, body) => apiClient.patch(`${S}/${id}/`, body)
export const settlementSettle = (id, body) => apiClient.post(`${S}/${id}/settle`, body)
export const settlementVoid = (id, body) => apiClient.post(`${S}/${id}/void`, body)

// Lotes de pago a transportistas (P6)
export const batchList = params => apiClient.get(`${S}/batches`, params)
export const batchCreate = body => apiClient.post(`${S}/batches`, body)
export const batchDetail = id => apiClient.get(`${S}/batches/${id}`)
export const batchPay = (id, body) => apiClient.post(`${S}/batches/${id}/pay`, body)
export const batchVoid = id => apiClient.post(`${S}/batches/${id}/void`, {})

// Portal del transportista
export const carrierEarnings = () => apiClient.get('/api/v2/portal/carrier/earnings')
export const carrierPayout = () => apiClient.get('/api/v2/portal/carrier/payout')
export const carrierPayoutUpdate = body => apiClient.patch('/api/v2/portal/carrier/payout', body)
