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
const DESPACHO = ['Administrador', 'Gerencia', 'Supervisor', 'Despacho']
const DESPACHO_MARGEN = ['Administrador', 'Gerencia', 'Supervisor', 'Despacho', 'Finanzas']
const SISTEMA = ['Administrador', 'Admin de sistema']
// Herramientas de despacho/operación del día a día que el asesor también
// consulta (reservas que él cerró, negociaciones, rutas). No es lo mismo que
// DESPACHO_MARGEN (que además ve plata/margen).
const DESPACHO_ASESOR = [...DESPACHO, 'Asesor de Ventas']

// Menú declarativo.
//  - `to`        : ruta (VerticalNavLink)
//  - `children`  : grupo colapsable (VerticalNavGroup)
//  - `roles`     : si falta, visible para cualquier autenticado. En un
//                  `heading` es solo documentación (qué roles son "el dueño"
//                  típico de la sección) — NO se usa para ocultarla: la
//                  sección se oculta sola si ninguno de sus items queda
//                  visible. Ponerle roles más angostos que a sus hijos rompía
//                  el agrupamiento (un hijo visible pero de sección oculta
//                  terminaba metido en la sección anterior).
//  - `soon: true`: ítem planificado, sin construir → se muestra gris, va a "Próximamente"
//  - `badge`     : clave de pipeline.counts.unseen (el número solo si > 0)
const MENU = [
  { heading: 'Atención' },
  // Solo quien de verdad trabaja la conversación con el cliente/transportista.
  { title: 'Bandeja de entrada', icon: 'ri-inbox-line', to: '/atencion/bandeja-entrada', roles: [...OPS, 'Despacho'] },

  { heading: 'Comercial', roles: OPS },
  { title: 'Oportunidades', icon: 'ri-user-star-line', to: '/comercial/potenciales', roles: OPS, badge: 'potentials' },
  { title: 'Estancados', icon: 'ri-error-warning-line', to: '/comercial/para-revision', roles: OPS, badge: 'review' },
  { title: 'Por cotizar', icon: 'ri-price-tag-3-line', to: '/comercial/por-cotizar', roles: OPS, badge: 'quoting' },
  { title: 'Cotizados', icon: 'ri-file-text-line', to: '/comercial/cotizaciones', roles: OPS, badge: 'quotes' },
  { title: 'Perdidos', icon: 'ri-close-circle-line', to: '/comercial/perdidos', roles: OPS },
  { title: 'Clientes', icon: 'ri-group-line', to: '/comercial/clientes', roles: OPS },

  { heading: 'Operaciones', roles: DESPACHO_ASESOR },
  { title: 'Reservas', icon: 'ri-calendar-check-line', to: '/operaciones/reservas', roles: DESPACHO_ASESOR, badge: 'bookings' },
  { title: 'Programación', icon: 'ri-calendar-todo-line', to: '/operaciones/programacion', roles: DESPACHO_ASESOR },
  { title: 'Pizarra', icon: 'ri-layout-grid-line', to: '/operaciones/pizarra', roles: DESPACHO_ASESOR },

  { heading: 'Mi equipo', roles: DESPACHO_ASESOR },
  {
    title: 'Planilla', icon: 'ri-team-line', roles: DESPACHO_ASESOR, children: [
      { title: 'Personal', icon: 'ri-id-card-line', to: '/mi-equipo/personal' },
      { title: 'Asistencia', icon: 'ri-time-line', to: '/mi-equipo/horas-extras' },
      { title: 'Compensaciones', icon: 'ri-hand-coin-line', to: '/mi-equipo/compensaciones' },
      { title: 'Pagos', icon: 'ri-bank-card-line', to: '/mi-equipo/pagos' },
    ],
  },
  {
    title: 'Mi flota', icon: 'ri-truck-line', roles: DESPACHO_ASESOR, children: [
      { title: 'Vehículos', icon: 'ri-truck-line', to: '/flota/vehiculos' },
      { title: 'Mantenimientos', icon: 'ri-tools-line', to: '/flota/mantenimientos' },
    ],
  },

  { heading: 'Encomiendas', roles: DESPACHO_ASESOR },
  { title: 'Envíos', icon: 'ri-e-bike-2-line', to: '/encomiendas', roles: DESPACHO_ASESOR },
  { title: 'Rutas de reparto', icon: 'ri-route-line', to: '/encomiendas/rutas', roles: DESPACHO },

  { heading: 'Tercerización', roles: DESPACHO_ASESOR },
  { title: 'Transportistas', icon: 'ri-team-line', to: '/transportistas/afiliados', roles: DESPACHO_ASESOR },
  { title: 'Vehículos afiliados', icon: 'ri-truck-line', to: '/transportistas/vehiculos', roles: DESPACHO_ASESOR },
  { title: 'Publicaciones', icon: 'ri-megaphone-line', to: '/tercerizacion/publicaciones', roles: DESPACHO },
  { title: 'Negociaciones', icon: 'ri-discuss-line', to: '/tercerizacion/negociaciones', roles: DESPACHO_ASESOR },
  { title: 'Asignaciones', icon: 'ri-user-shared-line', to: '/tercerizacion/asignaciones', roles: DESPACHO_ASESOR, soon: true },

  { heading: 'Finanzas', roles: DESPACHO_MARGEN },
  { title: 'Liquidaciones', icon: 'ri-wallet-3-line', to: '/finanzas/liquidaciones', roles: DESPACHO_MARGEN },
  { title: 'Contra-entrega (COD)', icon: 'ri-hand-coin-line', to: '/finanzas/cod', roles: DESPACHO_MARGEN },

  { heading: 'Analítica', roles: DESPACHO_MARGEN },
  { title: 'Ventas vivas', icon: 'ri-line-chart-line', to: '/analitica/ventas', roles: DESPACHO_MARGEN },
  { title: 'Histórico', icon: 'ri-bar-chart-box-line', to: '/analitica/benchmark', roles: DESPACHO_MARGEN },
  { title: 'Propio vs Tercerizado', icon: 'ri-scales-3-line', to: '/analitica/tercerizacion', roles: DESPACHO_MARGEN },

  { heading: 'Configuración', roles: [...ADMIN_SUP, 'Admin de sistema', 'Gerencia', 'Finanzas'] },
  { title: 'BOT', icon: 'ri-robot-line', to: '/configuracion/bot', roles: [...ADMIN_SUP, 'Admin de sistema'] },
  {
    title: 'Operaciones', icon: 'ri-settings-3-line', roles: ADMIN_SUP, children: [
      { title: 'Catálogo de vehículos', icon: 'ri-list-settings-line', to: '/configuracion/catalogo-vehiculos', roles: ADMIN_SUP },
    ],
  },
  { title: 'Comisiones de tercerización', icon: 'ri-percent-line', to: '/configuracion/comisiones', roles: ['Administrador', 'Gerencia', 'Finanzas'] },
  { title: 'Socios (API de envíos)', icon: 'ri-plug-line', to: '/configuracion/socios', roles: ['Administrador', 'Gerencia'] },
  { title: 'Usuarios y permisos', icon: 'ri-shield-user-line', to: '/configuracion/usuarios', roles: SISTEMA },
]

// En un heading, `roles` es solo documentación (ver comentario arriba) — no
// gatea nada; por eso acá se ignora a propósito.
const visibleFor = item => {
  if (item.heading) return true
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
