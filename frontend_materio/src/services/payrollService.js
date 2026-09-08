// Planilla (payroll). API v2, inglés canónico.
import { apiClient } from './apiClient'
import { createResource } from './createResource'

export const payrollConfigService = createResource('payroll-config')
export const attendanceService = createResource('payroll-attendance')
export const compensationsService = createResource('payroll-compensations')
export const openingBalanceService = createResource('payroll-opening-balance')
export const paymentsService = createResource('payroll-payments')

export const fetchPayrollDay = date => apiClient.get('/api/v2/payroll/day', { date })
export const savePayrollDay = body => apiClient.post('/api/v2/payroll/day', body)
export const fetchPendingAbsences = params => apiClient.get('/api/v2/payroll/pending-absences', params)
export const fetchPayCalc = params => apiClient.get('/api/v2/payroll/calc', params)
export const fetchPayrollSummary = date => apiClient.get('/api/v2/payroll/summary', { date })
export const fetchWorkerPayroll = (id, date) => apiClient.get(`/api/v2/payroll/worker/${id}`, { date })

export const CONTRACT_TYPES = [
  { value: 'planilla', label: 'Planilla (sueldo mensual)' },
  { value: 'honorarios', label: 'Recibo por honorarios' },
]

export const DAY_TYPES = [
  { value: 'trabajado', label: 'Trabajado' },
  { value: 'falta', label: 'Falta' },
  { value: 'vacaciones', label: 'Vacaciones' },
  { value: 'descanso', label: 'Descanso / franco' },
  { value: 'feriado', label: 'Feriado' },
  { value: 'licencia_sin_goce', label: 'Licencia sin goce' },
]

export const PAYMENT_TYPES = [
  { value: 'quincena', label: 'Quincena' },
  { value: 'fin_de_mes', label: 'Fin de mes' },
  { value: 'adelanto', label: 'Adelanto / otro' },
]

export const COMPENSATION_KINDS = [
  { value: 'falta_compensada', label: 'Falta compensada con horas' },
  { value: 'dia_libre', label: 'Día libre a cuenta de horas' },
  { value: 'pago_horas', label: 'Pago de horas extra' },
  { value: 'devolucion_trabajador', label: 'El trabajador repone horas' },
  { value: 'ajuste', label: 'Ajuste manual' },
]
