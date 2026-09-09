// Usuarios y permisos (F4). API v2. Solo Administrador / Admin de sistema.
import { apiClient } from './apiClient'

export const userList = params => apiClient.get('/api/v2/users/', params)
export const userDetail = id => apiClient.get(`/api/v2/users/${id}/`)
export const userUpdate = (id, body) => apiClient.patch(`/api/v2/users/${id}/`, body)
export const roleList = () => apiClient.get('/api/v2/roles/')
