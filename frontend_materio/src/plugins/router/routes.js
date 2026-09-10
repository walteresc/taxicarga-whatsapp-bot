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

      // MI EQUIPO
      {
        path: 'mi-equipo/personal',
        component: () => import('@/pages/mi-equipo/personal/index.vue'),
        meta: { roles: PERSONAL_ROLES },
      },
      {
        path: 'mi-equipo/horas-extras',
        component: () => import('@/pages/mi-equipo/horas-extras/index.vue'),
        meta: { roles: PERSONAL_ROLES },
      },
      {
        path: 'mi-equipo/compensaciones',
        component: () => import('@/pages/mi-equipo/compensaciones/index.vue'),
        meta: { roles: PERSONAL_ROLES },
      },
      {
        path: 'mi-equipo/pagos',
        component: () => import('@/pages/mi-equipo/pagos/index.vue'),
        meta: { roles: PERSONAL_ROLES },
      },
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

      // TRANSPORTISTAS
      {
        path: 'transportistas/afiliados',
        component: () => import('@/pages/campo/transportistas/afiliados/index.vue'),
        meta: { roles: PERSONAL_ROLES },
      },
      {
        path: 'transportistas/vehiculos',
        component: () => import('@/pages/campo/transportistas/vehiculos/index.vue'),
        meta: { roles: PERSONAL_ROLES },
      },
      { path: 'campo/transportistas/afiliados', redirect: '/transportistas/afiliados' },
      { path: 'campo/transportistas/vehiculos', redirect: '/transportistas/vehiculos' },
      {
        path: 'tercerizacion/negociaciones',
        component: () => import('@/pages/tercerizacion/negociaciones/index.vue'),
        meta: { roles: OPERATIONS_ROLES },
      },
      {
        path: 'tercerizacion/publicaciones',
        component: () => import('@/pages/tercerizacion/publicaciones/index.vue'),
        meta: { roles: OPERATIONS_ROLES },
      },

      // CONFIGURACIÓN
      {
        path: 'configuracion/catalogo-vehiculos',
        component: () => import('@/pages/configuracion/catalogo-vehiculos/index.vue'),
        meta: { roles: ['Administrador', 'Supervisor'] },
      },
      {
        path: 'configuracion/bot',
        component: () => import('@/pages/sistema/bot.vue'),
        meta: { roles: ['Administrador', 'Supervisor'] },
      },
      { path: 'sistema/bot', redirect: '/configuracion/bot' },
      {
        path: 'configuracion/usuarios',
        component: () => import('@/pages/configuracion/usuarios/index.vue'),
        meta: { roles: ['Administrador', 'Admin de sistema'] },
      },
      {
        path: 'configuracion/comisiones',
        component: () => import('@/pages/configuracion/comisiones/index.vue'),
        meta: { roles: ['Administrador', 'Gerencia', 'Finanzas'] },
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
      { path: 'comercial/reservas', redirect: '/operaciones/reservas' },
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

      // OPERACIONES
      {
        path: 'operaciones/reservas',
        component: () => import('@/pages/comercial/reservas/index.vue'),
        meta: { roles: OPERATIONS_ROLES },
      },
      {
        path: 'operaciones/programacion',
        component: () => import('@/pages/operaciones/programacion/index.vue'),
        meta: { roles: OPERATIONS_ROLES },
      },
      {
        path: 'operaciones/pizarra',
        component: () => import('@/pages/operaciones/pizarra/index.vue'),
        meta: { roles: OPERATIONS_ROLES },
      },

      // FLOTA (Mi flota)
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
      {
        path: 'analitica/tercerizacion',
        component: () => import('@/pages/analitica/tercerizacion.vue'),
        meta: { roles: ['Administrador', 'Gerencia', 'Supervisor', 'Despacho', 'Finanzas'] },
      },
      {
        path: 'finanzas/liquidaciones',
        component: () => import('@/pages/finanzas/liquidaciones/index.vue'),
        meta: { roles: ['Administrador', 'Gerencia', 'Finanzas', 'Despacho'] },
      },

      {
        path: 'forbidden',
        component: () => import('@/pages/forbidden.vue'),
      },
    ],
  },
  {
    path: '/portal',
    component: () => import('@/layouts/portal.vue'),
    children: [
      { path: '', redirect: '/portal/cargas' },
      { path: 'cargas', component: () => import('@/pages/portal/cargas/index.vue'), meta: { portal: 'carrier' } },
      { path: 'ofertas', component: () => import('@/pages/portal/ofertas/index.vue'), meta: { portal: 'carrier' } },
      { path: 'asignaciones', component: () => import('@/pages/portal/asignaciones/index.vue'), meta: { portal: 'carrier' } },
      { path: 'cobros', component: () => import('@/pages/portal/cobros/index.vue'), meta: { portal: 'carrier' } },
      { path: 'negociaciones', component: () => import('@/pages/portal/negociaciones/index.vue'), meta: { portal: 'carrier' } },

      { path: 'cliente', redirect: '/portal/cliente/mis-cargas' },
      { path: 'cliente/mis-cargas', component: () => import('@/pages/portal/cliente/mis-cargas/index.vue'), meta: { portal: 'customer' } },
      { path: 'cliente/publicar', component: () => import('@/pages/portal/cliente/publicar/index.vue'), meta: { portal: 'customer' } },
      { path: 'cliente/carga/:code', component: () => import('@/pages/portal/cliente/carga/index.vue'), meta: { portal: 'customer' } },
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
        path: 'cotizar',
        component: () => import('@/pages/cotizar.vue'),
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
