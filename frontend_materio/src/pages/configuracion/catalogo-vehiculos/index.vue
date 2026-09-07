<script setup>
import { ref } from 'vue'

import CatalogTypeList from './CatalogTypeList.vue'
import CategoryTable from './CategoryTable.vue'
import CompatibilityList from './CompatibilityList.vue'
import { bodyTypesService, vehicleTypesService } from '@/services/catalogService'

const tab = ref('vehiculos')
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">
      Catálogo de vehículos
    </h1>
    <p class="text-body-1 text-medium-emphasis mb-6">
      Datos maestros de vehículos y carrocerías. Se usan al registrar vehículos de transportistas
      y en la derivación de cargas.
    </p>

    <VTabs v-model="tab" class="mb-6">
      <VTab value="vehiculos"><VIcon start icon="ri-truck-line" /> Tipos de vehículos</VTab>
      <VTab value="carrocerias"><VIcon start icon="ri-box-3-line" /> Tipos de carrocería</VTab>
      <VTab value="compatibilidades"><VIcon start icon="ri-links-line" /> Compatibilidades</VTab>
      <VTab value="categorizacion"><VIcon start icon="ri-scales-3-line" /> Categorización</VTab>
    </VTabs>

    <VWindow v-model="tab">
      <VWindowItem value="vehiculos">
        <CatalogTypeList :service="vehicleTypesService" singular="tipo de vehículo" create-label="Nuevo tipo" />
      </VWindowItem>
      <VWindowItem value="carrocerias">
        <CatalogTypeList :service="bodyTypesService" singular="tipo de carrocería" create-label="Nueva carrocería" />
      </VWindowItem>
      <VWindowItem value="compatibilidades">
        <CompatibilityList />
      </VWindowItem>
      <VWindowItem value="categorizacion">
        <CategoryTable />
      </VWindowItem>
    </VWindow>
  </section>
</template>
