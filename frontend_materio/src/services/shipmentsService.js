// Encomiendas (P1): envíos door-to-door. API v2, inglés canónico.
import { apiClient } from './apiClient'

const S = '/api/v2/shipments'

export const shipmentList = params => apiClient.get(`${S}/`, params)
export const shipmentCreate = body => apiClient.post(`${S}/`, body)
export const shipmentQuote = params => apiClient.get(`${S}/quote`, params)
export const shipmentZones = () => apiClient.get(`${S}/zones`)
export const shipmentDetail = code => apiClient.get(`${S}/${code}/`)
export const shipmentAssign = (code, body) => apiClient.post(`${S}/${code}/assign`, body)
export const shipmentEvent = (code, body) => apiClient.post(`${S}/${code}/events`, body)
export const shipmentCancel = (code, reason) => apiClient.post(`${S}/${code}/cancel`, { reason })

// Portal del transportista
export const carrierDeliveries = () => apiClient.get('/api/v2/portal/carrier/deliveries')
export const carrierDeliveryEvent = (code, body) =>
  apiClient.post(`/api/v2/portal/carrier/deliveries/${code}/event`, body)

// Público (sin sesión)
export const trackShipment = token => apiClient.get(`/api/v2/track/${token}`)
