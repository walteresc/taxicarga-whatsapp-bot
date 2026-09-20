// Configuración de IA — qué proveedor (OpenAI/DeepSeek) y modelo usar por
// propósito (extracción/conversación/copiloto), editable desde el panel sin
// redeploy. La API key NUNCA se maneja acá — sigue viviendo solo en el
// .env del servidor (ver apps/ia/api/views.py).
import { apiClient } from './apiClient'

export const aiConfigService = {
  async get() {
    return apiClient.get('ia/config')
  },
  async update(body) {
    return apiClient.patch('ia/config', body)
  },
}
