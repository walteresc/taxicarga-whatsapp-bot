# TaxiCarga — Contexto del Proyecto

## Qué es

Sistema de gestión operativa para mudanzas y carga en Perú. Integra CRM de leads, bot WhatsApp con IA (OpenAI), cotizador con aprendizaje por históricos, Pizarra Operativa (Gantt), gestión de equipos de campo, y dashboard con roles.

- Servidor local con ngrok expuesto en puerto 8001 para webhooks WhatsApp (Meta)
- Stack: Django 6.0.6 / DRF 3.17 / SQLite(dev) / PostgreSQL(prod) / OpenAI / Vanilla JS
- Sin Vue/Vuetify/React en código nuevo (base.html carga Vuetify CDN, resto vanilla JS IIFE)
- Clases CSS con prefijos: `ec-` (equipos), `th-equipo`/`.td-empty` (pizarra)
- Colores: Indigo #3949AB, Amber #F59E0B, Blue #2563EB, Green #10B981, Violet #8B5CF6, Red #DC2626

---

## Estructura

```
config/             → settings.py (18 apps), urls.py, wsgi.py, tests.py
apps/
├── dashboard/      → base.html, sidebar, login, leads pipeline (Vuetify kanban, 16 acciones)
│   ├── permissions.py  → 5 roles, decoradores
│   ├── context_processors.py → user_roles, channel filter
│   ├── views.py (986L) → login, dashboard_home, lead_action, placeholders
│   └── templates/  → base, login, home, leads, whatsapp, sidebar, mis_servicios, mi_programacion
├── clientes/       → Cliente (teléfono unique), Conversacion. DRF API + 4 vistas dashboard
├── leads/          → Lead (~45 campos, 12 migs). DRF ViewSet + Admin rico (6 fieldsets, 6 actions)
├── cotizador/      → ServicioHistorico + Cotizacion. Services: cotizar_lead, similarity scoring (~22 pts), fallback pricing
├── whatsapp/       → Webhook Meta, canales multicanal, schedules, conversation guard, override
├── ia/             → conversation_engine (1916L), OpenAI client, data_extractor (regex), image_analyzer, prompts, few-shot
├── servicios/      → Servicio/Reserva (~35 campos, 6 estados), PagoReserva. 8 vistas, 532 tests
├── campo/          → Vehiculo/Conductor/Ayudante/EquipoDia/ProgramacionServicio. Pizarra + Equipos cards+tabs
└── flota/          → MantenimientoVehiculo (FK campo.Vehiculo). 8 vistas CRUD
```

---

## Modelos Clave

**Lead** — estados: nuevo/en_conversacion/datos_incompletos/cotizado/asignado/cerrado/perdido. FK a Cliente, User, WhatsAppChannel. Flags bot: atencion_humana, requiere_asesor, bot_pausado, motivo_derivacion, fecha_derivacion, mixto_inteligente

**Cliente** — telefono (unique), nombre, documento, correo, ruc, razon_social
**Conversacion** — FK Cliente, mensaje_entrada/salida, canal, fecha

**Vehiculo** — placa (unique), marca, modelo, capacidades, vencimientos SOAT/RTV/extintor
**Conductor** — dni (unique), nombre, licencia, FK opcional User
**Ayudante** — dni (unique), nombre, FK opcional User
**EquipoDia** — unique_together=[fecha, vehiculo, conductor]. M2M ayudantes. Related: `equipo.servicios.all()` (NUNCA `programaciones`)
**EquipoFrecuente** — plantilla reutilizable: nombre, FK Vehiculo + Conductor, M2M Ayudantes + conductores_ayudantes (M2M Conductor). Migration 0005. Usado en modal Pizarra tab "Frecuentes" → crea EquipoDia al instanciar
**ProgramacionServicio** — estados: programado/en_ruta/en_servicio/finalizado/cancelado. FK servicios.Servicio

**Servicio** — 6 estados (pendiente→programado→asignado→en_ruta→finalizado/cancelado). Props: total_pagado, total_descuentos, saldo_pendiente, estado_pago
**PagoReserva** — FK Servicio, concepto (adelanto/parcial/final/descuento/ajuste)

**WhatsAppChannel** — phone_number_id (unique), asesor (User), activo
**ConfiguracionBot** — por canal: bot_activo, modo_atencion (bot/humano/mixto), horarios, override. Método: `obtener(channel)` auto-crea
**BotSchedule** — horarios por canal (día, hora_inicio/fin, modo)

**ServicioHistorico** — ~25 campos matching. Índice (tipo_servicio, distrito_origen, distrito_destino). Unique por lead_origen y (fuente, ref_externa)

---

## Roles (apps/dashboard/permissions.py)

- **Administrador** — total (mapea a is_superuser)
- **Supervisor** — Campo, Pizarra, Servicios, Leads, Admin
- **Asesor de Ventas** — Campo, Pizarra, Servicios, Leads
- **Conductor** — solo sus servicios, puede actualizar estado
- **Ayudante** — solo sus servicios (lectura)

Funciones: `can_manage_campo/pizarra/leads/servicios/administracion()`, `can_view_assigned_services()`, `can_driver_update_status()`
Decoradores: `@role_required(...)`, `@leads_required`, `@servicios_required`, `@pizarra_required`, `@conductor_helper_required`
⚠️ **`@campo_required` NO existe** — usar `@role_required("Administrador", "Supervisor", "Asesor de Ventas")` para vistas de campo/pizarra/frecuentes

---

## Convenciones

- **Vistas**: `@login_required` + `@role_required` siempre. AJAX POST: `@require_http_methods(["POST"])`, JSON body, `JsonResponse`. Error → status 409, éxito → `{"status": "ok"}`
- **Templates**: Bloques `title`, `extra_head`, `content`, `extra_scripts`. CSRF en `<meta>`. JSON a JS con `|safe`. Modales con `removeAttribute('hidden')` / `setAttribute('hidden', '')`
- **JS**: IIFE `'use strict'`, event delegation con `e.target.closest()`, fetch con JSON
- **CSS**: inline en `extra_head`, prefijos por módulo

---

## URLs Principales

```
/ → /dashboard/     /admin/     /dashboard/login/     /dashboard/leads/ (pipeline)
/dashboard/leads/<id>/accion/ (POST, 16 acciones)     /dashboard/servicios/
/dashboard/pizarra/ (Gantt semanal)                   /dashboard/campo/equipos/ (cards+tabs)
/dashboard/campo/equipos/validar/ (AJAX GET)          /dashboard/campo/equipos/crear-ajax/ (POST)
/dashboard/campo/equipos/<pk>/eliminar-ajax/ (POST)   /dashboard/campo/equipos/<pk>/editar-ajax/ (POST)
/dashboard/campo/equipos-frecuentes/ (CRUD)           /dashboard/campo/equipos-frecuentes/crear-ajax/ (POST)
/dashboard/campo/equipos-frecuentes/<pk>/editar-ajax/ (POST)
/dashboard/campo/equipos-frecuentes/<pk>/eliminar-ajax/ (POST)
/dashboard/campo/pizarra/* (5 AJAX + equipo/desde-frecuente/)
/dashboard/flota/vehiculos/                           /dashboard/flota/mantenimientos/
/dashboard/whatsapp/                                  /dashboard/reportes/ (placeholder)
/api/clientes/ /api/leads/ /api/cotizador/            /api/bot-settings/ /api/bot-schedules/
/api/whatsapp-channels/                               /webhook/whatsapp/ (csrf_exempt)
```

---

## Pizarra (apps/campo/static/campo/js/pizarra.js)

- **Event delegation** sobre `#pizarra-table` — NO listeners individuales
- `.td-empty` → modal Nueva Reserva | `.btn-add-equipo` → modal Agregar Equipo (3 tabs) | `.btn-del-equipo` → eliminar | `.booking-block` → menú reserva | `.btn-edit-equipo` → editar equipo
- Semana completa (lunes→domingo), slots 06:00–21:00
- **Drag & drop**: `.booking-block[draggable]` y `.unassigned-card[draggable]` desde `#pizarra-table` (delegado). Variables: `draggedPsId`, `draggedSvId`, `draggedIsUnassigned`. Si solo `draggedSvId` (Servicio sin ProgramacionServicio) → llama `assignServicio`; si `draggedPsId` → llama `moveProgramacion`
- **Nueva td-empty**: un solo `.td-half-slot` por `<td>` (no dos). dragover usa `emptyCell.querySelector('.td-half-slot')` como fallback si cursor está en `<td>` pero no en el slot interno
- **`user-select: none`** en `.booking-block` y `.unassigned-card` para evitar selección de texto al iniciar drag

### Modal Agregar/Editar Equipo — 3 tabs

```
.eq-mode-tab[data-eq-mode="dia"]        → panel #eq-panel-dia
.eq-mode-tab[data-eq-mode="frecuentes"] → panel #eq-panel-frecuentes
.eq-mode-tab[data-eq-mode="crear"]      → panel #eq-panel-crear
```

- **Tab "Del día"**: `renderEquiposDia(highlightId)` filtra `EQUIPOS_DIA` por fecha. Cada card tiene `.eq-dia-edit-btn` → pre-llena builder y cambia a tab "Crear". `#eq-panel-formados-inner` se oculta al editar (mostrarlo al reset)
- **Tab "Frecuentes"**: `renderEquiposFrecuentes()` de `EQUIPOS_FRECUENTES`. Seleccionar → `equipoState.frecuenteId`. Envía a `/pizarra/equipo/desde-frecuente/`
- **Tab "Crear nuevo"**: builder con radio vehiculo / role-checks conductor / checkboxes ayudantes. `_fillBuilderFromEquipo(equipo)` reutilizado tanto desde "formados" como desde editar
- `openEquipoModal(fechaIso)` → modo default: 'dia' si hay equipos ese día, 'frecuentes' si hay plantillas, sino 'crear'
- `openEquipoEditModal(equipoId)` → abre en 'dia' con equipo resaltado, pre-llena builder
- Datos JSON en template: `{{ equipos_dia_json|json_script:"pizarra-equipos-dia" }}` y `{{ equipos_frecuentes_json|json_script:"pizarra-equipos-frecuentes" }}`

---

## Equipos de Campo (equipo_calendario, L328, 650L template)

**UI**: Topbar día a día, tabs hoy-1→hoy+7, cards (placa + badge reservas / avatar conductor + chips / advertencias / Ver-Eliminar), modal creación con autocomplete + chips, snackbar

**Reglas**: (1) misma comb vehiculo+conductor → 409 error, (2) mismo vehículo otro cond → warning, (3) conductor multiple → warning, (4) cond no ayudante en su propio equipo, (5) ayudante multi-equipo permitido

**Conductor como ayudante**: autocomplete combina `Ayudante` + `Conductor` en `personal_json` con `role`. Sugerencias/chips con badge (verde/azul). IDs con role="ayudante" → M2M, role="conductor" → `conductor_helper_ids` → se registran en `observaciones`

**Val client-side**: `EQUIPOS_EX` (equipos del día en JSON) chequea combinación existente y warnings instantáneos

**AJAX**: `validar/` (GET), `crear-ajax/` (POST, recibe ayudante_ids + conductor_helper_ids), `<pk>/eliminar-ajax/` (POST), `<pk>/editar-ajax/` (POST)

### Equipos Frecuentes (`/dashboard/campo/equipos-frecuentes/`)

Página CRUD separada para gestionar plantillas `EquipoFrecuente`. Template: `equipos_frecuentes.html`. Contexto: `frecuentes_json`, `vehiculos_json`, `conductores_json`, `ayudantes_json`. Modal único de creación/edición con radio vehiculo, role-checks conductor, checkboxes ayudantes. AJAX a `crear-ajax/`, `<pk>/editar-ajax/`, `<pk>/eliminar-ajax/`.

---

## Flujo Bot WhatsApp → IA → Cotizador

```
Webhook (_receive_message) → extract_event → _reserve_message (idempotencia)
→ Crea/recupera Cliente + Lead, asocia WhatsAppChannel
→ should_bot_reply() → evaluar_mixto_inteligente (route provincia, objetos especiales, históricos <3)
                    → Conversation Guard (patrones pago/reserva/derivación)
→ [Imagen] download_whatsapp_image → analyze_moving_image (OpenAI Vision)
→ [Texto] handle_incoming_message → extract_lead_data (regex) + extract_lead_with_ai (OpenAI)
                                  → conversation_examples_for (few-shot)
                                  → cotizar_lead → _find_similar_services → score_service (~22 pts)
                                                 → fallback_price_for_lead (<3 históricos)
→ Lead cerrado → signal → crear_servicio_historico_desde_lead
```

---

## Tests

| App | Archivo | Líneas | Cobertura |
|-----|---------|--------|-----------|
| campo | `tests/test_models.py` | 317 | Modelos + CRUD |
| campo | `tests/test_pizarra.py` | 231 | Pizarra, estados, permisos |
| dashboard | `tests.py` | 485 | 27 tests: auth, CRUD, CSV, 16 actions |
| dashboard | `tests_permissions.py` | 62 | 5 tests acceso por rol |
| leads | `tests.py` | ~200 | 6 tests: API + admin |
| cotizador | `tests.py` | 470 | Importación, cotización, aprendizaje |
| ia | `tests.py` | 1347+ | Extractor, engine, flujo completo |
| whatsapp | `tests.py` | 1347+ | Webhook, schedules, mixto, multicanal, guard |
| servicios | `tests.py` | 532 | CRUD, permisos, pagos |
| clientes | stub vacío | — | — |
| config | `tests.py` | 9 | Root redirect |

Correr todos: `python manage.py test`

---

## Rama: `feature/gestion-servicios`

Todo lo nuevo vs `main`: sistema permisos, base template + sidebar Vue/Vuetify, apps campo/servicios/flota, WhatsApp multicanal + bot mixto, Pizarra rediseñada (semana completa, drag & drop, modal 3 tabs, edición inline), Equipos de Campo (cards+tabs, conductor-ayudante), Equipos Frecuentes (CRUD + integración pizarra), dashboard leads (kanban, 16 acciones, CSV), cotizador con IA + similarity scoring.

Migs: campo 0001→**0005** (0005=EquipoFrecuente), leads 0011→0012, whatsapp 0001→0007, servicios 0001→0004.

---

## .env

| Variable | Default | Propósito |
|----------|---------|-----------|
| SECRET_KEY | django-insecure-dev-only-change-me | Django secret |
| DJANGO_DEBUG | True | Debug mode |
| ALLOWED_HOSTS | localhost,127.0.0.1,testserver | Hosts |
| DATABASE_URL | sqlite:///db.sqlite3 | DB |
| OPENAI_API_KEY | "" | OpenAI key |
| OPENAI_MODEL | gpt-4.1-mini | Modelo |
| WHATSAPP_VERIFY_TOKEN | "" | Webhook verify |
| WHATSAPP_ACCESS_TOKEN | "" | Meta API token |
| WHATSAPP_PHONE_NUMBER_ID | "" | Número WhatsApp |
| WHATSAPP_API_VERSION | v20.0 | API version |
| YCLOUD_API_KEY | "" | YCloud API key (X-API-Key header) — envío y descarga de medios |
| YCLOUD_WEBHOOK_SECRET | "" | Valida webhooks entrantes de YCloud (HMAC) — distinta de YCLOUD_API_KEY |

⚠️ **Docker (`docker-compose.yml`, servicio `django`/`taxicarga-api`): `docker restart <container>` NO recarga `.env`.** El contenedor conserva el entorno con el que fue creado. Para que cambios en `.env` (nuevas variables, valores actualizados) lleguen al contenedor, usar `docker compose up -d <servicio>` (recrea el contenedor), no `docker restart`. Confirmado 2026-08-27: `YCLOUD_API_KEY` añadida a `.env` no llegó al proceso tras `docker restart taxicarga-api`; sí llegó tras `docker compose up -d django`.

---

## Pendientes

1. **`apps/flota/`** — solo mantenimientos, falta CRUD vehicular propio
2. **Placeholders**: campo.html, personal.html, reportes.html
3. Verificar en browser flujo completo pizarra: modal 3 tabs, drag de POR ASIGNAR a matriz, edición de equipo
4. Merge a `main` cuando estable
5. Deploy (PostgreSQL, SECRET_KEY, ALLOWED_HOSTS)

### Implementado recientemente (no en main)

- ✅ **EquipoFrecuente** — modelo + migración 0005 + CRUD `/equipos-frecuentes/`
- ✅ **Modal Pizarra 3 tabs** — Del día / Frecuentes / Crear nuevo
- ✅ **Editar equipo desde pizarra** — `.btn-edit-equipo` → abre modal en tab "Del día" con resaltado, "Editar" pre-llena builder
- ✅ **Drag & drop unassigned** — items con solo `servicio_id` (sin `ps_id`) ahora son `draggable="true"`; branch `assignServicio` vs `moveProgramacion` en drop
- ✅ **`user-select: none`** en `.booking-block` y `.unassigned-card` (evita selección texto al arrastrar)
- ✅ **Fix dragover** — condición `if (emptyCell)` en vez de `if (halfSlot && emptyCell)` para nueva td-empty con un solo slot interno

---

## NO Tocar

- **Bot WhatsApp** (apps/whatsapp/, apps/ia/) — IA crítica en producción
- **Pizarra** (pizarra.js) — solo bug fixes
- **Tests existentes** — no borrar ni modificar
- **equipo_detail.html** y **equipo_drag_form.html** — legacy activos
- **NO hacer commit** sin pedido explícito

---

## Quién eres

Desarrollador full stack senior Django/DRF para este proyecto. Rol y contrato de trabajo:

**Identidad técnica**
- Django/DRF, Python, Vanilla JS (IIFE), SQLite dev / PostgreSQL prod
- Sin frameworks JS nuevos — solo los ya presentes (Vuetify CDN en base.html)
- Conoces toda la estructura documentada arriba: modelos, roles, URLs, flujo bot

**Estilo de respuesta**
- Código primero. Explicaciones solo si el usuario las pide explícitamente
- Para cambios grandes o que tocan varios archivos: mostrar plan numerado antes de tocar nada, esperar confirmación
- Respuestas cortas y directas — sin introducciones, sin resúmenes al final

**Convenciones que siempre aplicas**
- Vistas: `@login_required` + `@role_required` siempre. AJAX POST: `@require_http_methods(["POST"])`, `JsonResponse`. Error → 409, éxito → `{"status": "ok"}`
- Templates: bloques `title`/`extra_head`/`content`/`extra_scripts`. CSRF en `<meta>`. JSON a JS con `|safe`. Modales con `removeAttribute('hidden')` / `setAttribute('hidden', '')`
- JS: IIFE con `'use strict'`, event delegation con `e.target.closest()`, fetch con JSON
- CSS: inline en `extra_head`, prefijos por módulo (`ec-`, `th-equipo`, etc.)
- No agregar comentarios salvo que el WHY sea no obvio

**Lo que no tocas sin aviso explícito**
- apps/whatsapp/, apps/ia/ (bot en producción)
- pizarra.js (solo bug fixes)
- Tests existentes
- equipo_detail.html, equipo_drag_form.html
