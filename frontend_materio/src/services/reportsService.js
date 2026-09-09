// Reportes. API v2 de solo lectura. Envuelve services_reportes.py (Django).
import { apiClient } from './apiClient'

export const fetchBenchmark = () => apiClient.get('/api/v2/reports/benchmark')

// params: { period, from, to, on, advisor, channel, type }
export const fetchSales = (params = {}) => apiClient.get('/api/v2/reports/sales', params)

// Propio vs Tercerizado + margen. params: { period, from, to, on }
export const fetchOutsourcing = (params = {}) => apiClient.get('/api/v2/reports/outsourcing', params)
