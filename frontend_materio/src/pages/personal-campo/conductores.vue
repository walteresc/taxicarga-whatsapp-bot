<script setup>
import CrudResourcePage from '@/components/crud/CrudResourcePage.vue'
import { driversService, LICENSE_CATEGORIES } from '@/services/personnelService'

const columns = [
  { key: 'name', label: 'Nombre' },
  { key: 'documentId', label: 'Documento' },
  { key: 'phone', label: 'Teléfono' },
  {
    key: 'licenseNumber',
    label: 'Licencia',
    format: r => (r.licenseNumber ? `${r.licenseNumber}${r.licenseCategory ? ` · ${r.licenseCategory}` : ''}` : '—'),
  },
  {
    key: 'licenseExpiresOn',
    label: 'Vence',
    format: r => r.licenseExpiresOn || '—',
  },
]

const fields = [
  { key: 'name', label: 'Nombre completo', type: 'text', required: true, cols: 12 },
  { key: 'documentId', label: 'Documento (DNI)', type: 'text', required: true, cols: 6 },
  { key: 'phone', label: 'Teléfono', type: 'text', required: true, cols: 6 },
  { key: 'licenseNumber', label: 'N° de licencia', type: 'text', cols: 6 },
  { key: 'licenseCategory', label: 'Categoría', type: 'select', options: LICENSE_CATEGORIES, cols: 6 },
  { key: 'licenseExpiresOn', label: 'Vencimiento de licencia', type: 'date', cols: 6 },
  { key: 'active', label: 'Activo', type: 'switch', cols: 6 },
  { key: 'notes', label: 'Observaciones', type: 'textarea', cols: 12 },
]
</script>

<template>
  <CrudResourcePage
    title="Conductores"
    subtitle="Personal de campo con licencia de conducir"
    singular="conductor"
    :service="driversService"
    :columns="columns"
    :fields="fields"
    search-label="Buscar por nombre, documento, teléfono o licencia"
    label-field="name"
  />
</template>
