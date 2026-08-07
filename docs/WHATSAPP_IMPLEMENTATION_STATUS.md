# Estado de implementación del módulo WhatsApp

Última actualización: 2026-08-07  
Etapa actual: ETAPA 0 — Auditoría terminada  
Próximo paso: corregir primero la suite base y, tras aprobación, diseñar ETAPA 1 sin duplicar `Cliente`, `Lead`, `WhatsAppChannel`, `Conversacion`, `Cotizacion` ni `ServicioHistorico`.

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

### No implementada

- Bandeja compartida de tres columnas con filtros, no leídos y espera.
- Cola única “Por cotizar” con deduplicación explícita.
- Crear cotización con borrador, snapshot inmutable, margen, condiciones y vista previa.
- Historial comercial de cotizaciones y detalle con revisiones.
- Auditoría de transferencias, cambios, autorizaciones y envíos.
- Estados de entrega de Meta y webhook de status.
- Reintentos salientes persistentes.
- Bloqueo atómico para evitar dos asesores activos.
- Permiso especial para precio bajo margen.

## 4. Duplicaciones, inconsistencias y código sin uso claro

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
| 1. Base de datos y estados | Pendiente | Modelos mínimos, transiciones, permisos, auditoría y pruebas |
| 2. Menú y rutas base | Pendiente | Grupo WhatsApp y cuatro entradas con datos reales |
| 3. Conversaciones | Pendiente | Bandeja, chat, ficha y control atómico |
| 4. Por cotizar | Pendiente | Cola deduplicada y asignable |
| 5. Crear cotización | Pendiente | Borrador, snapshot, margen y envío |
| 6. Cotizaciones | Pendiente | Historial, estados, filtros y acciones |
| 7. Detalle | Pendiente | Revisiones, timeline y auditoría |
| 8. Configuración | Pendiente | Cuatro modos y reglas por canal |
| 9. Integración real | Pendiente | Status, archivos, reintentos y flujo completo |
| 10. Pruebas completas | Pendiente | Suite verde, E2E y verificación visual |

## 10. Archivos modificados en esta etapa

- `docs/WHATSAPP_IMPLEMENTATION_STATUS.md`: creado.

Migraciones creadas: ninguna.  
Cambios funcionales: ninguno.  
Registros modificados: ninguno.

## 11. Próximo paso exacto

Tras aprobación de ETAPA 0:

1. Corregir o clasificar los 10 problemas de la suite base antes de alterar modelos.
2. Definir esquema de compatibilidad para conversación/mensaje y cotización comercial.
3. Implementar ETAPA 1 con migraciones aditivas, transiciones atómicas, auditoría y pruebas críticas.
4. Detenerse al terminar ETAPA 1 y entregar migraciones, comandos y resultados antes de crear pantallas.
