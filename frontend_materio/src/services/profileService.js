// Mi perfil (autoservicio) — ver/editar datos propios y cambiar contraseña.
import { apiClient } from './apiClient'

export const getProfile = () => apiClient.get('/api/v2/me')
export const updateProfile = body => apiClient.patch('/api/v2/me', body)
export const changePassword = body => apiClient.post('/api/v2/me/change-password', body)
