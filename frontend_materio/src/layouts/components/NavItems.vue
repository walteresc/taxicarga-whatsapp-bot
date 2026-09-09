<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'

import VerticalNavGroup from '@layouts/components/VerticalNavGroup.vue'
import VerticalNavLink from '@layouts/components/VerticalNavLink.vue'
import VerticalNavSectionTitle from '@/@layouts/components/VerticalNavSectionTitle.vue'
import { useAuthStore } from '@/stores/authStore'
import { usePipelineStore } from '@/stores/pipelineStore'

const auth = useAuthStore()
const pipeline = usePipelineStore()
const route = useRoute()

onMounted(() => pipeline.start())
onUnmounted(() => pipeline.stop())

const OPS = ['Administrador', 'Supervisor', 'Asesor de Ventas']
const ADMIN_SUP = ['Administrador', 'Supervisor']
const ADMIN = ['Administrador']

// Menú declarativo.
//  - `to`        : ruta (VerticalNavLink)
//  - `children`  : grupo colapsable (VerticalNavGroup)
//  - `roles`     : si falta, visible para cualquier autenticado
//  - `soon: true`: ítem planificado, sin construir → se muestra gris, va a "Próximamente"
//  - `badge`     : clave de pipeline.counts.unseen (el número solo si > 0)
const MENU = [
  { heading: 'Atención' },
  { title: 'Bandeja de entrada', icon: 'ri-inbox-line', to: '/atencion/bandeja-entrada' },

  { heading: 'Comercial', roles: OPS },
  { title: 'Oportunidades', icon: 'ri-user-star-line', to: '/comercial/potenciales', roles: OPS, badge: 'potentials' },
  { title: 'Estancados', icon: 'ri-error-warning-line', to: '/comercial/para-revision', roles: OPS, badge: 'review' },
  { title: 'Por cotizar', icon: 'ri-price-tag-3-line', to: '/comercial/por-cotizar', roles: OPS, badge: 'quoting' },
  { title: 'Cotizados', icon: 'ri-file-text-line', to: '/comercial/cotizaciones', roles: OPS, badge: 'quotes' },
  { title: 'Perdidos', icon: 'ri-close-circle-line', to: '/comercial/perdidos', roles: OPS },
  { title: 'Clientes', icon: 'ri-group-line', to: '/comercial/clientes', roles: OPS },

  { heading: 'Operaciones', roles: OPS },
  { title: 'Reservas', icon: 'ri-calendar-check-line', to: '/operaciones/reservas', roles: OPS, badge: 'bookings' },
  { title: 'Programación', icon: 'ri-calendar-todo-line', to: '/operaciones/programacion', roles: OPS },
  { title: 'Pizarra', icon: 'ri-layout-grid-line', to: '/operaciones/pizarra', roles: OPS },

  { heading: 'Mi equipo', roles: OPS },
  {
    title: 'Planilla', icon: 'ri-team-line', roles: OPS, children: [
      { title: 'Personal', icon: 'ri-id-card-line', to: '/mi-equipo/personal' },
      { title: 'Asistencia', icon: 'ri-time-line', to: '/mi-equipo/horas-extras' },
      { title: 'Compensaciones', icon: 'ri-hand-coin-line', to: '/mi-equipo/compensaciones' },
      { title: 'Pagos', icon: 'ri-bank-card-line', to: '/mi-equipo/pagos' },
    ],
  },
  {
    title: 'Mi flota', icon: 'ri-truck-line', roles: OPS, children: [
      { title: 'Vehículos', icon: 'ri-truck-line', to: '/flota/vehiculos' },
      { title: 'Mantenimientos', icon: 'ri-tools-line', to: '/flota/mantenimientos' },
    ],
  },

  { heading: 'Tercerización', roles: OPS },
  { title: 'Transportistas', icon: 'ri-team-line', to: '/transportistas/afiliados', roles: OPS },
  { title: 'Vehículos afiliados', icon: 'ri-truck-line', to: '/transportistas/vehiculos', roles: OPS },
  { title: 'Publicaciones', icon: 'ri-megaphone-line', to: '/tercerizacion/publicaciones', roles: OPS, soon: true },
  { title: 'Negociaciones', icon: 'ri-discuss-line', to: '/tercerizacion/negociaciones', roles: OPS },
  { title: 'Asignaciones', icon: 'ri-user-shared-line', to: '/tercerizacion/asignaciones', roles: OPS, soon: true },

  { heading: 'Analítica', roles: ADMIN_SUP },
  { title: 'Ventas vivas', icon: 'ri-line-chart-line', to: '/analitica/ventas', roles: ADMIN_SUP },
  { title: 'Histórico', icon: 'ri-bar-chart-box-line', to: '/analitica/benchmark', roles: ADMIN_SUP },

  { heading: 'Configuración', roles: ADMIN_SUP },
  { title: 'BOT', icon: 'ri-robot-line', to: '/configuracion/bot', roles: ADMIN_SUP },
  {
    title: 'Operaciones', icon: 'ri-settings-3-line', roles: ADMIN_SUP, children: [
      { title: 'Catálogo de vehículos', icon: 'ri-list-settings-line', to: '/configuracion/catalogo-vehiculos', roles: ADMIN_SUP },
      { title: 'Precios y comisiones', icon: 'ri-percent-line', to: '/configuracion/precios-comisiones', roles: ADMIN_SUP, soon: true },
    ],
  },
  { title: 'Usuarios y permisos', icon: 'ri-shield-user-line', to: '/configuracion/usuarios', roles: ADMIN, soon: true },
]

const visibleFor = item => {
  if (!item.roles?.length) return true
  return auth.hasAnyRole(...item.roles)
}

const navItem = link => {
  // Ítem "próximamente": sin ruta (inerte) + gris.
  const item = link.soon
    ? { title: `${link.title}`, icon: link.icon, disable: true }
    : { title: link.title, icon: link.icon, to: link.to }
  const n = link.badge ? (pipeline.counts.unseen?.[link.badge] ?? 0) : 0
  if (n > 0) {
    item.badgeContent = n
    item.badgeClass = link.badge === 'review' ? 'bg-error' : 'bg-primary'
  }

  return item
}

const items = computed(() => {
  const out = []
  MENU.forEach(entry => {
    if (entry.heading) {
      if (visibleFor(entry)) out.push({ type: 'heading', heading: entry.heading, _links: [] })

      return
    }
    const last = out[out.length - 1]
    if (!last?._links) return

    if (entry.children) {
      const kids = entry.children.filter(visibleFor)
      if (kids.length) {
        last._links.push({
          type: 'group',
          key: entry.title,
          nav: { title: entry.title, icon: entry.icon },
          children: kids,
          defaultOpen: kids.some(k => route.path.startsWith(k.to)),
        })
      }

      return
    }
    if (visibleFor(entry)) last._links.push({ type: 'link', key: entry.to, link: entry })
  })

  return out.filter(entry => entry._links.length)
})

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
    <template v-for="row in section._links" :key="row.key">
      <VerticalNavGroup
        v-if="row.type === 'group'"
        :item="{ ...row.nav, defaultOpen: row.defaultOpen }"
      >
        <VerticalNavLink
          v-for="child in row.children"
          :key="child.to"
          :item="navItem(child)"
        />
      </VerticalNavGroup>
      <VerticalNavLink
        v-else
        :item="navItem(row.link)"
        @click="handleNavClick(row.link)"
      />
    </template>
  </template>
</template>
