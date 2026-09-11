// Socios comerciales (P4): tiendas que integran la API de envíos. API v2 interna.
import { apiClient } from './apiClient'

const P = '/api/v2/partners'

export const partnerList = () => apiClient.get(`${P}/`)
export const partnerCreate = body => apiClient.post(`${P}/`, body)
export const partnerDetail = id => apiClient.get(`${P}/${id}/`)
export const partnerUpdate = (id, body) => apiClient.patch(`${P}/${id}/`, body)
export const partnerKeyCreate = (id, body) => apiClient.post(`${P}/${id}/keys`, body)
export const partnerKeyRevoke = (id, keyId) => apiClient.post(`${P}/${id}/keys/${keyId}/revoke`, {})
