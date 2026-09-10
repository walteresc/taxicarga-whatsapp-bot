// Publicaciones a transportistas (F3): publicar carga, registrar ofertas, adjudicar.
// API v2, inglés canónico.
import { apiClient } from './apiClient'

const P = '/api/v2/publications'

export const publicationList = params => apiClient.get(`${P}/`, params)
export const publicationDetail = id => apiClient.get(`${P}/${id}/`)
export const publicationPublish = (id, groups) => apiClient.post(`${P}/${id}/publish`, { groups })
export const publicationAddOffer = (id, body) => apiClient.post(`${P}/${id}/offers`, body)
export const publicationAward = (id, body) => apiClient.post(`${P}/${id}/award`, body)

// Política de derivación de interprovinciales (G3).
export const outsourcingSettings = () => apiClient.get('/api/v2/outsourcing/settings')
export const outsourcingSettingsUpdate = body => apiClient.patch('/api/v2/outsourcing/settings', body)
