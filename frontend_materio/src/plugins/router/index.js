import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/authStore'
import { routes } from './routes'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// Guardia de sesión y rol.
// - Sin sesión -> /login?next=  (salvo rutas públicas).
// - Con sesión en ruta pública -> a la bandeja.
// - meta.roles y el usuario no lo tiene -> /forbidden.
router.beforeEach(async to => {
  const auth = useAuthStore()
  await auth.ensureLoaded()

  const isPublic = to.meta?.public === true

  if (!auth.isAuthenticated)
    return isPublic ? true : { path: '/login', query: { next: to.fullPath } }

  if (isPublic)
    return { path: '/atencion/bandeja-entrada' }

  const required = to.meta?.roles
  if (required?.length && !auth.hasAnyRole(...required))
    return { path: '/forbidden' }

  return true
})

export default function (app) {
  app.use(router)
}
export { router }
