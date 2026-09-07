// Fábrica de recursos REST de la API v2.
//
//   const drivers = createResource('drivers')
//   drivers.list({ search, status, ordering, page, pageSize })  -> { results, page, pageSize, total, pages }
//   drivers.get(id) / drivers.create(payload) / drivers.update(id, payload) / drivers.remove(id)
//   drivers.action(id, 'toggle-active')
//
// Todas las claves de payload y respuesta son inglés canónico (contrato API).

import { apiClient } from './apiClient'

export const createResource = name => ({
  list: (params = {}) => apiClient.get(`/api/v2/${name}/`, params),
  get: id => apiClient.get(`/api/v2/${name}/${id}/`),
  create: payload => apiClient.post(`/api/v2/${name}/`, payload),
  update: (id, payload) => apiClient.patch(`/api/v2/${name}/${id}/`, payload),
  remove: id => apiClient.delete(`/api/v2/${name}/${id}/`),
  action: (id, verb, body) => apiClient.post(`/api/v2/${name}/${id}/${verb}/`, body ?? {}),
})
