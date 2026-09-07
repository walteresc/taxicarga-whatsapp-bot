// Personal de campo: conductores y ayudantes. API v2, inglés canónico.
import { createResource } from './createResource'

export const driversService = createResource('drivers')
export const assistantsService = createResource('assistants')

// Categorías de licencia peruanas (mismo valor en API y BD).
export const LICENSE_CATEGORIES = [
  'A-I', 'A-II-a', 'A-II-b', 'A-III-a', 'A-III-b', 'A-III-c',
  'B-I', 'B-II-a', 'B-II-b', 'B-II-c',
]
