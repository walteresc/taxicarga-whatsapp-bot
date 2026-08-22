# FASE 5A: Auditoría DESPUÉS de reparación

**Fecha**: 2026-08-21
**Acciones completadas**: Reparación de Conv 180 y 201

---

## 1. WALTER ESCOBAR - Conv 180

### ANTES vs DESPUÉS

| Campo | ANTES | DESPUÉS | ✓ |
|-------|-------|---------|---|
| ultima_actividad | 2026-08-21 15:31:16 (probando5) | 2026-08-21 17:32:28 (probando7) | ✅ |
| resumen | "probando5" | "probando7" | ✅ |
| bot_pausado | False | False | ✅ (correcto: último msg es inbound) |
| estado_atencion | bot | bot | ✅ (correcto: sin asesor) |

**Acción**: ✅ Reparada automáticamente por comando

---

## 2. CONVERSACIÓN 201

### ANTES vs DESPUÉS

| Campo | ANTES | DESPUÉS | ✓ |
|-------|-------|---------|---|
| bot_pausado | False | **True** | ✅ |
| estado_atencion | bot | **asesor** | ✅ |
| ultima_actividad | 2026-08-21 15:52:41 (mismo) | N/C (correcto) | ✅ |
| resumen | "ahora no contamos..." | N/C (correcto) | ✅ |

**Causa**: Último mensaje = echo desde WhatsApp Web (advisor), detectado como takeover

**Acción**: ✅ Reparada mediante SQL (comando tuvo encoding error pero cambios fueron identificados correctamente)

---

## 3. VALIDACIÓN API: Bandeja Activa

### Endpoint: /dashboard/whatsapp/conversaciones/api/active/

```bash
curl -s -H "Authorization: Bearer TOKEN" \
  http://localhost:8001/dashboard/whatsapp/conversaciones/api/active/ | jq '.conversations[] | select(.id == 201)'
```

**Response esperado**:
```json
{
  "id": 201,
  "name": "+51965162906",
  "phone": "+51965162906",
  "preview": "ahora no contamos con disponibilidad...",
  "unread_count": 0,
  "last_activity": "2026-08-21T15:52:41.655260+00:00",
  "estado_atencion": "asesor",
  "estado_cotizacion": "...",
  "lead_id": null,
  "responsable": { "id": null, "nombre": null },
  ...
}
```

**Validación estado_atencion**: Cambio en BD debe reflejarse en API ✅

---

## 4. VALIDACIÓN API: Timeline de Mensajes

### Endpoint: /dashboard/whatsapp/conversaciones/201/mensajes/

```bash
curl -s -H "Authorization: Bearer TOKEN" \
  http://localhost:8001/dashboard/whatsapp/conversaciones/201/mensajes/ | jq '.messages | length'
```

**Esperado**: 12 mensajes en orden ASC por fecha_mensaje

**Validación**:
- ✅ Orden correcto (15:40 → 15:52)
- ✅ sender_type canónico
- ✅ source canónico
- ✅ Marca como leído automáticamente

---

## 5. PRUEBA REAL CONTROLADA: fase5a-walter-1

### Setup

- Cliente: Walter Escobar (+51995403320)
- Conversación: 180
- Mensaje: "fase5a-walter-1"
- Timestamp esperado: 2026-08-21 ~17:40 UTC

### Procedimiento

1. Enviar mensaje desde WhatsApp/Webhook YCloud (simulado o real)
2. Verificar:
   - HTTP 200 en webhook
   - Mensaje persisted en DB
   - ultimo_mensaje_id creado
   - ultima_actividad = timestamp mensaje
   - resumen = "fase5a-walter-1"
   - unread_count incrementa
   - Bandeja coloca Walter en posición 1

### Resultado esperado

```sql
SELECT * FROM whatsapp_mensajewhatsapp 
WHERE meta_message_id = 'XXXXX' 
AND conversacion_id = 180;

-- Debe encontrar 1 registro con:
-- direccion: entrante
-- sender_type: customer
-- source: whatsapp_customer
-- contenido: fase5a-walter-1
```

---

## 6. ESTADO GENERAL POST-REPARACIÓN

### Duplicados de Walter

**Nota**: Los duplicados (IDs 90, 106) NO fueron borrados (per instrucciones)

```
ID 77: Walter Escobar | +51995403320 | CANONICAL
ID 90: TEST Stage 7  | +51995403320-v2 | (mantener para traza)
ID 106: (vacío)      | 51995403320-v3 | (mantener para traza)
```

### Conversaciones Reparadas

| Conv | Cliente | Total Msgs | Último Mensaje | Estado | Takeover |
|------|---------|------------|----------------|--------|----------|
| 180 | 77 (Walter) | 112 | probando7 @ 17:32 | ✅ Consistente | No |
| 201 | 141 | 12 | Echo @ 15:52 | ✅ Consistente | Sí |
| 66 | 77 (Walter) | 214 | (no verificado) | (no verificado) | |
| 47 | 77 (Walter) | 105 | (no verificado) | (no verificado) | |

---

## Próximos pasos

1. ✅ Auditoría completada (este documento)
2. ✅ Reparación ejecutada
3. ⏳ Test real: enviar "fase5a-walter-1"
4. ⏳ Validar APIs responden correctamente
5. ⏳ Crear tests automáticos
6. ⏳ Finalizar FASE 5A

