// Portal del Cliente (F6). API v2, scoped al cliente logueado.
import { apiClient } from './apiClient'

const P = '/api/v2/portal/customer'

export const customerMe = () => apiClient.get(`${P}/me`)
export const customerLoads = () => apiClient.get(`${P}/loads`)

// Con fotos (photos: File[]) se manda multipart: el resto del body va
// stringificado en el campo `data`, ver apps/leads/photos.py::parse_request_body.
const withPhotos = (body, photos) => {
  if (!photos?.length) return body
  const fd = new FormData()
  fd.append('data', JSON.stringify(body))
  photos.forEach((file, i) => fd.append(`photo${i}`, file))

  return fd
}
export const customerPublish = (body, photos) => apiClient.post(`${P}/loads`, withPhotos(body, photos))
export const customerLoad = code => apiClient.get(`${P}/loads/${code}`)
export const customerAccept = (code, body) => apiClient.post(`${P}/loads/${code}/accept`, body)
export const customerRequestAdvisor = code => apiClient.post(`${P}/loads/${code}/request-advisor`, {})
export const customerNegotiate = (code, body) => apiClient.post(`${P}/loads/${code}/negotiate`, body)
export const customerNegotiation = code => apiClient.get(`${P}/loads/${code}/negotiation`)
export const customerNegotiationSend = (code, body) => apiClient.post(`${P}/loads/${code}/negotiation/messages`, body)
export const customerNegotiationRespond = (code, messageId, body) =>
  apiClient.post(`${P}/loads/${code}/negotiation/messages/${messageId}/respond`, body)
export const customerPay = (code, body) => apiClient.post(`${P}/loads/${code}/pay`, body || {})

// Ofertas de transportistas para MI carga (F8) — nunca el costo de compra,
// ver apps/clientes/api/portal_cliente_views.py::client_offer_item. Preferir
// una NO adjudica sola, es una señal para que el asesor confirme.
export const customerLoadOffers = code => apiClient.get(`${P}/loads/${code}/offers`)
export const customerLoadPreferOffer = (code, offerId) =>
  apiClient.post(`${P}/loads/${code}/offers/prefer`, offerId ? { offerId } : {})
