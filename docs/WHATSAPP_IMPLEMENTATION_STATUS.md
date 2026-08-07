# Estado de implementación del módulo WhatsApp

Última actualización: 2026-08-07  
Etapa actual: ETAPA 10 — Validación técnica terminada; 387/388 pruebas pasan
Próximo paso: validación manual con cuenta Meta real y estabilizar la prueba horaria legacy.

## 1. Arquitectura encontrada

- Backend: Django 6.0.6 y Django REST Framework 3.17.
- Frontend: templates Django, Vue 3 y Vuetify cargados por CDN en `apps/dashboard/templates/dashboard/base.html`; otros módulos usan JavaScript vanilla.
- Base local: SQLite en `db.sqlite3`. Producción prevista con PostgreSQL mediante `DATABASE_URL`.
- Autenticación: sesión Django.
- Roles existentes: Administrador, Supervisor, Asesor de Ventas, Conductor y Ayudante; lógica en `apps/dashboard/permissions.py`.
- Integraciones: Meta WhatsApp Cloud API y OpenAI.
- Rama revisada: `feature/gestion-servicios`.
- Estado Git inicial: árbol de trabajo con cambios modificados y archivos no rastreados previos. Se conservaron íntegramente. Esta etapa solo añade este documento.

### Datos locales verificados

| Entidad | Registros |
|---|---:|
| Cliente | 49 |
| Conversacion | 212 |
| Lead | 45 |
| Cotizacion | 14 |
| ServicioHistorico | 19 505 |
| WhatsAppChannel | 4 |
| ConfiguracionBot | 5, incluida configuración global |
| BotSchedule | 21 |
| MensajeWhatsappProcesado | 73 |
| EvidenciaWhatsapp | 0 |

Configuraciones encontradas: dos canales en modo `bot`, uno en `humano`, uno en `mixto`, más configuración global en `bot`. No se cambiaron.

## 2. Componentes existentes que deben conservarse

### Clientes y conversación

- `apps/clientes/models.py`
  - `Cliente`: nombre, teléfono único, documento, correo, RUC, razón social y última interacción.
  - `Conversacion`: guarda pares simples `mensaje_entrada`/`mensaje_salida`, canal textual y fecha.
- `apps/clientes/views.py` y `apps/clientes/urls.py`: API DRF para clientes y conversaciones.
- `apps/clientes/admin.py`: consulta de clientes y conversación desde admin.

### Solicitud estructurada

- `apps/leads/models.py` contiene `Lead`, hoy principal ficha estructurada del servicio.
- Ya guarda tipo, ruta, direcciones, pisos, ascensores, inventario, objetos pesados, modalidad, desarmado, accesos, llegada del camión, distancias, peso, volumen, vehículo, fecha, horario, precios, prioridad, asesor y canal.
- Ya incluye flags de control: `atencion_humana`, `requiere_asesor`, `bot_pausado`, `motivo_derivacion`, `fecha_derivacion`.
- `apps/leads/views.py` y `apps/leads/urls.py`: API de leads, pendientes, cotizados y acciones comerciales.
- `apps/dashboard/views.py`: dashboard actual, ficha de lead y 16 acciones, incluidas tomar/liberar, respuesta manual, recálculo y envío de precio.

### WhatsApp y canales

- `apps/whatsapp/models.py`
  - `WhatsAppChannel`: nombre, `phone_number_id`, número visible, asesor y estado activo.
  - `ConfiguracionBot`: configuración global o por canal, modo, días, horario, mensaje fuera de horario y override.
  - `BotSchedule`: rangos por día, canal y modo.
  - `MensajeWhatsappProcesado`: idempotencia de entrada por `message_id` único.
  - `EvidenciaWhatsapp`: archivo, metadatos y análisis visual para imágenes.
- `apps/whatsapp/views.py`
  - `GET/POST /webhook/whatsapp/`: verificación y recepción.
  - Identifica canal usando `metadata.phone_number_id`.
  - Ignora canal inactivo.
  - Reserva el evento antes de procesarlo y evita duplicados.
  - Crea o recupera cliente y lead.
  - Guarda texto e imágenes.
  - Bloquea respuesta automática cuando el lead está en atención humana.
  - Envía la respuesta por Meta y solo completa el evento si Meta acepta el mensaje.
  - Expone APIs autenticadas para configuración, horarios y canales.
- `apps/whatsapp/services.py`: envío de texto y descarga privada de imágenes desde Meta.
- `apps/whatsapp/utils.py`: horarios, overrides, reglas mixtas, guard de conversación, derivación y extracción del evento.

### IA y extracción

- `apps/ia/conversation_engine.py`: motor conversacional progresivo. Extrae varios datos en un turno, pregunta por faltantes, cotiza, negocia, reserva y deriva rutas/casos complejos.
- `apps/ia/data_extractor.py`: extracción determinista de tipo, ruta, pisos, ascensores, fecha, horario, inventario, objetos pesados, modalidad y desarmado.
- `apps/ia/openai_client.py`: extracción/respuesta complementaria con OpenAI.
- `apps/ia/image_analyzer.py`: análisis de inventario desde fotografías.
- `apps/ia/history.py` y `apps/ia/models.py`: ejemplos anonimizados para contexto.

### Cotización e históricos

- `apps/cotizador/models.py`
  - `ServicioHistorico`: datos operativos, vehículo, ayudantes y precios; índices y restricciones antiduplcado.
  - `Cotizacion`: resultado técnico ligado al lead con mínimo, máximo, recomendado, cantidad de similares y explicación.
- `apps/cotizador/services.py`: búsqueda de similares, cálculo por históricos y fallback.
- `apps/cotizador/pricing.py`: reglas de precio base y factores operativos.
- `apps/cotizador/signals.py`: crea o actualiza un histórico al cerrar un lead válido.
- Importadores existentes para CSV y dump Wally anonimizado.

### Visual existente

- `apps/dashboard/templates/dashboard/base.html`: cabecera, sidebar, selector de canal, tipografía y estructura general.
- `apps/dashboard/templates/dashboard/leads.html`: pipeline comercial, chat/ficha y acciones que pueden reutilizarse.
- `apps/dashboard/templates/dashboard/whatsapp.html`: pantalla funcional de configuración por canal, modos, horarios, mensaje fuera de horario y override.
- La imagen de referencia coincide con el patrón actual: sidebar oscuro, cabecera clara, contenido en tarjetas/tablas, acento naranja y densidad de escritorio. Debe usarse como guía para las seis pantallas, no como fuente de datos.

## 3. Funcionalidad realmente operativa

### Verificada por código, base y pruebas que pasan

- Base de datos activa; no es un frontend estático.
- Webhook GET valida `WHATSAPP_VERIFY_TOKEN`.
- Webhook POST extrae texto e imagen.
- Idempotencia de mensajes entrantes.
- Asociación de mensajes con canal por `phone_number_id`.
- Canales independientes, activos/inactivos y con asesor.
- Configuración y horarios por canal.
- Modos actuales: `bot`, `humano`, `mixto`.
- Overrides temporales: forzar bot, humano o mixto.
- Bot no responde cuando `atencion_humana`, `bot_pausado` o `requiere_asesor` están activos.
- Guard detecta pagos, reservas o coordinación humana y pausa el bot.
- Extracción progresiva de datos y preguntas solo por faltantes.
- Imágenes guardadas privadamente y analizadas cuando OpenAI está disponible.
- Cotización por similares o fallback.
- Derivación mixta por provincia, objetos especiales, pisos altos sin ascensor, oficina, embalaje full o pocos históricos.
- Respuesta manual y envío de precio desde Gestión de Leads.
- Aprendizaje desde servicios cerrados sin duplicar histórico por lead.

### Parcialmente implementada

- Control bot/asesor existe mediante flags en `Lead`, pero no es una máquina de estados separada ni una transferencia atómica.
- `manual_reply` activa atención humana, pero no usa `transaction.atomic()` ni `select_for_update()`; dos asesores podrían competir.
- Al devolver al bot solo se limpian flags. No existe instrucción de continuación ni bloqueo explícito de precio/condiciones del asesor.
- Chat actual guarda un registro con entrada y salida juntas. No representa cada mensaje, autor, tipo, entrega, lectura, error o canal real.
- Fotos existen como evidencia; audios, documentos, ubicaciones y adjuntos salientes no están implementados.
- `Lead` sirve como ficha, cola y estado comercial simultáneamente. Faltan estados independientes de atención, recopilación y cotización.
- `Cotizacion` es cálculo técnico. No tiene código comercial, estado, revisión, snapshot, condiciones, vigencia, creador, emisor, canal, entrega o auditoría.
- Configuración por canal funciona, pero no cubre los cuatro modos solicitados ni reglas configurables, margen, confianza, seguimiento o zona horaria.
- La pantalla de configuración existe; “Canales WhatsApp” aún es placeholder.
- Gestión de Leads contiene conversación, toma, respuesta y precio, pero no equivale a las seis pantallas separadas.

### No implementada después de ETAPA 1

- Bandeja compartida de tres columnas con filtros, no leídos y espera.
- Cola única “Por cotizar” con deduplicación explícita.
- Crear cotización con borrador, snapshot inmutable, margen, condiciones y vista previa.
- Historial comercial de cotizaciones y detalle con revisiones.
- Integración visual de la auditoría de transferencias, cambios, autorizaciones y envíos.
- Estados de entrega de Meta y webhook de status.
- Reintentos salientes persistentes.
- Aplicación del permiso especial de precio bajo margen en la futura vista; la validación de dominio ya existe.

## 3.1. ETAPA 1 implementada

### Conversación y mensajes normalizados

- `whatsapp.ConversacionWhatsApp`: sesión ligada a cliente, lead, canal y responsable.
- Estados separados de atención, recopilación y cotización.
- Resumen, datos faltantes, porcentaje, derivación y timestamps separados.
- Restricción de una conversación activa por lead.
- Índices para bandeja por canal, atención, cotización y actividad.
- `whatsapp.MensajeWhatsApp`: mensaje individual con dirección, origen, tipo, autor, evidencia, estado Meta, error y timestamps.
- Restricción idempotente para `meta_message_id` no vacío.
- `whatsapp.AuditoriaWhatsApp`: eventos append-only con actor y detalle JSON.

### Transiciones atómicas

- `apps/whatsapp/domain.py` centraliza:
  - obtener o crear conversación compatible con el lead legacy;
  - tomar conversación;
  - devolver al bot con instrucción explícita;
  - enviar a cotizar sin duplicar pendientes;
  - cerrar conversación;
  - sincronizar flags legacy y registrar auditoría.
- Usa `transaction.atomic()` y `select_for_update()`.
- Impide que un segundo asesor tome una conversación asignada.
- Respuesta manual y envío de precio toman primero la conversación.
- Acciones legacy `take_over` y `release` ya usan el servicio central.
- Devolver al bot conserva precios existentes y limpia flags de control humano.

### Cola y cotización comercial

- `cotizador.SolicitudCotizacion`: cola con estado, motivo, faltantes, prioridad, asignación y timestamps.
- Restricción de una solicitud activa por lead.
- `cotizador.CotizacionComercial`: código, lead, solicitud, canal, origen bot/asesor, estado y responsable.
- `cotizador.RevisionCotizacion`: snapshot, precios sugeridos, costo, margen, precio final, condiciones, vigencia y mensaje.
- Revisión enviada inmutable; cambios posteriores requieren nueva revisión.
- Validación de precio contra costo y margen mínimo, con bandera explícita para autorización futura.
- `cotizador.EnvioCotizacion`: intento, canal, estado Meta, error y entrega.
- `apps/cotizador/commercial.py` centraliza borradores, revisiones y cierre de solicitud al enviar.

### Compatibilidad y datos

- No se eliminó ni renombró ningún modelo o campo existente.
- Migración de datos creó 45 sesiones desde 45 leads locales.
- 44 quedaron activas y una cerrada según estado legacy.
- Los 212 registros legacy de `clientes.Conversacion` se conservan sin alteración.
- No se normalizaron mensajes legacy automáticamente porque no contienen vínculo inequívoco a lead/canal ni un mensaje por fila.
- Nuevos modelos registrados en Django Admin.
- Permisos base añadidos: `can_manage_whatsapp`, `can_configure_whatsapp`, `whatsapp_required` y `whatsapp_config_required`. Su aplicación a pantallas/API se hará junto con rutas para no romper endpoints legacy antes de ETAPA 2/8.

## 3.2. ETAPA 2 implementada

### Menú lateral

- Grupo `WHATSAPP` añadido al sidebar principal.
- Entradas: Conversaciones, Por cotizar, Cotizaciones y Configuración del bot.
- Administrador ve las cuatro opciones.
- Supervisor y Asesor de Ventas ven las tres opciones operativas.
- Conductor y Ayudante no ven ni acceden al módulo.
- `context_processors.user_roles` reconoce superusuario como Administrador.
- Se actualizaron las dos fuentes de menú existentes: `base.html` y `views_sidebar.py`.

### Rutas base

- `/dashboard/whatsapp/conversaciones/`
- `/dashboard/whatsapp/por-cotizar/`
- `/dashboard/whatsapp/cotizaciones/`
- `/dashboard/whatsapp/configuracion/`

Las tres rutas operativas usan `whatsapp_required`. Configuración usa `whatsapp_config_required` y queda restringida a Administrador. La ruta legacy `/dashboard/whatsapp/` y Gestión de Leads siguen disponibles.

### Datos reales

- Conversaciones consulta `ConversacionWhatsApp`, cliente, lead, canal y responsable.
- Por cotizar consulta solicitudes activas de `SolicitudCotizacion`.
- Cotizaciones consulta `CotizacionComercial` y última `RevisionCotizacion`.
- Selector global de canal filtra cada consulta cuando el canal existe y está activo.
- Cada vista base muestra métricas y hasta 20 registros reales; no contiene datos demo permanentes.
- Configuración reutiliza `dashboard/whatsapp.html`; no se creó pantalla duplicada.

## 4. Duplicaciones, inconsistencias y código sin uso claro

## 3.9. ETAPA 9 implementada

- Envío real de la última revisión desde el detalle de cotización.
- Usa el `phone_number_id` del canal seleccionado, no solo el canal global.
- Cada intento queda persistido con Meta ID, error, número y límite de intentos.
- Webhook procesa estados `sent`, `delivered`, `read` y `failed`.
- Cotización pasa a entregada cuando Meta confirma entrega.
- Reintentos exponenciales persistentes mediante `reintentar_envios_whatsapp`.
- Recepción y almacenamiento privado de imágenes, audios, PDF, DOC y DOCX.
- Recepción de ubicaciones y extracción de coordenadas.
- Compatibilidad conservada con el flujo legacy y mensajes normalizados.

## 3.8. ETAPA 8 implementada

- Configuración independiente por canal WhatsApp.
- Cuatro modos operativos: Solo asesor, Recopilar datos, Cotización automática e Híbrido.
- Compatibilidad sincronizada con los modos legacy `humano`, `bot` y `mixto`.
- Horario, días activos, zona horaria y transferencia fuera de horario.
- Confianza mínima, margen mínimo, espera del asesor y seguimiento.
- Asesor predeterminado, reglas automáticas y mensajes configurables.
- El modo Recopilar datos deriva antes de enviar un precio automático.
- Pantalla restringida a Administrador; APIs legacy conservadas.
- Migración aplicada preservando las cinco configuraciones locales existentes.

## 3.7. ETAPA 7 implementada

- Detalle comercial enlazado desde el historial.
- Cabecera con código, estado y opción Imprimir/PDF del navegador.
- Resumen de creación, última revisión, último envío y estado.
- Información del cliente, canal, asesor y servicio.
- Precio, condiciones, vigencia y versión vigente.
- Historial completo de revisiones con mensajes WhatsApp guardados.
- Timeline derivado de creación, revisiones e intentos de envío/error.
- Acciones rápidas según transición permitida.
- Diseño responsive y formato de impresión.
- No se añadieron migraciones ni envíos reales.

## 3.6. ETAPA 6 implementada

- Historial comercial real con última revisión y precio.
- Métricas mensuales y activas: total, enviadas, negociación, aceptadas y vencidas.
- Pestañas por estado y filtros por búsqueda, origen, asesor y canal.
- Paginación de resultados y diseño responsive.
- Edición y cancelación de borradores.
- Transiciones de estado controladas y atómicas.
- Acciones para negociación y aceptación solo desde estados compatibles.
- No se envía WhatsApp desde esta pantalla.
- No se añadieron migraciones.

## 3.5. ETAPA 5 implementada

- Formulario dedicado de creación desde la cola Por cotizar.
- Resumen real del cliente, ruta, accesos, fecha, inventario y motivo.
- Rango sugerido calculado por históricos o reglas de fallback existentes.
- Precio final, costo, margen mínimo, condiciones, vigencia y nota interna.
- Validación de precio positivo y bloqueo bajo margen.
- Excepción bajo margen visible únicamente para superusuario Administrador.
- Snapshot completo del servicio guardado en cada revisión.
- Un borrador comercial por solicitud; cada guardado posterior crea una revisión nueva.
- Vista previa editable del mensaje de WhatsApp.
- Guardar borrador no envía WhatsApp ni marca la revisión como enviada.
- No se añadieron migraciones.

## 3.4. ETAPA 4 implementada

- Cola real de solicitudes pendientes y en proceso.
- Métricas de pendientes, urgentes y creadas hoy.
- Búsqueda por cliente, teléfono y ruta.
- Filtros por asesor, prioridad, motivo y canal.
- Información recopilada, tiempo de espera, asignación y paginación.
- Toma atómica que sincroniza solicitud, lead y conversación.
- Bloqueo si otro asesor ya tomó la solicitud.
- Botón Cotizar enlaza temporalmente al detalle comercial existente; ETAPA 5 lo reemplazará con el formulario dedicado.
- No se añadieron migraciones.

## 3.3. ETAPA 3 implementada

- Bandeja responsive de tres columnas: lista, chat y ficha del servicio.
- Búsqueda y filtros reales por estado, canal y asesor.
- Historial normalizado con fallback de lectura para conversaciones legacy.
- Acciones atómicas: tomar, devolver al bot, enviar a cotizar y cerrar.
- Respuesta manual registrada en historial normalizado y legacy.
- Bloqueo de toma simultánea por dos asesores y auditoría de transiciones.
- Cola de cotización deduplicada por lead.
- Cierre sincroniza la conversación y pausa los flags legacy del bot.
- No se añadieron migraciones en esta etapa.

- `apps/dashboard/templates/dashboard/base.html` contiene sidebar embebido, mientras `apps/dashboard/templates/dashboard/sidebar.html` y `apps/dashboard/views_sidebar.py` también definen navegación. Hay dos fuentes de verdad visual.
- `ConfiguracionBot` conserva días/horario legacy y también `BotSchedule`; ambos siguen activos mediante fallback.
- Existe configuración global y configuración por canal. Debe definirse precedencia explícita sin eliminar compatibilidad.
- `Lead.atencion_humana`, `Lead.bot_pausado` y `Lead.requiere_asesor` se actualizan desde varias funciones y vistas; transiciones duplicadas.
- `_marcar_atencion_humana()` solo cambia `atencion_humana`, mientras `_marcar_derivacion()` cambia cuatro campos. Estados pueden quedar incoherentes.
- `Conversacion.canal` solo admite el texto `whatsapp`; no referencia `WhatsAppChannel`.
- Una conversación se relaciona indirectamente con lead mediante cliente, problemático cuando el mismo cliente tiene varios leads.
- `_send_handoff_message()` usa atributo temporal `_handoff_sent`, no persistente; otro proceso/reintento puede reenviar.
- Logs de `apps/whatsapp/utils.py` incluyen teléfono completo y fragmentos de mensajes, contrario al nuevo requisito de minimización.
- APIs de configuración comprueban autenticación, pero no aplican roles granulares de Administrador/Supervisor/Asesor.
- `lead_action` está autenticada, pero no usa decorador de rol ni transición de dominio centralizada.
- La acción `release` solo limpia `atencion_humana`; puede dejar `bot_pausado` o `requiere_asesor` activos, por lo que “liberada” no siempre reactiva realmente el bot.
- El modo “Solo bot” actual no corresponde exactamente a “Cotización automática”; “Recopilar datos” no existe como modo propio.

## 5. Mapeo concreto hacia las seis pantallas

### 1. Conversaciones

Reutilizar:

- `Cliente`, campos estructurados de `Lead`, `WhatsAppChannel`, `EvidenciaWhatsapp`.
- Historial actual de `Conversacion` durante transición.
- Acciones `take_over`, `release`, `manual_reply` como comportamiento de referencia.
- Base visual y componentes de `leads.html`.

Adaptar/crear en ETAPA 1 y 3:

- Entidad o evolución de conversación/sesión ligada a canal, cliente y lead.
- Mensaje individual con autor, tipo, estado Meta, timestamps y error.
- Responsable activo y transferencia atómica.
- Estados separados y servicio central de transiciones.
- Contadores, búsqueda, filtros, espera y resumen.

### 2. Por cotizar

Reutilizar:

- `Lead`, `requiere_asesor`, `motivo_derivacion`, prioridad, canal, asesor y cálculo de completitud de `apps/dashboard/views.py`.
- `evaluar_mixto_inteligente()` como base de reglas.

Adaptar/crear:

- Estado/entidad de solicitud de cotización con restricción de pendiente único por conversación/lead.
- Motivo normalizado, ingreso/salida de cola y tiempos.
- No duplicar mensajes ni funcionar como bandeja secundaria.

### 3. Crear cotización

Reutilizar:

- Ficha `Lead`, evidencias, `_find_similar_services()`, `cotizar_lead()` y recomendación actual.
- Mensaje generado por `_default_quote_message()` solo como punto de partida.

Adaptar/crear:

- Cotización comercial versionada, borrador, snapshot JSON inmutable, condiciones, vigencia, costos/margen y autoría.
- Servicio transaccional para guardar/enviar y sacar de cola.
- Validación de margen y permiso de excepción.

### 4. Cotizaciones

Reutilizar:

- `Cotizacion` técnica como cálculo asociado, no como historial comercial completo.
- `Lead` y `WhatsAppChannel` para filtros.

Adaptar/crear:

- Estados comerciales, código, origen bot/asesor, revisión, fechas y acciones válidas.
- Registrar automática y manual con mismo modelo comercial.

### 5. Detalle de cotización

Reutilizar:

- Snapshot comercial propuesto, lead, cliente, evidencias y mensajes.

Adaptar/crear:

- Revisiones inmutables, timeline, historial de estado, envíos/reenvíos y auditoría.
- Nueva revisión para cambios comerciales; nunca editar enviada.

### 6. Configuración del bot

Reutilizar:

- Pantalla `dashboard/whatsapp.html`.
- `WhatsAppChannel`, `ConfiguracionBot`, `BotSchedule` y APIs actuales.

Adaptar/crear:

- Modos: solo asesor, recopilar datos, cotización automática e híbrido.
- Zona horaria, reglas, confianza, margen, espera, seguimiento y plantillas.
- Permisos de Administrador y ocultación consistente de identificadores sensibles.
- Mantener configuración actual mediante migración de valores, sin cambiar canales reales automáticamente.

## 6. Modelado nuevo mínimo propuesto para ETAPA 1

Diseño sujeto a aprobación; nombres finales se validarán contra migraciones:

- Evolucionar `Conversacion` o crear una entidad de sesión de atención cuando mantener compatibilidad lo exija. Debe ligar cliente, lead, canal, responsable y estados separados.
- Crear mensaje individual normalizado, conservando lectura del historial legacy.
- Crear evento de auditoría append-only.
- Evolucionar `Cotizacion` o separar cálculo técnico de cotización comercial versionada. Preferencia: conservar la tabla actual como cálculo y añadir modelo comercial, evitando romper APIs existentes.
- Crear registro persistente de envío/status/reintento.
- Centralizar cambios en servicios de dominio con `transaction.atomic()` y `select_for_update()`.
- Añadir restricciones condicionales para un responsable/pendiente activo y revisión única.

## 7. Riesgos técnicos

1. Árbol Git muy sucio: mezclar cambios nuevos con trabajo previo dificulta revisión y rollback.
2. Suite base no está verde: 161 pruebas ejecutadas; 151 pasan, 9 fallan y 1 termina en error.
3. SQLite limita pruebas reales de concurrencia; bloqueo definitivo debe validarse también en PostgreSQL.
4. Historial `Conversacion` no distingue mensajes individuales ni lead/canal; migración requiere compatibilidad y backfill cuidadoso.
5. Estados distribuidos en vistas, webhook, IA y utilidades; corregir solo una ruta dejaría inconsistencias.
6. Envío a Meta y cambios locales no tienen outbox transaccional; puede existir estado local distinto al remoto.
7. Regla idempotente elimina la reserva si ocurre error, permitiendo reintento, pero no registra intentos/error persistente.
8. Datos sensibles aparecen completos en algunos logs.
9. Configuración y canales carecen de autorización granular.
10. El catch-all de `config/urls.py` redirige rutas desconocidas y puede ocultar errores 404 durante desarrollo.

## 8. Resultado de validación

Comandos ejecutados:

```powershell
.\.venv\Scripts\python.exe manage.py showmigrations whatsapp leads clientes cotizador
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test apps.whatsapp apps.cotizador apps.leads apps.clientes apps.dashboard --verbosity 1
```

Resultados:

- Todas las migraciones existentes de esos módulos están aplicadas.
- `makemigrations --check --dry-run`: `No changes detected`.
- `manage.py check`: sin problemas.
- Suite dirigida: 161 pruebas; 151 pasan, 9 fallan, 1 error.

Fallos observados:

- Error: `IntegrationBotConfigWebhookTests.test_fuera_horario_marca_lead_como_humano` espera `human_takeover` y la respuesta actual no lo incluye en ese escenario.
- Tres fallos de selección/cambio de canal reciben 302 en lugar de 200.
- Cotizador: ponderación reciente esperada 17.0, obtenida 15.3.
- Dashboard: falta `chat-timeline` esperado.
- Redirección root autenticada termina en login en vez de leads en el test.
- Dos pruebas esperan texto legacy `Panel Comercial` ya ausente.
- Servicios devuelve 403 para el usuario usado por la prueba.

No se corrigieron durante ETAPA 0 porque la tarea exige auditoría sin cambios funcionales.

## 9. Plan por etapas

| Etapa | Estado | Entregable |
|---|---|---|
| 0. Auditoría | Terminada | Este documento, mapa real y validación base |
| 1. Base de datos y estados | Terminada | Modelos aditivos, transiciones atómicas, permisos base, auditoría y pruebas |
| 2. Menú y rutas base | Terminada | Grupo WhatsApp, cuatro rutas, permisos y vistas base con datos reales |
| 3. Conversaciones | Terminada | Bandeja, chat, ficha y control atómico |
| 4. Por cotizar | Terminada | Cola deduplicada y asignable |
| 5. Crear cotización | Terminada | Borrador, snapshot, margen y vista previa |
| 6. Cotizaciones | Terminada | Historial, estados, filtros y acciones |
| 7. Detalle | Terminada | Revisiones, timeline y auditoría |
| 8. Configuración | Terminada | Cuatro modos y reglas por canal |
| 9. Integración real | Terminada | Status, archivos, reintentos y flujo completo |
| 10. Pruebas completas | Parcial | 387/388; queda una prueba horaria no determinista |

## 10. Archivos modificados

- `apps/whatsapp/models.py`
- `apps/whatsapp/domain.py`
- `apps/whatsapp/admin.py`
- `apps/whatsapp/tests_stage1.py`
- `apps/cotizador/models.py`
- `apps/cotizador/commercial.py`
- `apps/cotizador/admin.py`
- `apps/cotizador/tests_stage1.py`
- `apps/dashboard/permissions.py`
- `apps/dashboard/views.py`
- `apps/dashboard/urls.py`
- `apps/dashboard/context_processors.py`
- `apps/dashboard/views_sidebar.py`
- `apps/dashboard/templates/dashboard/base.html`
- `apps/dashboard/templates/dashboard/whatsapp_module_base.html`
- `apps/dashboard/tests_whatsapp_stage2.py`
- `apps/dashboard/views_whatsapp.py`
- `apps/dashboard/templates/dashboard/whatsapp_conversations.html`
- `apps/dashboard/tests_whatsapp_stage3.py`
- `apps/dashboard/views_quotes.py`
- `apps/dashboard/templates/dashboard/whatsapp_quote_queue.html`
- `apps/dashboard/tests_whatsapp_stage4.py`
- `apps/dashboard/templates/dashboard/whatsapp_quote_create.html`
- `apps/dashboard/tests_whatsapp_stage5.py`
- `apps/dashboard/views_quote_history.py`
- `apps/dashboard/templates/dashboard/whatsapp_quote_history.html`
- `apps/dashboard/tests_whatsapp_stage6.py`
- `apps/dashboard/templates/dashboard/whatsapp_quote_detail.html`
- `apps/dashboard/tests_whatsapp_stage7.py`
- `apps/dashboard/views_bot_config.py`
- `apps/dashboard/templates/dashboard/whatsapp_bot_config.html`
- `apps/dashboard/tests_whatsapp_stage8.py`
- `apps/dashboard/tests_whatsapp_stage9.py`
- `apps/cotizador/delivery.py`
- `apps/whatsapp/status.py`
- `apps/whatsapp/management/commands/reintentar_envios_whatsapp.py`
- `docs/WHATSAPP_IMPLEMENTATION_STATUS.md`

Migraciones creadas:

- `whatsapp/0009_conversacionwhatsapp_auditoriawhatsapp_and_more.py`
- `whatsapp/0010_backfill_conversaciones_whatsapp.py`
- `whatsapp/0011_configuracionbot_asesor_predeterminado_and_more.py`
- `cotizador/0007_cotizacioncomercial_revisioncotizacion_and_more.py`
- `cotizador/0008_solicitudcotizacion_conversacion_and_more.py`
- `cotizador/0009_enviocotizacion_leido_en_and_more.py`

Todas aplicadas correctamente en SQLite local.

## 11. Última validación de ETAPA 1

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test apps.whatsapp.tests_stage1 apps.cotizador.tests_stage1
.\.venv\Scripts\python.exe manage.py test apps.whatsapp apps.cotizador apps.dashboard
```

Resultados:

- Pruebas nuevas: 9/9 pasan.
- Pruebas críticas nuevas + integración legacy: 12/12 pasan.
- Suite WhatsApp, cotizador y dashboard: 164 pruebas; conserva exactamente 9 fallos y 1 error ya documentados en ETAPA 0.
- Suite global excedió el límite operativo de 120 segundos por logging DEBUG; no produjo una conclusión final.
- `manage.py check`: correcto.
- `makemigrations --check --dry-run`: sin cambios pendientes.

## 12. Próximo paso exacto

1. Abrir una cotización en borrador y pulsar Enviar por WhatsApp.
2. Confirmar recepción y estados entregado/leído usando Meta real.
3. Confirmar recepción de audio, documento y ubicación.
4. Iniciar ETAPA 10 después de la validación real.

## 13. Validación de ETAPA 2

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test apps.dashboard.tests_whatsapp_stage2
```

Resultados:

- Pruebas de ETAPA 2: 7/7 pasan.
- Cuatro rutas verificadas con usuario Administrador: HTTP 200.
- `manage.py check`: correcto.
- Migraciones nuevas: ninguna.
- Verificación visual automatizada no disponible por fallo interno de conexión al navegador integrado; render HTML, permisos, contenido real y respuesta HTTP sí quedaron verificados.

## 14. Validación de ETAPA 3

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test apps.whatsapp.tests_stage1 apps.cotizador.tests_stage1 apps.dashboard.tests_whatsapp_stage2 apps.dashboard.tests_whatsapp_stage3
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
git diff --check
```

Resultados:

- Pruebas acumuladas de ETAPAS 1–3: 23/23 pasan.
- Pruebas específicas de Conversaciones: 7/7 pasan.
- `manage.py check`: correcto.
- Migraciones pendientes: ninguna.
- `git diff --check`: correcto; solo avisos de conversión LF/CRLF del entorno Windows.

## 15. Validación de ETAPA 4

- Pruebas acumuladas de interfaz ETAPAS 2–4: 20/20 pasan.
- Pruebas específicas de Por cotizar: 6/6 pasan.
- `manage.py check`: correcto.
- Migraciones pendientes: ninguna.
- `git diff --check`: correcto; solo avisos LF/CRLF de Windows.

## 16. Validación de ETAPA 5

- Pruebas focalizadas de dominio, cola y formulario: 16/16 pasan.
- Pruebas específicas de Crear cotización: 7/7 pasan.
- `manage.py check`: correcto.
- Migraciones pendientes: ninguna.
- Guardado probado sin llamadas a Meta WhatsApp.

## 17. Validación de ETAPA 6

- Pruebas acumuladas de interfaz ETAPAS 2–6: 33/33 pasan.
- Pruebas específicas de Cotizaciones: 6/6 pasan.
- `manage.py check`: correcto.
- Migraciones pendientes: ninguna.
- Transiciones inválidas rechazadas sin modificar datos.

## 18. Validación de ETAPA 7

- Pruebas acumuladas de interfaz ETAPAS 2–7: 39/39 pasan.
- Pruebas específicas de Detalle: 6/6 pasan.
- `manage.py check`: correcto.
- Migraciones pendientes: ninguna.
- Intentos y errores se muestran sin reintentar ni contactar Meta.

## 19. Validación de ETAPA 8

- Pruebas acumuladas de interfaz ETAPAS 2–8: 45/45 pasan.
- Pruebas focalizadas de configuración y compatibilidad: 17/17 pasan.
- `manage.py check`: correcto.
- `makemigrations --check --dry-run`: sin cambios pendientes.
- Migración aplicada; cinco configuraciones existentes preservadas y mapeadas.

## 20. Validación de ETAPA 9

- Pruebas acumuladas de interfaz ETAPAS 2–9: 50/50 pasan.
- Envío aceptado, error persistente, programación de reintento y estados Meta probados.
- Extracción de documento y ubicación probada.
- `manage.py check`: correcto.
- `makemigrations --check --dry-run`: sin cambios pendientes.
- Migración `cotizador.0009` aplicada correctamente.

## 21. Validación de ETAPA 10

- Suite global ejecutada después de correcciones: 388 pruebas; 387 pasan y queda 1 error legacy dependiente del reloj real.
- Etapas WhatsApp 2–9: 50/50 pasan.
- Cuatro pantallas principales verificadas autenticadas: HTTP 200.
- Responsive verificado por reglas CSS en todas las pantallas nuevas.
- El navegador integrado no pudo conectarse por un fallo interno del entorno; no se obtuvo captura automatizada.
- Corregidos: Pizarra (6), dashboard legacy (5), selector de canal legacy (3) y ponderación histórica del cotizador (1).
- Error restante: `test_fuera_horario_marca_lead_como_humano` configura 09:00–18:00 pero usa la hora real; durante esta ejecución estaba dentro del horario.
- No se modificaron pruebas existentes ni se alteró la lógica productiva correcta para satisfacer una expectativa horaria contradictoria.
- `manage.py check`: correcto; migraciones pendientes: ninguna.
