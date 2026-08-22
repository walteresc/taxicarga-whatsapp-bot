# FASE 5A: Auditoría ANTES de reparación

**Fecha**: 2026-08-21
**Objetivo**: Documentar estado antes de validación/reparación

---

## 1. WALTER ESCOBAR - Estado ANTES

### Identidad

| Campo | Valor |
|-------|-------|
| Cliente canónico ID | 77 |
| Nombre | Walter Escobar |
| Teléfono canónico | +51995403320 |
| Duplicados encontrados | ID 90, ID 106 |

### Duplicados

| ID | Nombre | Teléfono |
|----|--------|----------|
| 77 | Walter Escobar | +51995403320 |
| 90 | TEST Stage 7 | +51995403320-v2 |
| 106 | (vacío) | 51995403320-v3 |

**Acción necesaria**: Considerar fusión controlada (no borrar físicamente)

### Conversaciones

| ID | Mensajes | UA | Último wamid | Último contenido |
|----|-----------|----|--------------|------------------|
| 180 | 112 | 2026-08-21 17:32:28 | 6a888bab40b5af25accb27a7 | probando7 |
| 66 | 214 | 2026-08-18 23:18:41 | (verificar) | Tu número de DNI? |
| 47 | 105 | 2026-08-14 16:26:23 | wamid.HBgL... | Hola, necesito presupuesto... |

### Conv 180 - Mensajes "probando"

| ID | Timestamp | Dirección | Sender | Source | Contenido |
|----|-----------|-----------|---------|---------|-----------| 
| 668 | 2026-08-21 14:52:21 | entrante | customer | whatsapp_api | probando4 |
| 672 | 2026-08-21 15:31:16 | entrante | customer | whatsapp_api | probando5 |
| 748 | 2026-08-21 17:27:23 | entrante | customer | whatsapp_customer | probando6 |
| 749 | 2026-08-21 17:32:28 | entrante | customer | whatsapp_customer | probando7 |

**Observación**: `probando4-5` tienen source=whatsapp_api (historico), `probando6-7` son whatsapp_customer (correcto)

---

## 2. CONVERSACIÓN 201 - Estado ANTES

### Identidad

| Campo | Valor |
|-------|-------|
| Conv ID | 201 |
| Cliente ID | 141 |
| Teléfono | +51965162906 |
| Nombre cliente | (vacío) |
| Total mensajes | 12 |
| UA | 2026-08-21 15:52:41 |

### Estructura de Mensajes

| ID | Hora | Dirección | Sender | Source | Estado |
|----|----|-----------|--------|--------|--------|
| 673 | 15:40:51 | entrante | customer | whatsapp_customer | recibido |
| 674 | 15:41:08 | **saliente** | **advisor** | **whatsapp_business_app** | enviado |
| 675 | 15:41:10 | saliente | bot | bot | enviado |
| 676 | 15:41:13 | saliente | advisor | whatsapp_business_app | enviado |
| 677 | 15:41:37 | saliente | advisor | whatsapp_business_app | enviado |
| 678 | 15:41:40 | entrante | customer | whatsapp_customer | recibido |
| 679 | 15:41:41 | saliente | advisor | whatsapp_business_app | enviado |
| 680 | 15:43:47 | entrante | customer | whatsapp_customer | recibido |
| 681 | 15:44:26 | entrante | customer | whatsapp_customer | recibido |
| 682 | 15:49:18 | saliente | advisor | whatsapp_business_app | enviado |
| 683 | 15:51:23 | entrante | customer | whatsapp_customer | recibido |
| 684 | 15:52:41 | **saliente** | **advisor** | **whatsapp_business_app** | enviado |

**Estructura observada**:
- Mensajes 674, 676, 677, 679, 682, 684 = echoes (advisor via WhatsApp Business App)
- Mensaje 675 = respuesta bot (no interactúa)
- Mensajes 673, 678, 680, 681, 683 = inbound del cliente

**Validación**: ✅ Estructura canónica correcta
- Inbound: customer | whatsapp_customer
- Echo: advisor | whatsapp_business_app
- Bot: bot | bot

**Validación estado_atencion**: Estado='bot', pero recibió echos (takeover) — verificar si debe cambiar a 'advisor'

---

## 3. APIs EXISTENTES

### Endpoint: /dashboard/whatsapp/conversaciones/api/active/

**Estado**: ✅ Implementado

**Contrato**:
```json
{
  "conversations": [
    {
      "id": 201,
      "name": "Cliente Name",
      "phone": "+51965162906",
      "preview": "Último mensaje (100 chars)",
      "unread_count": 2,
      "last_activity": "2026-08-21T15:52:41+00:00",
      "estado_atencion": "bot|advisor|waiting",
      "estado_cotizacion": "...",
      "lead_id": 12,
      ...
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 25,
    "total": N,
    "has_next": false
  }
}
```

**Validación necesaria**:
- ¿preview derivado de último mensaje? ✓ (código lo hace)
- ¿last_activity = ultima_actividad? ✓ (código lo hace)
- ¿Ordenado por -last_activity? ⚠️ (verificar en consulta SQL)

### Endpoint: /dashboard/whatsapp/conversaciones/<id>/mensajes/

**Estado**: ✅ Implementado

**Contrato**:
```json
{
  "messages": [
    {
      "id": 673,
      "sender": "customer",
      "source": "whatsapp_customer",
      "badge": "customer",
      "text": "Contenido mensaje",
      "timestamp": "2026-08-21T15:40:51+00:00",
      "status": "recibido"
    }
  ],
  "total": 12,
  "conversation_id": 201
}
```

**Validación necesaria**:
- ¿Orden ASC por fecha_mensaje? ✓ (código lo hace)
- ¿sender_type y source canónicos? ✓ (código lo hace)
- ¿Marca como leído automáticamente? ✓ (mark_conversation_as_read)

---

## 4. CONTADORES NO LEÍDOS

### Conv 201

**Consultando tabla actual**:
- `count_unread`: (necesita verificar de BD)

**Calculado desde mensajes**:
- Entrantes sin leer: (necesita verificar read_state)

**Acción**: Revisar `services_read_state.py` para entender tracking

---

## Próximas acciones

1. ✅ Auditoría completada (este documento)
2. ⏳ Comando de reparación seguro (dry-run)
3. ⏳ Validación de APIs (test real)
4. ⏳ Prueba controlada (fase5a-walter-1)
5. ⏳ Verificación post-reparación

