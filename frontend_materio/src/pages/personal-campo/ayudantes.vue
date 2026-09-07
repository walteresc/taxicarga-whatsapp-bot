<script setup>
import CrudResourcePage from '@/components/crud/CrudResourcePage.vue'
import { assistantsService } from '@/services/personnelService'

const columns = [
  { key: 'name', label: 'Nombre' },
  { key: 'documentId', label: 'Documento' },
  { key: 'phone', label: 'Teléfono' },
]

const fields = [
  { key: 'name', label: 'Nombre completo', type: 'text', required: true, cols: 12 },
  { key: 'documentId', label: 'Documento (DNI)', type: 'text', required: true, cols: 6 },
  { key: 'phone', label: 'Teléfono', type: 'text', required: true, cols: 6 },
  { key: 'active', label: 'Activo', type: 'switch', cols: 6 },
  { key: 'notes', label: 'Observaciones', type: 'textarea', cols: 12 },
]
</script>

<template>
  <CrudResourcePage
    title="Ayudantes"
    subtitle="Personal de campo de apoyo en carga y descarga"
    singular="ayudante"
    :service="assistantsService"
    :columns="columns"
    :fields="fields"
    search-label="Buscar por nombre, documento o teléfono"
    label-field="name"
  />
</template>
