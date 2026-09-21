// Configuración de precios — parámetros del cálculo por reglas base
// (apps/cotizador/pricing.py::fallback_price_for_lead), editables desde el
// panel sin redeploy.
import { apiClient } from './apiClient'

export const pricingConfigService = {
  async get() {
    return apiClient.get('cotizador/pricing-config')
  },
  async update(body) {
    return apiClient.patch('cotizador/pricing-config', body)
  },
}
