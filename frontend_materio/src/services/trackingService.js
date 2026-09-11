// Rastreo público unificado (Fase 0): código + teléfono, sin login.
// Complementa el link con token (/seguimiento/:token, ver shipmentsService) —
// este es el respaldo para cuando el cliente no lo tiene a mano.
import { apiClient } from './apiClient'

export const trackingLookup = (code, phone) => apiClient.post('/api/v2/track/lookup', { code, phone })
