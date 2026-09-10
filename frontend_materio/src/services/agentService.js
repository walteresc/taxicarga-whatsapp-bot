// Asistente / agente de IA. El widget solo se muestra si /status dice enabled.
import { apiClient } from './apiClient'

const A = '/api/v2/agent'

export const agentStatus = () => apiClient.get(`${A}/status`)
export const agentAsk = body => apiClient.post(`${A}/ask`, body)
export const agentConversation = id => apiClient.get(`${A}/conversations/${id}/`)
export const agentProposalApply = id => apiClient.post(`${A}/proposals/${id}/apply`, {})
export const agentProposalReject = (id, motivo) => apiClient.post(`${A}/proposals/${id}/reject`, { motivo })
