# FASE 5A: Análisis de Contador No Leído

---

## Conv 180 (Walter Escobar)

| Métrica | Valor | Estado |
|---------|-------|--------|
| Total mensajes entrantes | 59 | ✅ |
| Mensajes del customer | 59 | ✅ (todos son del customer) |
| Último mensaje | ID 749 (probando7) | ✅ |
| Read state (testadmin) | last_read_message_id=749 | ✅ |
| Read state timestamp | 2026-08-21 17:33:27 | ✅ |
| **Unread calculado** | **0** | ✅ TODO LEÍDO |

**Conclusión**: Conv 180 tiene unread=0. Todos los mensajes inbound fueron marcados como leídos por testadmin.

---

## Conv 201

| Métrica | Valor | Estado |
|---------|-------|--------|
| Total mensajes entrantes | 5 | ✅ |
| Mensajes del customer | 5 | ✅ |
| Último mensaje | ID 683 (2026-08-21 15:51) | ✅ |
| Read state | SIN ENTRADA | ⚠️ |
| **Unread calculado** | **5** | ⚠️ NO LEÍDO |

**Conclusión**: Conv 201 no tiene registro de lectura → **unread=5** (todos los inbound sin leer).

**Deuda técnica**: El modelo de lectura requiere que exista un registro en `conversationreadstate` para que el endpoint calcule unread. Si no existe el registro, se asume "no leído".

---

## Reglas Validadas

| Regla | Prueba | Resultado |
|-------|--------|-----------|
| Solo inbound incrementa | Conv 180 tiene 59 inbound, 53 outbound | ✅ Solo conté entrante |
| Mismo wamid no reincrementa | Idempotencia verificada en FASE 4 | ✅ |
| Bot no incrementa | Conv 180 tiene msgs bot | ✅ No incluidos en entrante |
| Echo no incrementa | Conv 201 tiene 6 echoes | ✅ No incluidos en entrante |
| Sin marcar leído aún → unread | Conv 201 sin read_state | ✅ unread=5 |

---

## Modelo Actual

- ✅ Existe tabla `conversationreadstate` (per-user, per-conversation)
- ✅ `last_read_message_id` indica hasta dónde leyó el usuario
- ✅ Mensajes después de `last_read_message_id` = "no leído"
- ✅ Inbound del customer = incrementan potencialmente
- ✅ Outbound (bot, advisor, system) = no incrementan

---

## Limitaciones Actuales

1. **No existe tracking per-message**: No hay campo `read_at` en cada MensajeWhatsApp
   - Solo existe `last_read_message_id` de la conversación
   - No se distingue "leído por asesor A" vs "leído por asesor B"

2. **No existe "marcar como leído al abrir"** (FASE 5C)
   - Los mensajes se marcan cuando se carga `conversation_messages` endpoint
   - No se actualiza en real-time al hacer scroll

3. **No existe notificación de "nuevos mensajes"**
   - Sin SSE/WebSocket, no hay push en tiempo real

---

## Validación de Cálculo

```
unread_count(conversation, user) = 
  COUNT(
    MensajeWhatsApp
    WHERE conversacion = conversation
    AND direccion = 'entrante'
    AND sender_type = 'customer'
    AND id > last_read_message_id(conversation, user)
  )
```

✅ **Implementable**: Sí, lógica es válida
✅ **Precisa**: Sí, cuenta únicamente inbound del customer
✅ **Idempotente**: Sí, no afecta por reproceso

---

## Próximas Fases

- FASE 5C: Implementar mark_as_read_on_load
- FASE 5D: Agregar SSE para notificaciones
- Consideración: Agregar tracking per-message (opcional)

