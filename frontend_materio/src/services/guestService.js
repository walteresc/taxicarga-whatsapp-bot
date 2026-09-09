// Cotización rápida de invitado (F7). Endpoints PÚBLICOS, sin sesión.
const BASE = '/api/v2/guest'

const post = async (path, body) => {
  const res = await fetch(`${BASE}/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    credentials: 'include',
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || 'No se pudo completar la solicitud.')
  return data
}

export const guestQuote = body => post('quote', body)
export const guestSignup = body => post('signup', body)
