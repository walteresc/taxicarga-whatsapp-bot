<script setup>
import VerticalNavSectionTitle from '@/@layouts/components/VerticalNavSectionTitle.vue'
import VerticalNavGroup from '@layouts/components/VerticalNavGroup.vue'
import VerticalNavLink from '@layouts/components/VerticalNavLink.vue'
</script>

<template>
  <!-- 👉 PRINCIPAL -->
  <VerticalNavLink
    :item="{
      title: 'Dashboard',
      icon: 'ri-home-smile-line',
      to: '/dashboard',
    }"
  />

  <!-- 👉 ATENCIÓN -->
  <VerticalNavSectionTitle
    :item="{
      heading: 'ATENCIÓN',
    }"
  />
  <VerticalNavLink
    :item="{
      title: 'Bandeja de entrada',
      icon: 'ri-inbox-line',
      to: '/atencion/bandeja-entrada',
      badge: { content: 18, color: 'error' },
    }"
  />

  <VerticalNavLink
    :item="{
      title: 'Leads',
      icon: 'ri-user-add-line',
      to: '/atencion/leads',
      badge: { content: 7, color: 'warning' },
    }"
  />

  <!-- 👉 COMERCIAL -->
  <VerticalNavSectionTitle
    :item="{
      heading: 'COMERCIAL',
    }"
  />
  <VerticalNavGroup
    :item="{
      title: 'Por Cotizar',
      icon: 'ri-file-list-line',
    }"
  >
    <VerticalNavLink
      :item="{
        title: 'Lista',
        to: '/comercial/por-cotizar',
      }"
    />
  </VerticalNavGroup>

  <VerticalNavGroup
    :item="{
      title: 'Cotizaciones',
      icon: 'ri-file-text-line',
    }"
  >
    <VerticalNavLink
      :item="{
        title: 'Historial',
        to: '/comercial/cotizaciones',
      }"
    />
  </VerticalNavGroup>

  <VerticalNavLink
    :item="{
      title: 'Clientes',
      icon: 'ri-user-line',
      to: '/comercial/clientes',
    }"
  />

  <VerticalNavLink
    :item="{
      title: 'Reservas',
      icon: 'ri-calendar-check-line',
      to: '/comercial/reservas',
    }"
  />

  <!-- 👉 OPERACIONES -->
  <VerticalNavSectionTitle
    :item="{
      heading: 'OPERACIONES',
    }"
  />
  <VerticalNavGroup
    :item="{
      title: 'Pizarra',
      icon: 'ri-layout-grid-line',
    }"
  >
    <VerticalNavLink
      :item="{
        title: 'Programación Visual',
        to: '/operaciones/pizarra',
      }"
    />
  </VerticalNavGroup>

  <VerticalNavLink
    :item="{
      title: 'Programación',
      icon: 'ri-calendar-line',
      to: '/operaciones/programacion',
    }"
  />

  <VerticalNavLink
    :item="{
      title: 'Servicios',
      icon: 'ri-service-line',
      to: '/operaciones/servicios',
    }"
  />

  <!-- 👉 PERSONAL DE CAMPO -->
  <VerticalNavSectionTitle
    :item="{
      heading: 'PERSONAL DE CAMPO',
    }"
  />
  <VerticalNavGroup
    :item="{
      title: 'Personal',
      icon: 'ri-team-line',
    }"
  >
    <VerticalNavLink
      :item="{
        title: 'Conductores',
        to: '/personal-campo/conductores',
      }"
    />
    <VerticalNavLink
      :item="{
        title: 'Ayudantes',
        to: '/personal-campo/ayudantes',
      }"
    />
  </VerticalNavGroup>

  <VerticalNavLink
    :item="{
      title: 'Equipos',
      icon: 'ri-group-line',
      to: '/personal-campo/equipos',
    }"
  />

  <!-- 👉 FLOTA -->
  <VerticalNavSectionTitle
    :item="{
      heading: 'FLOTA',
    }"
  />
  <VerticalNavGroup
    :item="{
      title: 'Vehículos',
      icon: 'ri-truck-line',
    }"
  >
    <VerticalNavLink
      :item="{
        title: 'Inventario',
        to: '/flota/vehiculos',
      }"
    />
  </VerticalNavGroup>

  <VerticalNavLink
    :item="{
      title: 'Mantenimientos',
      icon: 'ri-tools-line',
      to: '/flota/mantenimientos',
    }"
  />

  <!-- 👉 AUTOMATIZACIÓN -->
  <VerticalNavSectionTitle
    :item="{
      heading: 'AUTOMATIZACIÓN',
    }"
  />
  <VerticalNavGroup
    :item="{
      title: 'Bot WhatsApp',
      icon: 'ri-robot-line',
    }"
  >
    <VerticalNavLink
      :item="{
        title: 'Bots',
        to: '/automatizacion/bots',
      }"
    />
    <VerticalNavLink
      :item="{
        title: 'Flujos',
        to: '/automatizacion/flujos',
      }"
    />
    <VerticalNavLink
      :item="{
        title: 'Respuestas',
        to: '/automatizacion/respuestas',
      }"
    />
    <VerticalNavLink
      :item="{
        title: 'Canales',
        to: '/automatizacion/canales',
      }"
    />
  </VerticalNavGroup>

  <!-- 👉 ANALÍTICA -->
  <VerticalNavSectionTitle
    :item="{
      heading: 'ANALÍTICA',
    }"
  />
  <VerticalNavGroup
    :item="{
      title: 'Reportes',
      icon: 'ri-bar-chart-line',
    }"
  >
    <VerticalNavLink
      :item="{
        title: 'Reportes',
        to: '/analitica/reportes',
      }"
    />
    <VerticalNavLink
      :item="{
        title: 'Rendimiento',
        to: '/analitica/rendimiento',
      }"
    />
  </VerticalNavGroup>

  <!-- 👉 SISTEMA -->
  <VerticalNavSectionTitle
    :item="{
      heading: 'SISTEMA',
    }"
  />
  <VerticalNavGroup
    :item="{
      title: 'Administración',
      icon: 'ri-settings-line',
    }"
  >
    <VerticalNavLink
      :item="{
        title: 'Usuarios',
        to: '/sistema/usuarios',
      }"
    />
    <VerticalNavLink
      :item="{
        title: 'Integraciones',
        to: '/sistema/integraciones',
      }"
    />
    <VerticalNavLink
      :item="{
        title: 'Configuración',
        to: '/sistema/config',
      }"
    />
  </VerticalNavGroup>
</template>
