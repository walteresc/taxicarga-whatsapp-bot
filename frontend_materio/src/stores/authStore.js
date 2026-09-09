// Sesión y roles del usuario. Fuente: /dashboard/api/auth/user/.
//
// El guard del router (plugins/router/index.js) llama a ensureLoaded() antes de
// cada navegación protegida. Los componentes usan hasRole()/hasAnyRole() para
// mostrar u ocultar acciones.

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const loaded = ref(false)
  let inFlight = null

  const isAuthenticated = computed(() => !!user.value)
  const roles = computed(() => user.value?.roles ?? [])

  const hasRole = role => roles.value.includes(role)
  const hasAnyRole = (...wanted) => wanted.some(r => roles.value.includes(r))

  // Portales externos (misma sesión, shell propio, sin acceso al CRM).
  const carrierId = computed(() => user.value?.carrierId ?? null)
  const isCarrier = computed(() => !!carrierId.value)
  const portalCustomerId = computed(() => user.value?.portalCustomerId ?? null)
  const isCustomer = computed(() => !!portalCustomerId.value)
  const isExternal = computed(() => isCarrier.value || isCustomer.value)

  const _fetchUser = async () => {
    try {
      const res = await fetch('/dashboard/api/auth/user/', {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'include',
      })
      user.value = res.ok ? (await res.json()).user : null
    } catch {
      user.value = null
    } finally {
      loaded.value = true
    }
  }

  // Carga la sesión una sola vez; llamadas concurrentes comparten la promesa.
  const ensureLoaded = () => {
    if (loaded.value) return Promise.resolve()
    if (!inFlight) inFlight = _fetchUser().finally(() => { inFlight = null })
    return inFlight
  }

  // Fuerza un refetch (tras login/logout): descarta cualquier fetch en curso.
  const reload = () => {
    loaded.value = false
    inFlight = null

    return ensureLoaded()
  }

  const clear = () => { user.value = null; loaded.value = true }

  return {
    user, loaded, isAuthenticated, roles, hasRole, hasAnyRole,
    carrierId, isCarrier, portalCustomerId, isCustomer, isExternal,
    ensureLoaded, reload, clear,
  }
})
