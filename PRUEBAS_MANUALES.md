# Guía de pruebas manuales — Lima Express

Generada el 2026-09-11. Entorno local (Docker), datos de prueba ya cargados en la
base de datos de desarrollo. No toca ninguna cuenta real existente (`wally`,
`asesor_demo`, etc.) — todo lo de abajo es nuevo.

## Acceso

**URL:** http://localhost:8001

Los 4 contenedores deben estar arriba (`docker ps`): `taxicarga-nginx`,
`taxicarga-api`, `taxicarga-postgres`, `taxicarga-redis`.

> ⚠️ **Si cambiás código de backend (Python) y no se refleja al probar**: el
> contenedor `taxicarga-api` corre con Gunicorn, que **no** recarga solo — hay
> que `docker restart taxicarga-api` y esperar a que el healthcheck pase
> (`docker inspect -f '{{.State.Health.Status}}' taxicarga-api`). Esto pasó
> hoy: varios endpoints nuevos daban 404/405 hasta reiniciar el contenedor.

## Usuarios de prueba (contraseña única: `Prueba2026!`)

| Usuario | Rol | Para qué sirve |
|---|---|---|
| `test_gerencia` | Gerencia | Ve márgenes/costos, reportes, comisiones |
| `test_despacho` | Despacho | Pizarra, encomiendas, publicaciones a transportistas |
| `test_finanzas` | Finanzas | Pagos, liquidaciones, COD |
| `test_supervisor` | Supervisor | Similar a Despacho + reportes |
| `test_sistema` | Admin de sistema | Usuarios y permisos, configuración |
| `test_asesor` | Asesor de Ventas | Bandeja, cotizaciones, negociaciones |
| `test_transportista` | Transportista (portal) | Portal Transportista — afiliado en **Lima** |
| `test_cliente` | Cliente Portal | Portal Cliente — teléfono `+51999000002` |

**Transportistas de prueba** (sin login, solo para asignar desde el CRM):
- **Transportes Demo** — Lima, vehículo `DEM-001`, es quien lleva las cargas/envíos de prueba.
- **Local Arequipa** — ubicación frecuente Arequipa, para probar "Asignar reparto a domicilio" en una encomienda interprovincial.

## Datos de prueba para /rastrear (sin login)

Ir a **http://localhost:8001/rastrear** y probar con:

| Código | Teléfono (bastan los últimos 4) | Qué vas a ver |
|---|---|---|
| `CRG-0042` | `0002` | Carga local, estado "En ruta", con Transportes Demo asignado |
| `ENC-00001` | `0002` (remitente) o `0004` (destinatario) | Encomienda local, "En ruta" |
| `ENC-00002` | `0002` (remitente) o `0005` (destinatario) | Encomienda **interprovincial** a Arequipa, "Llegó a destino" |

Probar también:
- Código correcto + teléfono incorrecto → debe rechazar con mensaje genérico.
- Código en minúsculas (`crg-0042`) → debe funcionar igual (case-insensitive).

## Actualización 2026-09-12: menú por rol corregido
Al probar con `test_despacho`/`test_gerencia` se notó que faltaban/sobraban opciones en el menú lateral. Corregido (commit `c81ac3d`): revisar con cada usuario de rol que el menú lateral muestre solo lo que le corresponde:
- `test_despacho` / `test_gerencia`: ahora **sí** deberían ver "Operaciones" (Pizarra, Programación, Reservas), "Mi equipo" y toda la sección "Tercerización" (antes solo veían una parte, o nada).
- `test_finanzas` / `test_sistema`: **no** deberían ver "Bandeja de entrada" en "Atención" (antes la veían todos los roles sin excepción).
- `test_gerencia`: en Analítica ahora debería ver "Ventas vivas" e "Histórico" además de "Propio vs Tercerizado".

## Actualización 2026-09-12 (2): Gerencia superadmin, Supervisor sin Finanzas/Analítica/Configuración
- `test_gerencia`: ahora debería ver **todo** el menú, incluida "Configuración" y todo "Finanzas"/"Analítica".
- `test_supervisor`: ya **no** debería ver "Finanzas", "Analítica" ni "Configuración" — el resto del menú sigue igual.

## Flujos sugeridos por área

### 1. Rastreo público (sin login) — la Fase 0 de hoy
1. `/rastrear` con los 3 códigos de la tabla de arriba.
2. Desde `/seguimiento/<token-inexistente>` → debería fallar y ofrecer el link a "Rastrear con código y teléfono".
3. Desde `/login`, fijarse que aparece el link "¿Ya tenés una carga o envío? Rastreálo con tu código".

### 2. Portal Transportista (`test_transportista`)
1. Login → `/portal/cargas`, `/portal/asignaciones`, `/portal/entregas`, `/portal/cobros`.
2. En `/portal/entregas` debería aparecer la ruta/envío `ENC-00001` (asignado a Transportes Demo, en_ruta).

### 3. Portal Cliente (`test_cliente`)
1. Login → `/portal/cliente/mis-cargas` — debería listar la carga `CRG-0042`.
2. Abrir `/portal/cliente/carga/CRG-0042` — ver el seguimiento (transportista, placa, conductor).
3. Probar `/portal/cliente/publicar` — armar una carga nueva con el autocompletado de direcciones (Mapbox) y, si la marcás a una ciudad como Arequipa, el toggle "Completa / Parcial".

### 4. CRM — Encomiendas (`test_despacho` o `test_gerencia`)
1. `/encomiendas` → buscar `ENC-00002` (interprovincial, en Arequipa, estado "En destino").
2. Abrir el detalle → debería aparecer el bloque **"Reparto a domicilio en destino"** con "Local Arequipa" para elegir y asignar. Confirmar que pasa a estado "En reparto a domicilio (destino)".
3. Crear un envío nuevo desde el botón "Nuevo envío", probar el nivel "Interprovincial (a otra ciudad)" y el campo de punto de entrega (debería ofrecer autocompletar si hay puntos cargados para esa ciudad — hoy no hay ninguno cargado, así que va a pedir texto libre).

### 5. CRM — Configuración → Tarifas de tercerización (`test_gerencia`)
1. Tab "Comisiones" — ya existía, revisar que la tabla cargue.
2. Tab "Carga parcial (consolidada)" — debería listar Arequipa/Trujillo/Chiclayo/Cusco/Piura + tramo general. Probar crear/editar/borrar un tramo.

### 6. CRM — Campo → Transportistas → Afiliados (`test_despacho` o `test_sistema`)
1. Ver que "Transportes Demo" y "Local Arequipa" aparecen en la lista con su columna "Ubicación".
2. Abrir el detalle de "Transportes Demo" → debería mostrar la dirección y el chip de ubicación.
3. Crear un afiliado nuevo y completar "Dirección" y "Ubicación frecuente" — confirmar que se guardan.

### 7. Cotizador de invitado (sin login)
1. `/cotizar` → probar una ruta dentro de Lima (debería cotizar automático) y una a una ciudad de provincia (debería activar el toggle Completa/Parcial y, si elegís Parcial, mostrar "Llega en N días").

## Qué NO está cubierto todavía (no es un bug si falla)
- Reparto a domicilio real en destino más allá de la asignación (no hay app del transportista para que actualice su posición).
- Timeline de eventos para cargas (`CRG-`/`SVC-`) — hoy `/rastrear` solo muestra el estado actual, no un historial (es la Fase 1 pendiente).
- Notificación automática por WhatsApp al cambiar de estado (Fase 2 pendiente).
