<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'

import VerticalNavLink from '@layouts/components/VerticalNavLink.vue'
import VerticalNavSectionTitle from '@/@layouts/components/VerticalNavSectionTitle.vue'
import { useAuthStore } from '@/stores/authStore'
import { usePipelineStore } from '@/stores/pipelineStore'

const auth = useAuthStore()
const pipeline = usePipelineStore()
const route = useRoute()

onMounted(() => pipeline.start())
onUnmounted(() => pipeline.stop())

const COMMERCIAL_ROLES = ['Administrador', 'Supervisor', 'Asesor de Ventas']

// Menú declarativo. `ready:false` = la sección aún vive solo en el panel Django.
// `badge` = clave de pipelineStore.counts; el número solo se muestra si es > 0.
const MENU = [
  { heading: 'Atención' },
  { title: 'Bandeja de entrada', icon: 'ri-inbox-line', to: '/atencion/bandeja-entrada', ready: true },
  { title: 'Leads', icon: 'ri-user-add-line', to: '/atencion/leads', ready: false },

  { heading: 'Comercial' },
  { title: 'Oportunidades', icon: 'ri-user-star-line', to: '/comercial/potenciales', ready: true, roles: COMMERCIAL_ROLES, badge: 'potentials' },
  { title: 'Para revisión', icon: 'ri-eye-line', to: '/comercial/para-revision', ready: true, roles: COMMERCIAL_ROLES, badge: 'review' },
  { title: 'Por cotizar', icon: 'ri-price-tag-3-line', to: '/comercial/por-cotizar', ready: true, roles: COMMERCIAL_ROLES, badge: 'quoting' },
  { title: 'Cotizaciones', icon: 'ri-file-text-line', to: '/comercial/cotizaciones', ready: true, roles: COMMERCIAL_ROLES, badge: 'quotes' },
  { title: 'Reservas', icon: 'ri-calendar-check-line', to: '/comercial/reservas', ready: true, roles: COMMERCIAL_ROLES, badge: 'bookings' },
  { title: 'Perdidos', icon: 'ri-close-circle-line', to: '/comercial/perdidos', ready: true, roles: COMMERCIAL_ROLES },
  { title: 'Clientes', icon: 'ri-user-line', to: '/comercial/clientes', ready: true, roles: COMMERCIAL_ROLES },

  { heading: 'Operaciones' },
  { title: 'Pizarra', icon: 'ri-layout-grid-line', to: '/operaciones/pizarra', ready: false },
  { title: 'Programación', icon: 'ri-calendar-line', to: '/operaciones/programacion', ready: false },

  { heading: 'Campo · Nuestro equipo' },
  { title: 'Conductores', icon: 'ri-steering-line', to: '/personal-campo/conductores', ready: true, roles: COMMERCIAL_ROLES },
  { title: 'Ayudantes', icon: 'ri-user-2-line', to: '/personal-campo/ayudantes', ready: true, roles: COMMERCIAL_ROLES },
  { title: 'Equipos', icon: 'ri-group-line', to: '/personal-campo/equipos', ready: false },

  { heading: 'Campo · Transportistas' },
  { title: 'Afiliados', icon: 'ri-team-line', to: '/campo/transportistas/afiliados', ready: true, roles: COMMERCIAL_ROLES },
  { title: 'Vehículos', icon: 'ri-truck-line', to: '/campo/transportistas/vehiculos', ready: true, roles: COMMERCIAL_ROLES },
  { title: 'Catálogo de vehículos', icon: 'ri-list-settings-line', to: '/configuracion/catalogo-vehiculos', ready: true, roles: ['Administrador', 'Supervisor'] },

  { heading: 'Flota' },
  { title: 'Vehículos', icon: 'ri-truck-line', to: '/flota/vehiculos', ready: true, roles: COMMERCIAL_ROLES },
  { title: 'Mantenimientos', icon: 'ri-tools-line', to: '/flota/mantenimientos', ready: true, roles: COMMERCIAL_ROLES },

  { heading: 'Analítica' },
  { title: 'Ventas vivas', icon: 'ri-line-chart-line', to: '/analitica/ventas', ready: true, roles: ['Administrador', 'Supervisor'] },
  { title: 'Benchmark histórico', icon: 'ri-bar-chart-box-line', to: '/analitica/benchmark', ready: true, roles: ['Administrador', 'Supervisor'] },

  { heading: 'Configuración' },
  { title: 'Catálogo de vehículos', icon: 'ri-list-settings-line', to: '/configuracion/catalogo-vehiculos', ready: true, roles: ['Administrador', 'Supervisor'] },

  { heading: 'Sistema' },
  { title: 'Configuración del bot', icon: 'ri-robot-line', to: '/sistema/bot', ready: true, roles: COMMERCIAL_ROLES },
  { title: 'Administración', icon: 'ri-settings-line', to: '/sistema/config', ready: false },
]

const visibleFor = item => {
  if (!item.ready) return false
  if (!item.roles?.length) return true
  return auth.hasAnyRole(...item.roles)
}

const items = computed(() => {
  const out = []
  MENU.forEach(entry => {
    if (entry.heading) {
      out.push({ ...entry, _links: [] })
    } else if (visibleFor(entry)) {
      const last = out[out.length - 1]
      if (last?.heading) last._links.push(entry)
    }
  })
  return out.filter(entry => entry._links.length)
})

const navItem = link => {
  const item = { title: link.title, icon: link.icon, to: link.to }
  const n = link.badge ? (pipeline.counts.unseen?.[link.badge] ?? 0) : 0
  if (n > 0) item.badge = { content: n, color: link.badge === 'review' ? 'error' : 'primary' }

  return item
}

// Clic en el link de la página en la que ya estás: Vue Router no re-navega
// (misma ruta), así que sin esto la bandeja queda atascada en el filtro/
// partición donde se haya quedado el usuario. La bandeja escucha este evento
// y vuelve a "Todas".
const handleNavClick = link => {
  if (link.to === '/atencion/bandeja-entrada' && route.path === link.to) {
    window.dispatchEvent(new Event('bandeja:reset-view'))
  }
}
</script>

<template>
  <template v-for="section in items" :key="section.heading">
    <VerticalNavSectionTitle :item="{ heading: section.heading }" />
    <VerticalNavLink
      v-for="link in section._links"
      :key="link.to"
      :item="navItem(link)"
      @click="handleNavClick(link)"
    />
  </template>
</template>
