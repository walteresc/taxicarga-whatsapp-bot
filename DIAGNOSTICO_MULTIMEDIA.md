# DIAGNÓSTICO: SOPORTE MULTIMEDIA EN CHAT

**Fecha:** 2026-08-19  
**Estado:** CRÍTICO - Archivos multimedia no se muestran en el CRM

## 1. HALLAZGOS PRINCIPALES

### 1.1 Problema Identificado
Los archivos multimedia (imágenes, audio, video, documentos) se reciben en el webhook pero **NO aparecen en el chat del CRM**.

### 1.2 Razón Raíz
El flujo está dividido en dos sistemas sin conexión:

```
Webhook → Procesa multimedia → Guarda en EvidenciaWhatsapp
                            ↓
                      Crea Conversacion
                      (solo texto)
                            ↓
                      API retorna solo Conversacion
                            ↓
                      Vue muestra solo mensajes de texto
```

## 2. ANÁLISIS DEL CÓDIGO ACTUAL

### 2.1 Webhook (apps/whatsapp/views.py)

**Líneas 107-139:** El webhook SÍ procesa multimedia

```python
if event["type"] == "image":
    response = _receive_image(cliente, active_lead, event)
    return response

if event["type"] in {"audio", "document"}:
    result = download_whatsapp_media(cliente, active_lead, event)
    label = "[Audio recibido]" if event["type"] == "audio" else "[Documento recibido]"
    if event.get("caption"):
        label += f" {event['caption']}"
    Conversacion.objects.create(
        cliente=cliente, mensaje_entrada=label, mensaje_salida="",
        canal=Conversacion.CANAL_WHATSAPP,
    )
    return JsonResponse({"ok": True, "media_saved": result.get("saved", False)})
```

**Problema:** 
- Crea un mensaje con texto placeholder "[Audio recibido]"
- NO guarda referencia al archivo descargado
- NO guarda media_id, mime_type, filename, etc.

### 2.2 Modelo de Conversacion (apps/clientes/models.py)

```python
class Conversacion(models.Model):
    cliente = models.ForeignKey(Cliente, ...)
    mensaje_entrada = models.TextField(blank=True)     # ← Solo texto
    mensaje_salida = models.TextField(blank=True)       # ← Solo texto
    canal = models.CharField(...)
    fecha = models.DateTimeField(auto_now_add=True)
```

**Faltan campos:** media_id, media_url, media_type, mime_type, filename, media_status, caption, wamid, direction, sender_type

### 2.3 Modelo EvidenciaWhatsapp (apps/whatsapp/models.py)

```python
class EvidenciaWhatsapp(models.Model):
    cliente = models.ForeignKey(Cliente, ...)
    lead = models.ForeignKey(Lead, ...)
    media_id = models.CharField(max_length=160, unique=True)
    archivo = models.FileField(upload_to="whatsapp/%Y/%m/")
    mime_type = models.CharField(max_length=100)
    sha256_meta = models.CharField(max_length=128, blank=True)
    caption = models.TextField(blank=True)
    analisis_visual = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
```

**Problema:** 
- Está desconectado de Conversacion
- Solo almacena "evidencia" (fotos para análisis visual)
- No se usa para imágenes del chat
- No tiene referencia a conversación

### 2.4 Servicios (apps/whatsapp/services.py)

**Funciones existentes:**
- `download_whatsapp_image()` - Descarga imagen
- `download_whatsapp_media()` - Descarga audio/documento
- `send_whatsapp_message()` - Envía texto

**Problema:** 
- Los archivos se descargan pero la referencia se pierde
- No hay persistencia en BD de dónde está el archivo

## 3. FLUJO ACTUAL vs REQUERIDO

### 3.1 Flujo Actual (Roto)

```
1. YCloud webhook → apps/whatsapp/views._receive_message()
2. Extrae event["type"], event["media_id"], event["link"]
3. Si type == "image" → _receive_image() → descarga → EvidenciaWhatsapp
4. Si type == "audio"|"document" → download_whatsapp_media() → descarga → (sin guardar dónde)
5. Crea Conversacion con mensaje_entrada = "[Audio recibido]"
6. API retorna Conversacion (sin referencia al archivo)
7. Vue recibe solo texto → muestra "[Audio recibido]" sin archivo
```

### 3.2 Flujo Requerido

```
1. YCloud webhook → handler
2. Guarda mensaje con TODOS los metadatos en BD
3. Responde HTTP 200 inmediatamente
4. Descarga archivo en background (si existe worker)
5. Actualiza estado de descarga
6. API retorna mensaje completo (texto + media)
7. Vue renderiza según type (image, video, audio, document, etc.)
```

## 4. ESTADO DEL ALMACENAMIENTO

### 4.1 Media Descargadas
- **Ubicación:** `whatsapp/YYYY/MM/` (según `EvidenciaWhatsapp.archivo`)
- **Almacenamiento:** MEDIA_ROOT (desarrollo) o S3 (producción)
- **Organización:** Plana, sin relación a conversación

### 4.2 Base de Datos
- Tabla `clientes_conversacion`: Solo texto
- Tabla `whatsapp_evidenciawhatsapp`: Solo imágenes para análisis
- **Falta:** Tabla/modelo para mensajes multimedia genéricos

## 5. SEGURIDAD ACTUAL

### 5.1 YCloud API Key
- Ubicación: `settings.YCLOUD_API_KEY` (Django settings)
- Uso: En `download_whatsapp_image()` y `download_whatsapp_media()`
- **Riesgo:** No aparece en logs normales, pero necesita verificación

### 5.2 URLs de Descargas
- YCloud proporciona: `image.link`, `video.link`, `document.link`
- Tiempo de expiración: Desconocido (típicamente 15-60 minutos en Meta)
- **Problema:** URLs temporales no se guardan en BD

## 6. PLAN DE IMPLEMENTACIÓN

### Fase A: Modelo Extendido (Crítico)
1. Crear modelo `MensajeMultimedia` o extender `Conversacion`
2. Campos requeridos:
   - message_type (text, image, video, audio, document, sticker, location)
   - media_id (YCloud ID)
   - media_url (URL de descarga local)
   - media_status (pending, downloading, ready, failed)
   - mime_type
   - filename
   - file_size
   - caption
   - wamid (WhatsApp message ID)
   - direction (inbound/outbound)
   - sender_type (customer/bot/advisor)

### Fase B: Webhook Mejorado
1. Cambiar handler para guardar mensaje antes de descargar
2. Responder HTTP 200 inmediatamente
3. Implementar descarga en background

### Fase C: Descarga Segura
1. Crear servicio de descarga con validación
2. Implementar reintentos
3. Guardar estado en BD

### Fase D: API
1. Actualizar serializer para retornar media
2. Endpoint autenticado para descargas

### Fase E: Vue
1. Crear componentes por tipo (ImageMessage, VideoMessage, etc.)
2. Mostrar media en chat

## 7. IMPACTO

- **Usuarios afectados:** Todos (no ven fotos, audios, videos)
- **Datos que se pierden:** Referencias a archivos (los archivos se descargan pero se pierden en BD)
- **Migración necesaria:** Sí, cambio importante de modelo

## 8. PRÓXIMOS PASOS

1. ✅ Diagnóstico completado
2. ⏳ Crear migración para extender Conversacion
3. ⏳ Modificar webhook handler
4. ⏳ Implementar descarga segura
5. ⏳ Actualizar API
6. ⏳ Crear componentes Vue
7. ⏳ Testing completo

---

**Clasificación:** BLOQUEADOR - Impide visualización de multimedia en chat
**Complejidad:** ALTA - Requiere cambios en modelo, webhook, API y frontend
**Tiempo estimado:** 16-20 horas
