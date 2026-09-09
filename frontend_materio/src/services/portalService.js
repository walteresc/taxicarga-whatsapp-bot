// Portal del Transportista (F5). API v2, scoped al transportista logueado.
// Nunca expone datos del cliente.
import { apiClient } from './apiClient'

const P = '/api/v2/portal/carrier'

export const carrierMe = () => apiClient.get(`${P}/me`)
export const carrierLoads = () => apiClient.get(`${P}/loads`)
export const carrierOffer = (code, body) => apiClient.post(`${P}/loads/${code}/offer`, body)
export const carrierOffers = () => apiClient.get(`${P}/offers`)
export const carrierAssignments = () => apiClient.get(`${P}/assignments`)
export const carrierNegotiations = () => apiClient.get(`${P}/negotiations`)
export const carrierNegotiationDetail = id => apiClient.get(`${P}/negotiations/${id}/`)
export const carrierNegotiationSend = (id, body) => apiClient.post(`${P}/negotiations/${id}/messages`, body)
export const carrierNegotiationRespond = (messageId, body) => apiClient.post(`${P}/negotiations/messages/${messageId}/respond`, body)
