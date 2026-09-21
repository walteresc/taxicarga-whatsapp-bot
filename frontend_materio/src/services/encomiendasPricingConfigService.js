// Configuración de Encomiendas/Reparto — comisión sobre contra-entrega y
// costos de recojo/entrega a domicilio para envíos nacionales (siempre se
// suman, no hay oficina propia en destino — ver apps/encomiendas/models.py).
import { apiClient } from './apiClient'

export const encomiendasPricingConfigService = {
  async get() {
    return apiClient.get('shipments/pricing-config')
  },
  async update(body) {
    return apiClient.patch('shipments/pricing-config', body)
  },
}
