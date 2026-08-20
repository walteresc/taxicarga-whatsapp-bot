export const routes = [
  { path: '/', redirect: '/dashboard' },
  {
    path: '/',
    component: () => import('@/layouts/default.vue'),
    children: [
      // PRINCIPAL
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
    ],
  },
  {
    path: '/',
    component: () => import('@/layouts/blank.vue'),
    children: [
      {
        path: 'login',
        component: () => import('@/pages/login.vue'),
      },
      {
        path: 'register',
        component: () => import('@/pages/register.vue'),
      },
      {
        path: '/:pathMatch(.*)*',
        component: () => import('@/pages/[...error].vue'),
      },
    ],
  },
]
