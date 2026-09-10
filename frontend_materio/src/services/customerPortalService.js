// Portal del Cliente (F6). API v2, scoped al cliente logueado.
import { apiClient } from './apiClient'

const P = '/api/v2/portal/customer'

export const customerMe = () => apiClient.get(`${P}/me`)
export const customerLoads = () => apiClient.get(`${P}/loads`)
export const customerPublish = body => apiClient.post(`${P}/loads`, body)
export const customerLoad = code => apiClient.get(`${P}/loads/${code}`)
export const customerAccept = (code, body) => apiClient.post(`${P}/loads/${code}/accept`, body)
export const customerRequestAdvisor = code => apiClient.post(`${P}/loads/${code}/request-advisor`, {})
export const customerNegotiate = (code, body) => apiClient.post(`${P}/loads/${code}/negotiate`, body)
export const customerNegotiation = code => apiClient.get(`${P}/loads/${code}/negotiation`)
export const customerNegotiationSend = (code, body) => apiClient.post(`${P}/loads/${code}/negotiation/messages`, body)
export const customerNegotiationRespond = (code, messageId, body) =>
  apiClient.post(`${P}/loads/${code}/negotiation/messages/${messageId}/respond`, body)
export const customerPay = (code, body) => apiClient.post(`${P}/loads/${code}/pay`, body || {})
