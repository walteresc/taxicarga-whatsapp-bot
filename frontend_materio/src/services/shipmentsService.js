// Encomiendas (P1): envíos door-to-door. API v2, inglés canónico.
import { apiClient } from './apiClient'

const S = '/api/v2/shipments'

export const shipmentList = params => apiClient.get(`${S}/`, params)
export const shipmentCreate = body => apiClient.post(`${S}/`, body)
export const shipmentQuote = params => apiClient.get(`${S}/quote`, params)
export const shipmentZones = () => apiClient.get(`${S}/zones`)

// Catálogo de puntos de entrega en destino (Fase 3 — encomienda interprovincial)
export const pickupPoints = city => apiClient.get(`${S}/pickup-points`, city ? { city } : undefined)
export const pickupPointCreate = body => apiClient.post(`${S}/pickup-points`, body)
export const pickupPointUpdate = (id, body) => apiClient.patch(`${S}/pickup-points/${id}`, body)
export const pickupPointDelete = id => apiClient.delete(`${S}/pickup-points/${id}`)
export const shipmentDetail = code => apiClient.get(`${S}/${code}/`)
export const shipmentAssign = (code, body) => apiClient.post(`${S}/${code}/assign`, body)
// Fase B — reparto a domicilio en la ciudad destino (encomienda interprovincial)
export const shipmentDestinationCarriers = code => apiClient.get(`${S}/${code}/destination-carriers`)
export const shipmentAssignDestination = (code, body) => apiClient.post(`${S}/${code}/assign-destination`, body)
export const shipmentEvent = (code, body) => apiClient.post(`${S}/${code}/events`, body)
export const shipmentCancel = (code, reason) => apiClient.post(`${S}/${code}/cancel`, { reason })

// Rutas de reparto (P2)
export const routeList = params => apiClient.get('/api/v2/routes/', params)
export const routeCreate = body => apiClient.post('/api/v2/routes/', body)
export const routeDetail = code => apiClient.get(`/api/v2/routes/${code}/`)
export const routeStops = (code, body) => apiClient.post(`/api/v2/routes/${code}/stops`, body)
export const routeStart = code => apiClient.post(`/api/v2/routes/${code}/start`, {})
export const routeClose = code => apiClient.post(`/api/v2/routes/${code}/close`, {})

// Portal del transportista
export const carrierDeliveries = () => apiClient.get('/api/v2/portal/carrier/deliveries')
export const carrierRoute = () => apiClient.get('/api/v2/portal/carrier/route')
export const carrierRouteStart = () => apiClient.post('/api/v2/portal/carrier/route', {})
// body puede ser objeto JSON o FormData (con la foto de POD) — apiClient detecta
export const carrierDeliveryEvent = (code, body) =>
  apiClient.post(`/api/v2/portal/carrier/deliveries/${code}/event`, body)

// Contra-entrega (COD) — Finanzas
export const codPending = () => apiClient.get('/api/v2/cod/pending')
export const codToRemit = () => apiClient.get('/api/v2/cod/to-remit')
export const codSettlements = params => apiClient.get('/api/v2/cod/settlements', params)
export const codSettlementCreate = body => apiClient.post('/api/v2/cod/settlements', body)
export const codSettlementDetail = code => apiClient.get(`/api/v2/cod/settlements/${code}`)
export const codSettlementReconcile = (code, body) => apiClient.post(`/api/v2/cod/settlements/${code}`, body)
export const codRemit = body => apiClient.post('/api/v2/cod/to-remit', body)

// Público (sin sesión)
export const trackShipment = token => apiClient.get(`/api/v2/track/${token}`)
