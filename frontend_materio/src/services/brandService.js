// Marca (nombre + logo) — dato de negocio editable desde Configuración →
// Marca. Ver apps/dashboard/api/brand_views.py.
import { apiClient } from './apiClient'

export const publicBrand = () => apiClient.get('public/brand')
export const brandConfig = () => apiClient.get('brand')

export const updateBrand = ({ name, logoFile, removeLogo } = {}) => {
  if (!logoFile && !removeLogo) return apiClient.patch('brand', { name })

  const form = new FormData()
  if (name !== undefined) form.set('name', name)
  if (logoFile) form.set('logo', logoFile)
  if (removeLogo) form.set('removeLogo', '1')

  return apiClient.patch('brand', form)
}
