// Transportistas afiliados y sus vehículos. Contrato API v2, inglés canónico.
import { apiClient } from './apiClient'
import { createResource } from './createResource'

export const carriersService = createResource('carriers')
export const carrierVehiclesService = createResource('carrier-vehicles')
export const carrierDriversService = createResource('carrier-drivers')

export const LICENSE_CATEGORIES = [
  'A-I', 'A-II-a', 'A-II-b', 'A-III-a', 'A-III-b', 'A-III-c', 'B-I', 'B-II-a', 'B-II-b', 'B-II-c',
]

// Catálogo para los selects del alta de vehículos.
export const fetchVehicleCatalog = async () => {
  const [types, bodies] = await Promise.all([
    apiClient.get('/api/v2/vehicle-types/', { pageSize: 200, status: 'active' }),
    apiClient.get('/api/v2/body-types/', { pageSize: 200, status: 'active' }),
  ])

  return {
    vehicleTypes: types.results,
    bodyTypes: bodies.results,
  }
}
