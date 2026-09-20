// El formulario de Carga (ver mockup) no tiene campos separados de peso/
// volumen — el cliente los escribe dentro de la descripción libre ("...peso
// total 500 kg y volumen aprox. 2 m3..."). El motor de precios de Carga
// Consolidada sí necesita un peso estructurado (ver apps/tercerizacion/
// services.py::resolver_tarifa_parcial), así que lo extraemos con una regex
// best-effort; si no lo encuentra, cae al modo "asesor confirma" — el mismo
// fallback que ya existía. Se usa también para mostrarlo en el resumen.
export const extractWeightKg = text => {
  if (!text) return null
  const t = text.toLowerCase()
  let m = t.match(/(\d+(?:[.,]\d+)?)\s*(?:kg|kilos?)\b/)
  if (m) return parseFloat(m[1].replace(',', '.'))
  m = t.match(/(\d+(?:[.,]\d+)?)\s*(?:ton(?:elada)?s?)\b/)
  if (m) return parseFloat(m[1].replace(',', '.')) * 1000

  return null
}

export const extractVolumeM3 = text => {
  if (!text) return null
  const m = text.toLowerCase().match(/(\d+(?:[.,]\d+)?)\s*m\s*(?:3|³|cubicos?|cúbicos?)/)

  return m ? parseFloat(m[1].replace(',', '.')) : null
}

// El cliente nunca elige Compartido/Exclusivo a ciegas — el sistema recomienda
// según el tamaño de SU carga (chica -> tiene sentido compartir camión con
// otra carga; grande -> ya casi no ahorra compartir, conviene camión propio),
// premarcado pero siempre cambiable. Umbrales aproximados en kg (no hay una
// regla exacta de negocio para esto — son un punto de partida razonable,
// ajustable si en la práctica quedan mal calibrados):
//   <= 1500 kg  -> "compartido" (una carga chica no justifica un camión entero)
//   >= 8000 kg  -> "exclusivo"  (a esa escala compartir casi no ahorra)
//   en el medio -> "rango" (ambas modalidades tienen sentido real)
// Sin ninguna estimación de peso, se recomienda "compartido" — es el default
// más barato y más común, y evita anclar una expectativa de precio alto sin
// tener con qué respaldarla.
const UMBRAL_COMPARTIDO_KG = 1500
const UMBRAL_EXCLUSIVO_KG = 8000

export const recomendarModalidad = ({ weightKg } = {}) => {
  if (weightKg == null) return 'compartido'
  if (weightKg <= UMBRAL_COMPARTIDO_KG) return 'compartido'
  if (weightKg >= UMBRAL_EXCLUSIVO_KG) return 'exclusivo'

  return 'rango'
}
