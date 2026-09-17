<script setup>
// Ícono a medida "camión + silueta de la carrocería" para cada tipo del
// catálogo (apps/catalogo::TipoCarroceria) — Remix Icon (la librería que
// usa el resto de la app) no tiene variantes de camión por carrocería,
// solo un ícono genérico ("ri-truck-line"), que no dice nada sobre si es
// furgón cerrado, cisterna, volquete, grúa, etc. Todos comparten la misma
// cabina + ruedas; solo cambia la forma de la caja/plataforma trasera.
defineProps({
  code: { type: String, default: '' },
  size: { type: [Number, String], default: 18 },
})
</script>

<template>
  <svg
    :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"
  >
    <!-- Base compartida: cabina + parabrisas + ruedas + línea de chasis -->
    <rect x="1.5" y="10.5" width="5.5" height="6.5" rx="0.6" />
    <line x1="1.8" y1="13" x2="6.8" y2="13" stroke-width="1" />
    <circle cx="5.5" cy="19" r="1.6" />
    <circle cx="18" cy="19" r="1.6" />
    <line x1="7.3" y1="17" x2="22" y2="17" />

    <!-- Furgón cerrado: caja sólida cerrada -->
    <rect v-if="code === 'furgon_cerrado'" x="7.5" y="6.5" width="14" height="10.5" />

    <!-- Furgón frigorífico: caja cerrada + copo de nieve -->
    <template v-else-if="code === 'furgon_frigorifico'">
      <rect x="7.5" y="6.5" width="14" height="10.5" />
      <line x1="14.5" y1="9.5" x2="14.5" y2="13.5" stroke-width="1" />
      <line x1="12.7" y1="10" x2="16.3" y2="13" stroke-width="1" />
      <line x1="12.7" y1="13" x2="16.3" y2="10" stroke-width="1" />
    </template>

    <!-- Furgón isotérmico: caja cerrada de doble pared -->
    <template v-else-if="code === 'furgon_isotermico'">
      <rect x="7.5" y="6.5" width="14" height="10.5" />
      <rect x="8.9" y="7.9" width="11.2" height="7.7" stroke-width="1" />
    </template>

    <!-- Plataforma: chasis desnudo con un bulto suelto encima -->
    <rect v-else-if="code === 'plataforma'" x="11" y="12.5" width="6" height="4.5" />

    <!-- Plataforma portacontenedor: caja con nervaduras de contenedor -->
    <template v-else-if="code === 'plataforma_portacontenedor'">
      <rect x="8" y="9" width="13" height="8" />
      <line x1="11" y1="9" x2="11" y2="17" stroke-width="1" />
      <line x1="14.5" y1="9" x2="14.5" y2="17" stroke-width="1" />
      <line x1="18" y1="9" x2="18" y2="17" stroke-width="1" />
    </template>

    <!-- Rebatible: paneles laterales sueltos (abatibles) -->
    <template v-else-if="code === 'rebatible'">
      <line x1="8.5" y1="17" x2="8.5" y2="12.5" />
      <line x1="12.3" y1="17" x2="12.3" y2="12" />
      <line x1="16.1" y1="17" x2="16.1" y2="12.5" />
      <line x1="20" y1="17" x2="20" y2="12" />
    </template>

    <!-- Baranda / Tolva: barandas verticales, sin techo -->
    <template v-else-if="code === 'baranda_tolva'">
      <path d="M7.5 17 V12.5 H21.5 V17" />
      <line x1="11" y1="12.5" x2="11" y2="17" stroke-width="1" />
      <line x1="14.5" y1="12.5" x2="14.5" y2="17" stroke-width="1" />
      <line x1="18" y1="12.5" x2="18" y2="17" stroke-width="1" />
    </template>

    <!-- Baranda / Jaula: caja abierta con malla en cruz -->
    <template v-else-if="code === 'baranda_jaula'">
      <path d="M7.5 17 V9.5 H21.5 V17" />
      <line x1="7.5" y1="9.5" x2="21.5" y2="17" stroke-width="1" />
      <line x1="21.5" y1="9.5" x2="7.5" y2="17" stroke-width="1" />
    </template>

    <!-- Grúa telescópica: plataforma baja + brazo con gancho -->
    <template v-else-if="code === 'grua_telescopica'">
      <path d="M7.5 17 V13.5 H15 V17" />
      <line x1="11" y1="13.5" x2="20.5" y2="5" />
      <circle cx="21" cy="4.3" r="0.9" />
    </template>

    <!-- Cisterna / Tanque: cápsula horizontal -->
    <rect v-else-if="code === 'cisterna_tanque'" x="8" y="9" width="13" height="7" rx="3.5" />

    <!-- Volquete: caja con el borde trasero elevado (tolva basculante) -->
    <path v-else-if="code === 'volquete'" d="M7.5 17 V12 L14 9.5 H21.5 V17 Z" />

    <!-- Cama baja: plataforma muy pegada al piso, eje triple -->
    <template v-else-if="code === 'cama_baja'">
      <line x1="7.5" y1="16" x2="21.5" y2="16" />
      <circle cx="10.5" cy="19" r="1.2" />
      <circle cx="14" cy="19" r="1.2" />
    </template>

    <!-- Cama cuna: plataforma con hueco central hundido -->
    <path v-else-if="code === 'cama_cuna'" d="M7.5 13 H11 L13.5 16.5 H16.5 L19 13 H21.5" />

    <!-- Pickup: platón bajo y corto -->
    <path v-else-if="code === 'pickup'" d="M7.5 17 V14 H15 V17" />

    <!-- Fallback genérico: caja simple -->
    <rect v-else x="7.5" y="8" width="14" height="9" />
  </svg>
</template>
