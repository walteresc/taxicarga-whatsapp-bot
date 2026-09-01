const BASE_URL = '/dashboard/campo/api/personal'

const getCookie = name => document.cookie
  .split('; ')
  .find(row => row.startsWith(`${name}=`))
  ?.split('=')
  .slice(1)
  .join('=') || ''

const request = async (url, options = {}) => {
  const response = await fetch(url, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
      ...(options.method && options.method !== 'GET'
        ? { 'X-CSRFToken': decodeURIComponent(getCookie('csrftoken')) }
        : {}),
      ...options.headers,
    },
    ...options,
  })

  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(data.error || 'No se pudo completar la operación.')

    error.status = response.status
    error.errors = data.errors || {}
    throw error
  }
  
  return data
}

const resource = type => ({
  list(params = {}) {
    const query = new URLSearchParams()

    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') query.set(key, value)
    })
    
    return request(`${BASE_URL}/${type}/?${query}`)
  },
  create(payload) {
    return request(`${BASE_URL}/${type}/`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  update(id, payload) {
    return request(`${BASE_URL}/${type}/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    })
  },
})

export const conductoresService = resource('conductores')
export const ayudantesService = resource('ayudantes')
