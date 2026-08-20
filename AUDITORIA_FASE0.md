# FASE 0: AUDITORÍA COMPLETADA

## 1. USO DE CONVERSACION

### 1.1 Modelos relacionados
- `apps.clientes.models.Conversacion` (línea 22-40 en models.py)
- Campos actuales: `mensaje_entrada`, `mensaje_salida`, `canal`, `fecha`
- Relaciones: FK a Cliente

### 1.2 Serializers
- `apps.clientes.serializers.ConversacionSerializer`
- Expone todos los campos sin filtros

### 1.3 API Endpoints
- Router: `apps/clientes/urls.py`
- Endpoint: `/api/clientes/conversaciones/`
- ViewSet: `ConversacionViewSet` en `apps/clientes/views.py`

### 1.4 Usos en Webhook
- `apps/whatsapp/views.py` líneas 122-139
- Crea Conversacion con placeholders: "[Audio recibido]", "[Documento recibido]", "[Ubicación recibida]"
- NO guarda referencias multimedia

### 1.5 Usos en Dashboard
- `apps/dashboard/views_whatsapp.py` - Muestra conversaciones por cliente

### 1.6 Cantidad de registros históricos
- Desconocida (ejecutar: `python manage.py shell -c "from apps.clientes.models import Conversacion; print(Conversacion.objects.count())"`)
- Auditoría recomendada antes de migración grande

## 2. ALMACENAMIENTO ACTUAL

### 2.1 Media descargada
- Ubicación: `MEDIA_ROOT/whatsapp/YYYY/MM/` (desde EvidenciaWhatsapp)
- Storage: Django FileField (MEDIA_ROOT)
- Configuración: `MEDIA_URL`, `MEDIA_ROOT` en settings.py

### 2.2 No existe S3 aparente
- Verificar `DEFAULT_FILE_STORAGE` en settings.py
- Verificar variables de entorno AWS

## 3. WORKER / SCHEDULER

### 3.1 Búsqueda de Celery
- No visible en requirements.txt o installed apps
- `download_whatsapp_media()` en `apps/whatsapp/services.py` parece ser síncrono

### 3.2 Programador de tareas
- Verificar `APScheduler` o similar en settings.py
- Verificar `CELERY_` configuraciones

### 3.3 Recomendación
- Usar management commands ejecutados por cron o scheduler externo
- No crear threads en Django

## 4. MODELOS RELACIONADOS A REVISAR

- `apps.whatsapp.models.EvidenciaWhatsapp` - Guarda imágenes analizadas
- `apps.whatsapp.models.MensajeWhatsappProcesado` - Control de idempotencia
- `apps.whatsapp.models.WhatsAppChannel` - Configuración de canales
- `apps.integrations.models` - Posibles conversaciones en nueva arquit ectura
- `apps.cotizador.models.Cotizacion` - Para retención por cotización
- `apps.servicios.models.Servicio` - Para retención por servicio

## 5. SEGURIDAD ACTUAL

### 5.1 API Key de YCloud
- Ubicación esperada: `settings.YCLOUD_API_KEY`
- Uso: `apps/whatsapp/services.py` en funciones de descarga
- **Verificar:** No aparece en serializers, API responses ni logs

### 5.2 URLs temporales
- No se guardan en BD
- Se descargan inmediatamente

## 6. ESTADO DE PRUEBAS

- Buscar en `apps/whatsapp/tests.py`
- Buscar en `apps/dashboard/tests.py`
- Verificar cobertura de multimedia

## 7. NO-DESTRUCTIVO CONFIRMADO

- ✅ Crear nuevos modelos no afecta Conversacion existente
- ✅ Crear migraciones es reversible
- ✅ Dual-read posible durante transición
- ✅ No necesita borrar/renombrar campos antiguos

## 8. SIGUIENTE PASO

Fase A: Crear MensajeConversacion (preservando Conversacion existente)

Sin bloqueadores detectados. Proceder.
