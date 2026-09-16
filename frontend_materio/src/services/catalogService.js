// Catálogo maestro de vehículos (Configuración). Contrato API v2, inglés canónico.
import { apiClient } from './apiClient'
import { createResource } from './createResource'

export const vehicleTypesService = createResource('vehicle-types')
export const bodyTypesService = createResource('body-types')
export const vehicleCategoriesService = createResource('vehicle-categories')

// Público, solo lectura — selector de vehículo del cotizador (invitado/portal cliente).
export const vehiclePickerCatalog = () => apiClient.get('/api/v2/catalog/vehicle-picker')
