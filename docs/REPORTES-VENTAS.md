# Reportes de ventas

**Estado:** implementado (Fase reportes, 2026-09-03). Dos pantallas server-rendered
en `/dashboard/reportes/`, acceso Administrador / Supervisor.

- `dashboard-reportes` → hub con dos tarjetas.
- `dashboard-reportes-ventas` → **Ventas vivas** (pipeline del CRM).
- `dashboard-reportes-historico` → **Benchmark histórico** (`ServicioHistorico`).

Lógica de cálculo: `apps/dashboard/services_reportes.py` (capa de servicio, nada de
cálculo en las vistas). Nada escribe en la base. Nada toca el chat en tiempo real
(son páginas Django normales, sin bundle de frontend).

---

## Dos fuentes de datos, disjuntas

| | Filas hoy | Sirve para |
|---|---|---|
| **Ventas vivas**: `Servicio` + `Lead` + `PagoReserva` + `CotizacionComercial` | casi vacío | ventas atribuibles por asesor/canal/tipo, embudo, cobranzas. Se llena con el uso del CRM. |
| **Benchmark histórico**: `cotizador.ServicioHistorico` (~19.5k, fuente `wally`) | 19.505 | tendencia del negocio, distribución de precios, **tarifas de rutas interprovinciales**. Llega a jul-2026, no crece, no es atribuible a asesor/canal. |

Todas las funciones de `services_reportes` devuelven **ceros, no excepción**, con la
base vacía (test `ReportesServiceVacioTests`).

## Pantalla 2 — Ventas vivas

Selector de periodo (día / semana / quincena / mes / rango) + filtros asesor / canal
/ tipo. Cuatro bloques:

1. **Ventas del periodo** — reservas y facturación, **bruto** (incluye canceladas) y
   **neto** (las excluye) en columnas separadas; serie temporal; desglose por asesor,
   canal y tipo. "Venta" = `Servicio` con `fecha_confirmacion` en el rango.
2. **Embudo** — leads creados → cotizados (`CotizacionComercial` enviada) → ganados
   (`Lead.estado=cerrado`) → perdidos, con tasas y ciclo de venta
   (`fecha_cierre − fecha_creacion`). Desglose de `motivo_perdida`.
3. **Ticket local vs interprovincial** — usa `Servicio.es_interprovincial`.
4. **Cobranzas** — facturado / cobrado / pendiente (propiedades `Servicio.total_pagado`,
   `saldo_pendiente`, `estado_pago`), antigüedad del saldo, cobrado por método de pago,
   ranking de saldos.

## Pantalla 1 — Benchmark histórico

Volumen por año/mes, mix por tipo, distribución de precio (mediana/p25/p75/p90),
split local vs interprovincial (nº, ticket, facturación, %), y **rutas
interprovinciales con ≥ 3 servicios y su tarifa típica** (mediana). La ciudad se
infiere del texto de origen/destino con la lista `_CIUDADES_NO_LIMA`; la agrupación
es aproximada porque las direcciones no tienen estructura.

---

## Cambios de modelo aplicados (migraciones `leads.0014`, `servicios.0008`)

| Campo | Modelo | Se llena en |
|---|---|---|
| `fecha_confirmacion` (Date) | `Servicio` | `crear_servicio_desde_lead` (= `timezone.localdate()`) |
| `fecha_finalizacion` (Date) | `Servicio` | `Servicio.save()` la sella la 1.ª vez que `estado=finalizado` |
| `es_interprovincial` (bool) | `Servicio` | heredado del lead en `crear_servicio_desde_lead` |
| `es_interprovincial` (bool) | `Lead` | `volcar_datos_extraidos_al_lead` cuando la extracción detecta ruta fuera de Lima (ver [COTIZADOR-LIMITACION-INTERPROVINCIAL.md](COTIZADOR-LIMITACION-INTERPROVINCIAL.md)) |
| `motivo_perdida` → `choices` | `Lead` | `precio / tiempo_respuesta / competencia / no_responde / fuera_cobertura / otro`. `_close_lost` mapea texto libre con `Lead.map_motivo_perdida()` |
| `motivo_perdida_detalle` (Text) | `Lead` | guarda la frase original cuando no era un código |

`requiere_asesor=True` se **mantiene** en las rutas interprovinciales: es la
salvaguarda del cotizador, independiente de la marca de reporte.

## Huecos que quedan (fuera de alcance por decisión del usuario)

- `Servicio` sin campo de origen bot/asesor (se hereda `whatsapp_channel`, no la vía).
- Rentabilidad / margen: `RevisionCotizacion.costo_estimado` casi nunca se llena todavía.
- Serie temporal que empalme histórico + vivo.
- `ServicioHistorico` no tiene asesor ni canal y no se puede reconstruir.
