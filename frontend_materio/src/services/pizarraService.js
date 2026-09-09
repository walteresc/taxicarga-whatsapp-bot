// Pizarra de operaciones. API v2.
import { apiClient } from './apiClient'

export const fetchPizarra = (date, signal) => apiClient.get('/api/v2/pizarra/', { date }, { signal })
export const pizarraAssign = body => apiClient.post('/api/v2/pizarra/assign', body)
export const pizarraMove = body => apiClient.post('/api/v2/pizarra/move', body)
export const pizarraUnassign = assignmentId => apiClient.post('/api/v2/pizarra/unassign', { assignmentId })
export const pizarraEdit = body => apiClient.post('/api/v2/pizarra/edit', body)
export const pizarraAddCarrierRow = body => apiClient.post('/api/v2/pizarra/add-carrier-row', body)
export const pizarraRemoveCarrierRow = body => apiClient.post('/api/v2/pizarra/remove-carrier-row', body)
