<script setup>
import CrudResourcePage from '@/components/crud/CrudResourcePage.vue'
import { customersService } from '@/services/customersService'

const SEGMENT = {
  empresa: { text: 'Empresa / PYME', color: 'primary' },
  frecuente: { text: 'Frecuente', color: 'success' },
  ocasional: { text: 'Ocasional', color: 'info' },
  inactivo: { text: 'Inactivo', color: 'secondary' },
  nuevo: { text: 'Nuevo', color: 'default' },
}

const segments = [
  { value: '', label: 'Todos' },
  { value: 'frecuente', label: 'Frecuentes' },
  { value: 'empresa', label: 'Empresas / PYMES' },
  { value: 'ocasional', label: 'Ocasionales' },
  { value: 'inactivo', label: 'Inactivos' },
]

const columns = [
  { key: 'name', label: 'Nombre', format: r => r.displayName || r.name || '—' },
  {
    key: 'phone',
    label: 'Contacto',
    format: r => (r.hasRealPhone ? r.contactId : `ID WhatsApp: ${r.contactId}`),
  },
  { key: 'segment', label: 'Segmento', chip: r => SEGMENT[r.segment] || SEGMENT.nuevo },
  { key: 'serviceCount', label: 'Servicios', align: 'end', format: r => r.serviceCount ?? 0 },
  { key: 'businessName', label: 'Razón social', format: r => r.businessName || '—' },
  { key: 'email', label: 'Correo', format: r => r.email || '—' },
]

const fields = [
  { key: 'name', label: 'Nombre', type: 'text', cols: 12 },
  { key: 'phone', label: 'Teléfono', type: 'text', required: true, cols: 6 },
  { key: 'documentId', label: 'Documento (DNI)', type: 'text', cols: 6 },
  { key: 'email', label: 'Correo', type: 'text', cols: 12 },
  { key: 'taxId', label: 'RUC', type: 'text', cols: 6 },
  { key: 'businessName', label: 'Razón social', type: 'text', cols: 6 },
  { key: 'active', label: 'Activo', type: 'switch', cols: 6 },
]
</script>

<template>
  <CrudResourcePage
    title="Clientes"
    subtitle="Base de contactos del CRM"
    singular="cliente"
    :service="customersService"
    :columns="columns"
    :fields="fields"
    :segments="segments"
    :deletable="false"
    search-label="Buscar por nombre, teléfono, documento, correo o razón social"
    label-field="name"
  />
</template>
