/**
 * Parse fecha de múltiples formatos
 * Soporta: ISO string, Django datetime, timestamp, valor nulo
 */
export const parseDate = (dateValue) => {
  if (!dateValue) return null

  let date

  if (typeof dateValue === 'string') {
    date = new Date(dateValue)
  } else if (typeof dateValue === 'number') {
    date = new Date(dateValue)
  } else if (dateValue instanceof Date) {
    date = dateValue
  }

  // Validar que la fecha sea válida
  if (!date || isNaN(date.getTime())) {
    return null
  }

  return date
}

/**
 * Formatear fecha para mostrar en mensajes
 * Retorna: "HH:MM" o null si no es válida
 */
export const formatMessageTime = (dateValue) => {
  const date = parseDate(dateValue)
  if (!date) return null

  return date.toLocaleTimeString('es-ES', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Formatear fecha para separadores de grupo (Hoy, Ayer, fecha)
 * Retorna: "Hoy", "Ayer", "15 de agosto" o null
 */
export const formatDateSeparator = (dateValue) => {
  const date = parseDate(dateValue)
  if (!date) return null

  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)

  const dateStr = date.toLocaleDateString('es-ES')
  const todayStr = today.toLocaleDateString('es-ES')
  const yesterdayStr = yesterday.toLocaleDateString('es-ES')

  if (dateStr === todayStr) {
    return 'Hoy'
  }
  if (dateStr === yesterdayStr) {
    return 'Ayer'
  }

  // Formato: "15 de agosto"
  return date.toLocaleDateString('es-ES', {
    day: 'numeric',
    month: 'long',
  })
}

/**
 * Agrupar mensajes por fecha
 */
export const groupMessagesByDate = (messages) => {
  const groups = {}

  messages.forEach(msg => {
    const dateStr = formatDateSeparator(msg.timestamp)
    if (!dateStr) {
      // Si no hay fecha válida, ponerlo en un grupo especial
      if (!groups['invalid']) {
        groups['invalid'] = { date: null, messages: [], displayDate: null }
      }
      groups['invalid'].messages.push(msg)
    } else {
      if (!groups[dateStr]) {
        groups[dateStr] = {
          date: parseDate(msg.timestamp),
          messages: [],
          displayDate: dateStr,
        }
      }
      groups[dateStr].messages.push(msg)
    }
  })

  return Object.values(groups).sort((a, b) => {
    if (!a.date || !b.date) return 0
    return a.date.getTime() - b.date.getTime()
  })
}
