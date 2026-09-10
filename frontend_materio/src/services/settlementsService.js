// Liquidaciones de tercerización (P1): lo que la plataforma le paga a cada
// transportista, neto de comisión. Vista de Finanzas + "Mis cobros" del portal.
import { apiClient } from './apiClient'

const S = '/api/v2/settlements'

export const settlementList = params => apiClient.get(`${S}/`, params)
export const settlementSummary = () => apiClient.get(`${S}/summary`)
export const settlementUpdate = (id, body) => apiClient.patch(`${S}/${id}/`, body)
export const settlementSettle = (id, body) => apiClient.post(`${S}/${id}/settle`, body)
export const settlementVoid = (id, body) => apiClient.post(`${S}/${id}/void`, body)

// Portal del transportista
export const carrierEarnings = () => apiClient.get('/api/v2/portal/carrier/earnings')
