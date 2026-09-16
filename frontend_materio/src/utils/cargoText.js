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
