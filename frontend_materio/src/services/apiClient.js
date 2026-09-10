// Cliente HTTP base de la API v2 (panel Vue).
//
// - Envía la cookie de sesión y el X-CSRFToken en escrituras.
// - Normaliza la respuesta de error al contrato { error, fields }.
// - Ante un 401 redirige a /login conservando el destino.
//
// Contrato de la API: inglés canónico, ver docs/PATRON-API-VUE.md.

const API_ROOT = '/api/v2'

const getCookie = name => document.cookie
  .split('; ')
  .find(row => row.startsWith(`${name}=`))
  ?.split('=')
  .slice(1)
  .join('=') || ''

export class ApiError extends Error {
  constructor(message, { status, fields } = {}) {
    super(message || 'No se pudo completar la operación.')
    this.name = 'ApiError'
    this.status = status
    this.fields = fields || {}
  }
}

const redirectToLogin = () => {
  const here = window.location.pathname + window.location.search
  window.location.assign(`/login?next=${encodeURIComponent(here)}`)
}

const request = async (path, { method = 'GET', body, params, signal } = {}) => {
  let url = path.startsWith('/') ? path : `${API_ROOT}/${path}`
  if (params) {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, v)
    })
    const s = qs.toString()
    if (s) url += `?${s}`
  }

  const isForm = typeof FormData !== 'undefined' && body instanceof FormData
  const headers = { 'X-Requested-With': 'XMLHttpRequest' }
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json'
  if (method !== 'GET' && method !== 'HEAD') {
    headers['X-CSRFToken'] = decodeURIComponent(getCookie('csrftoken'))
  }

  const response = await fetch(url, {
    method,
    headers,
    credentials: 'include',
    signal,
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  })

  if (response.status === 401) {
    redirectToLogin()
    throw new ApiError('Sesión expirada.', { status: 401 })
  }

  if (response.status === 204) return null

  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError(data.error, { status: response.status, fields: data.fields })
  }

  return data
}

export const apiClient = {
  get: (path, params, opts) => request(path, { ...opts, method: 'GET', params }),
  post: (path, body, opts) => request(path, { ...opts, method: 'POST', body }),
  patch: (path, body, opts) => request(path, { ...opts, method: 'PATCH', body }),
  delete: (path, opts) => request(path, { ...opts, method: 'DELETE' }),
}
