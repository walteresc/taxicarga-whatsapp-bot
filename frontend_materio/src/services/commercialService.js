// Pipeline comercial: Para revisión, Por cotizar, Cotizaciones, Reservas.
// API v2, inglés canónico. Estado derivado en el backend (nunca duplicado).
import { apiClient } from './apiClient'

const P = '/api/v2/pipeline'

export const pipelineCounts = () => apiClient.get(`${P}/counts`)

// Datos del servicio de un lead con la forma de <ServiceSummary> (modal Ver).
export const leadServiceData = id => apiClient.get(`${P}/leads/${id}/service`)

// Descartar la oportunidad de un lead (→ perdido). Requiere motivo.
export const leadDiscard = (id, reason) => apiClient.post(`${P}/leads/${id}/discard`, { reason })

// Marca 'visto' el detalle de un lead en una etapa (badge de "no visto").
export const leadMarkSeen = (id, stage) => apiClient.post(`${P}/leads/${id}/mark-seen`, { stage })

// --- Potenciales ---
export const potentialList = params => apiClient.get(`${P}/potentials/`, params)
export const potentialDetail = id => apiClient.get(`${P}/potentials/${id}/`)

// --- Para revisión ---
export const reviewList = params => apiClient.get(`${P}/review/`, params)
export const reviewDetail = id => apiClient.get(`${P}/review/${id}/`)
export const reviewToQuoting = id => apiClient.post(`${P}/review/${id}/to-quoting`)
export const reviewDiscard = (id, reason) => apiClient.post(`${P}/review/${id}/discard`, { reason })

// --- Por cotizar ---
export const quoteRequestList = params => apiClient.get(`${P}/quote-requests/`, params)
export const quoteRequestDetail = id => apiClient.get(`${P}/quote-requests/${id}/`)
export const quoteRequestAssign = id => apiClient.post(`${P}/quote-requests/${id}/assign`)
export const quoteRequestSaveQuote = (id, body) => apiClient.post(`${P}/quote-requests/${id}/quote`, body)
export const quoteRequestSend = id => apiClient.post(`${P}/quote-requests/${id}/send`)

// --- Cotizaciones ---
export const quoteList = params => apiClient.get(`${P}/quotes/`, params)
export const quoteDetail = id => apiClient.get(`${P}/quotes/${id}/`)
export const quoteSetState = (id, state) => apiClient.post(`${P}/quotes/${id}/state`, { state })
export const quoteRevise = (id, body) => apiClient.post(`${P}/quotes/${id}/revise`, body)
export const quoteAccept = id => apiClient.post(`${P}/quotes/${id}/accept`)

// --- Perdidos ---
export const lostList = params => apiClient.get(`${P}/lost/`, params)
export const reactivateLead = id => apiClient.post(`${P}/leads/${id}/reactivate`)

// --- Reservas ---
export const bookingList = params => apiClient.get(`${P}/bookings/`, params)
export const bookingDetail = id => apiClient.get(`${P}/bookings/${id}/`)
export const bookingUpdate = (id, body) => apiClient.patch(`${P}/bookings/${id}/`, body)
export const bookingAddPayment = (id, body) => apiClient.post(`${P}/bookings/${id}/payment`, body)
export const bookingFinalize = id => apiClient.post(`${P}/bookings/${id}/finalize`)
export const bookingCancel = (id, reason) => apiClient.post(`${P}/bookings/${id}/cancel`, { reason })
