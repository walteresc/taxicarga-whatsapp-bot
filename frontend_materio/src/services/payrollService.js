// Planilla (payroll). API v2, inglés canónico.
import { createResource } from './createResource'

export const payrollConfigService = createResource('payroll-config')

export const CONTRACT_TYPES = [
  { value: 'planilla', label: 'Planilla (sueldo mensual)' },
  { value: 'honorarios', label: 'Recibo por honorarios' },
]
