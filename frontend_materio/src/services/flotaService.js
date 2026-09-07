// Flota: vehículos y mantenimientos. API v2, inglés canónico.
import { apiClient } from './apiClient'
import { createResource } from './createResource'

export const vehiclesService = createResource('vehicles')
export const maintenanceService = createResource('maintenance')

// Avisos de vencimientos (SOAT / RTV / extintor / mantenimiento por km).
export const fetchVehicleAlerts = () => apiClient.get('/api/v2/vehicles/alerts/')
