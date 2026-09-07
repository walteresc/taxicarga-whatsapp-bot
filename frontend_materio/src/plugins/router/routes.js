// Rutas del panel Vue.
//
// meta.public  -> accesible sin sesión (login / registro).
// meta.roles   -> lista de roles; si falta, basta con estar autenticado.
//                 Los nombres coinciden con los grupos del backend.
// El guard vive en plugins/router/index.js.

const OPERATIONS_ROLES = ['Administrador', 'Supervisor', 'Asesor de Ventas']
const PERSONAL_ROLES = OPERATIONS_ROLES
const ANALYTICS_ROLES = ['Administrador', 'Supervisor']

export const routes = [
  { path: '/', redirect: '/atencion/bandeja-entrada' },
  {
    path: '/',
    component: () => import('@/layouts/default.vue'),
    children: [
      {
        path: 'dashboard',
        component: () => import('@/pages/dashboard/index.vue'),
      },

      // ATENCIÓN
      {
        path: 'atencion/bandeja-entrada',
        component: () => import('@/pages/atencion/bandeja-entrada/index.vue'),
        meta: { hideFooter: true },
      },
      {
        path: 'atencion/leads',
        component: () => import('@/pages/atencion/leads/index.vue'),
      },

      // PERSONAL DE CAMPO
      {
        path: 'personal-campo/conductores',
        component: () => import('@/pages/personal-campo/conductores.vue'),
        meta: { roles: PERSONAL_ROLES },
      },
      {
        path: 'personal-campo/ayudantes',
        component: () => import('@/pages/personal-campo/ayudantes.vue'),
        meta: { roles: PERSONAL_ROLES },
      },
      {
        path: 'campo/transportistas/afiliados',
        component: () => import('@/pages/campo/transportistas/afiliados/index.vue'),
        meta: { roles: PERSONAL_ROLES },
      },
      {
        path: 'campo/transportistas/vehiculos',
        component: () => import('@/pages/campo/transportistas/vehiculos/index.vue'),
        meta: { roles: PERSONAL_ROLES },
      },

      // CONFIGURACIÓN
      {
        path: 'configuracion/catalogo-vehiculos',
        component: () => import('@/pages/configuracion/catalogo-vehiculos/index.vue'),
        meta: { roles: ['Administrador', 'Supervisor'] },
      },

      // COMERCIAL
      {
        path: 'comercial/potenciales',
        component: () => import('@/pages/comercial/potenciales/index.vue'),
        meta: { roles: OPERATIONS_ROLES },
      },
      {
        path: 'comercial/para-revision',
        component: () => import('@/pages/comercial/para-revision/index.vue'),
        meta: { roles: OPERATIONS_ROLES },
      },
      {
        path: 'comercial/por-cotizar',
        component: () => import('@/pages/comercial/por-cotizar/index.vue'),
        meta: { roles: OPERATIONS_ROLES },
      },
      {
        path: 'comercial/cotizaciones',
        component: () => import('@/pages/comercial/cotizaciones/index.vue'),
        meta: { roles: OPERATIONS_ROLES },
      },
      {
        path: 'comercial/reservas',
        component: () => import('@/pages/comercial/reservas/index.vue'),
        meta: { roles: OPERATIONS_ROLES },
      },
      {
        path: 'comercial/perdidos',
        component: () => import('@/pages/comercial/perdidos/index.vue'),
        meta: { roles: OPERATIONS_ROLES },
      },
      {
        path: 'comercial/clientes',
        component: () => import('@/pages/comercial/clientes/index.vue'),
        meta: { roles: OPERATIONS_ROLES },
      },

      // FLOTA
      {
        path: 'flota/vehiculos',
        component: () => import('@/pages/flota/vehiculos.vue'),
        meta: { roles: OPERATIONS_ROLES },
      },
      {
        path: 'flota/mantenimientos',
        component: () => import('@/pages/flota/mantenimientos.vue'),
        meta: { roles: OPERATIONS_ROLES },
      },

      // ANALÍTICA
      {
        path: 'analitica/ventas',
        component: () => import('@/pages/analitica/ventas.vue'),
        meta: { roles: ANALYTICS_ROLES },
      },
      {
        path: 'analitica/benchmark',
        component: () => import('@/pages/analitica/benchmark.vue'),
        meta: { roles: ANALYTICS_ROLES },
      },

      // SISTEMA
      {
        path: 'sistema/bot',
        component: () => import('@/pages/sistema/bot.vue'),
        meta: { roles: OPERATIONS_ROLES },
      },

      {
        path: 'forbidden',
        component: () => import('@/pages/forbidden.vue'),
      },
    ],
  },
  {
    path: '/',
    component: () => import('@/layouts/blank.vue'),
    children: [
      {
        path: 'login',
        component: () => import('@/pages/login.vue'),
        meta: { public: true },
      },
      {
        path: 'register',
        component: () => import('@/pages/register.vue'),
        meta: { public: true },
      },
      {
        path: '/:pathMatch(.*)*',
        component: () => import('@/pages/[...error].vue'),
      },
    ],
  },
]
