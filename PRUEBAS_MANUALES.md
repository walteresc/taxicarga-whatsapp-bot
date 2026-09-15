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

## Actualización 2026-09-12 (3): fotos del vehículo
- `test_transportista` → menú "Mi vehículo" (nuevo) → subir hasta 3 fotos del camión "DEM-001" (tocá cada casillero).
- `test_despacho` o `test_gerencia` → Campo → Transportistas → Afiliados → abrir el detalle de "Transportes Demo" → deberían verse las miniaturas en la columna "Fotos" de la tabla de vehículos.

## Actualización 2026-09-14: /forbidden al entrar a una opción visible en el menú (corregido)
Reportado con captura de pantalla: `test_despacho` veía "Mi equipo" y "Mi flota" en el sidebar, pero al entrar salía "Sin acceso" (`/forbidden`). Causa: hay **3 capas de permisos independientes** que deben coincidir — el menú (NavItems.vue, solo visual), el router de Vue (`routes.js` + el guard que redirige a `/forbidden`, control real) y el backend (`HasAnyRole`, el límite real de datos). `routes.js` estaba desactualizado; algunas vistas del backend (Pizarra/Programación, Drivers, Vehicles, Planilla) tampoco tenían a Despacho/Gerencia. Corregido (commit `f94fbb4`) y verificado en vivo contra el servidor. Volver a revisar:
- `test_despacho`: "Mi equipo" (Personal/Asistencia/Compensaciones/Pagos), "Mi flota", "Operaciones" (Pizarra/Programación/Reservas), Campo (Transportistas/Vehículos) — ya **no** debería salir `/forbidden` en ninguna.
- `test_sistema` (Admin de sistema): "Configuración → BOT" ya **debería** entrar.
- `test_supervisor`: "Configuración → BOT" ahora **correctamente** da `/forbidden` (a propósito, junto con Finanzas/Analítica/Configuración en general).

## Actualización 2026-09-14 (2): menú mostraba "Mi equipo" a roles que no debían verlo
Bug adicional encontrado al revisar `test_sistema` (Admin de sistema): el sidebar mostraba "Planilla" y "Mi flota" (dentro de "Mi equipo") aunque ese rol no tiene acceso — el bloqueo real (backend/router) sí funcionaba, pero el ítem aparecía igual en el menú, generando ruido. Causa: los roles del grupo padre nunca se evaluaban, solo los de sus hijos (que no tienen roles propios). Corregido (commit `6ee2a2f`). Revisar:
- `test_sistema`: el menú ahora debería mostrar **solo** "Configuración" (BOT, Usuarios y permisos) — nada de "Mi equipo", "Mi flota" ni ninguna otra sección.

## Actualización 2026-09-14 (3): "Mi perfil" — antes el menú de usuario no llevaba a ningún lado
El dropdown del avatar (arriba a la derecha) tenía "Profile/Settings/Pricing/FAQ" de la plantilla original, sin conectar, y mostraba "John Doe / Admin" fijo. Ahora:
- Cualquier usuario logueado: clic en el avatar → debería ver tu nombre y rol real (no "John Doe").
- "Mi perfil" → lleva a `/perfil`: ver tus datos, editar nombre/email, y cambiar tu contraseña (pide la actual). "Settings/Pricing/FAQ" se quitaron (no llevaban a nada).

## Actualización 2026-09-14 (4): taxonomía de cara al cliente — Carga | Mudanzas | Reparto
Decisión de negocio: en vez de Carga/Encomiendas/Delivery/Distribución/Última milla como categorías separadas, ahora son 3 líneas claras. Por dentro no cambió nada (misma API, mismos modelos) — revisar:
- Menú CRM: la sección "Encomiendas" ahora se llama **"Reparto"** (Pedidos + Rutas de reparto).
- **http://localhost:8001/cotizar** (sin login): ahora primero pregunta "¿Qué necesitas?" con 3 tarjetas — Carga / Mudanzas / Reparto — antes de pedir direcciones. Probar las 3 y confirmar que cada una pide los datos que le corresponden (Mudanza: ambientes/pisos/ascensor; Reparto: cantidad de pedidos/frecuencia/ecommerce).
- `test_cliente` → Portal Cliente → "Publicar solicitud": mismo selector de 3 tarjetas en el paso 2 del stepper.
- Una solicitud de "Reparto" cae igual en Comercial → Por cotizar, marcada con "[REPARTO]" en el detalle, siempre en modo "un asesor te confirma el precio" (no tiene tarifario propio todavía).

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
