// Cotización rápida de invitado (F7). Endpoints PÚBLICOS, sin sesión.
const BASE = '/api/v2/guest'

const post = async (path, body) => {
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData
  const headers = { 'X-Requested-With': 'XMLHttpRequest' }
  if (!isForm) headers['Content-Type'] = 'application/json'
  const res = await fetch(`${BASE}/${path}`, {
    method: 'POST',
    headers,
    credentials: 'include',
    body: isForm ? body : JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || 'No se pudo completar la solicitud.')
  return data
}

// Con fotos (photos: File[]) se manda multipart: el resto del body va
// stringificado en el campo `data`, ver apps/leads/photos.py::parse_request_body.
const withPhotos = (body, photos) => {
  if (!photos?.length) return body
  const fd = new FormData()
  fd.append('data', JSON.stringify(body))
  photos.forEach((file, i) => fd.append(`photo${i}`, file))

  return fd
}

export const guestQuote = (body, photos) => post('quote', withPhotos(body, photos))
export const guestQuotePreview = body => post('quote/preview', body)
// Precio Express por cada peso en `weights` en un solo pedido — la usa el
// selector de vehículo para mostrar el precio de cada unidad sin gastar una
// llamada (y su límite de throttle) por unidad. -> {isInterprovincial, prices}
export const guestQuotePreviewBatch = body => post('quote/preview-batch', body)
export const guestSignup = body => post('signup', body)
// Estima peso/volumen por IA cuando la descripción no trae números explícitos
// (ver apps/cotizador/services_estimacion.py) — {detail} + fotos opcionales ->
// {weightKg, volumeM3, confidence, suggestedQuestion}. Con fotos, la IA las usa
// como evidencia principal para el volumen.
export const guestCargoEstimate = (body, photos) => post('cargo/estimate', withPhotos(body, photos))
