# Limitación conocida del cotizador: rutas fuera de Lima Metropolitana

**Estado:** abierto — condiciona la Fase 3 (bot que da precios).
**Detectado:** 2026-09-02, durante la reincorporación de la extracción NLU (Fase 2).
**Regla operativa vigente:** el bot **no puede cotizar** rutas fuera de Lima. Los
leads con `requiere_asesor=True` por este motivo se cotizan **a mano**, siempre.

---

## Resumen en una línea

El cotizador automático solo tiene base estadística para rutas **dentro de Lima
Metropolitana**. Para una ruta interprovincial devuelve un precio con apariencia de
fundado que puede estar equivocado por un factor de ocho.

---

## Los números

Histórico de servicios (`cotizador_serviciohistorico`), a 2026-09-03:

| Métrica | Valor |
|---|---|
| Filas totales | 19.505 |
| Filas **cerradas** (las únicas que usa `_find_similar_services`) | 9.306 |
| Servicios cerrados **fuera de Lima** (heurística por nombre de ciudad) | ~551 → **5,9 %** de las cerradas |
| — de ellos: carga | 276 · mudanza 255 · oficina 20 |
| **Rutas interprovinciales distintas** representadas | ~525 |
| Rutas con **≥ 3 servicios** (mínimo que pide `cotizar_lead`) | **4** |
| Servicios interprovinciales con ≤ 2 años de antigüedad (peso de recencia ≥ 0,5) | 98 |

Dispersión de precio de esos servicios (soles, precio final):

| Tipo | n | mín | p25 | mediana | p75 | máx |
|---|---|---|---|---|---|---|
| carga | 276 | 55 | 200 | 550 | 1.100 | 6.490 |
| mudanza | 255 | 50 | 400 | 1.000 | 2.120 | 8.260 |

La mediana no significa nada: el precio interprovincial lo domina la **distancia
entre ciudades** (Lima→Cañete ≈ 150 km vs Lima→Iquitos, sin carretera), y el
cotizador no tiene ninguna variable de distancia.

---

## Por qué falla

`apps/cotizador/services.py :: _find_similar_services`

- Filtra duro solo por `tipo_servicio__iexact`. El distrito **no filtra**, solo suma
  puntos en `score_service` (+3 origen, +3 destino).
- `similarity._canonical` solo normaliza alias de distritos de Lima
  (`santiago de surco → surco`, …). No conoce `piura`, `tumbes`, `chiclayo`, etc.
- `cotizar_lead` exige **≥ 3** servicios con score ≥ `max(8, best_score − 3)`. Como
  casi ninguna ruta interprovincial tiene 3 casos, cae al `fallback_price_for_lead`.
- `fallback_price_for_lead` (`apps/cotizador/pricing.py`): `_distance_cost()` devuelve
  siempre `0`. Las `BASE_PRICES` (mudanza 150 / carga 180 / oficina 350) son precios
  **locales de Lima**.

Resultado: un lead interprovincial recibe, o bien un precio base de Lima, o bien
—peor— una mediana calculada con traslados locales que casualmente puntuaron 8.

---

## Dos casos reales (conversaciones de WhatsApp, sept. 2026)

### Piura → Tumbes, carga, 9,5 Tn de aceite
- Precio real que dio el asesor: **S/ 3.800 + IGV** (solo transporte).
- `_find_similar_services`: **0 similares** → fallback.
- Fallback con `peso_carga_kg = 9500` → recomendado **S/ 1.320** (min 1.188 / max 1.584).
- Desviación: **−65 %**. Sin el peso capturado habría dado S/ 180.

### Lima → Piura, carga, una cabina de audiometría (250 kg)
- Precio real que dio el asesor: **S/ 2.500 + IGV**.
- `_find_similar_services`: encuentra **4 "similares"**, todos traslados
  **Miraflores → distrito de Lima** (Los Olivos, Surco, Pueblo Libre, San Isidro),
  S/ 50–1.070, score 8.0–8.1.
- Como son ≥ 3, calcula mediana/percentiles con ellos → ~**S/ 300**, y lo presenta
  como *"calculada con mediana y percentiles de los históricos operativamente más
  similares"*.
- Desviación: **−88 %**, con narrativa de precio fundado. Este es el caso peligroso.

---

## Salvaguarda actual (Fase 2)

`apps/whatsapp/services_extraccion.py`:

- La extracción marca `ruta_interprovincial` en `datos_extraidos` cuando el modelo
  reporta `ambito = "interprovincial"` o cuando origen/destino contienen una ciudad
  de la lista `_CIUDADES_NO_LIMA`.
- `volcar_datos_extraidos_al_lead` pone entonces `lead.es_interprovincial = True`
  (marca estructurada, usada por los reportes) y `lead.requiere_asesor = True`
  (salvaguarda del cotizador).
- El comando `extraer_datos_conversaciones` avisa en pantalla: *"⚠ ruta FUERA DE
  LIMA — el cotizador automático no la cubre"*.

**Esta marca debe respetarse siempre.** Ningún flujo automático (ni el actual ni la
Fase 3) debe emitir un precio a un cliente para un lead con `requiere_asesor=True`
por ruta fuera de Lima.

---

## Implicancia para la Fase 3 (bot que cotiza)

Mientras esta limitación no se resuelva:

- El bot puede cotizar en automático **solo** rutas dentro de Lima Metropolitana +
  Callao.
- Para cualquier otra ruta el bot debe derivar a un asesor, no dar número.

---

## Opciones de mejora (pendiente de análisis, no diseñar aún)

1. **Separar el matching por ámbito**: que `_find_similar_services` no mezcle
   locales con interprovinciales; para interprovincial, exigir coincidencia de
   ciudad de destino.
2. **Variable de distancia entre ciudades**: tabla de km (o zonas) ciudad↔ciudad;
   `_distance_cost` deja de ser 0.
3. **Tabla de tarifas interprovinciales** construida a partir de los ~551 servicios
   cerrados que sí existen, agrupando por ciudad de destino y tipo de vehículo.
4. Combinación: (1) + (3) como tabla de respaldo cuando no hay ≥ 3 casos de la ruta.

Cualquiera de ellas es un tema en sí mismo; se aborda después de cerrar la Fase 2.
