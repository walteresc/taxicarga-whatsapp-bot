// Configuración del bot: 3 interruptores independientes.
//
// - customers  ("bot de conversaciones"): responde o no al cliente por WhatsApp.
//   Lee/escribe vía los mismos endpoints que ya usa la bandeja de entrada
//   (conversationService) — no se duplica esa lógica.
// - carriers   ("bot de transportistas"): igual que arriba, pero para
//   apps/tercerizacion. Endpoints propios de ese módulo (JSON en español).
// - operations ("bot operativo"): captura de datos (NLU), creación/
//   actualización de Lead y derivación automática a "Para revisión".
//   Independiente de si el bot está respondiendo o no. API v2 propia
//   (inglés canónico), ver docs/PATRON-API-VUE.md.
import { apiClient } from './apiClient'
import { conversationService } from './conversationService'

const CARRIERS_BASE = '/dashboard/tercerizacion/bot'

const carrierRequest = async (path, method = 'GET') => {
  const response = await fetch(`${CARRIERS_BASE}/${path}/`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(method !== 'GET' ? { 'X-CSRFToken': conversationService.getCsrfToken() } : {}),
    },
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)

  return response.json()
}

export const botConfigService = {
  // Estado combinado de los 3 interruptores (fuente: API v2, más
  // enabledInDeployment del kill-switch de despliegue de transportistas).
  async getStatus() {
    return apiClient.get('bot/status')
  },

  async pauseCustomers() {
    return conversationService.pauseBot()
  },
  async resumeCustomers() {
    return conversationService.activateBot()
  },

  async pauseCarriers() {
    return carrierRequest('pausar', 'POST')
  },
  async resumeCarriers() {
    return carrierRequest('activar', 'POST')
  },

  async pauseOperations() {
    return apiClient.post('bot/operations/pause')
  },
  async resumeOperations() {
    return apiClient.post('bot/operations/resume')
  },
}
