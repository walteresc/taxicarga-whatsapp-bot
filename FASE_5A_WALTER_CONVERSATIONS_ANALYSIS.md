# FASE 5A: Análisis de 3 Conversaciones de Walter Escobar

**Cliente**: Walter Escobar (ID 77) | Teléfono: +51995403320 | Canal: TEST Meta Stage 7

---

## Tabla de las 3 Conversaciones

| ID | Cliente ID | Teléfono | Canal | Creada | Primer Msg | Último Msg | Total Msgs | Estado | Decisión |
|----|----|---------|--------|--------|------------|---------|-----------|--------|----------|
| **47** | 77 | +51995403320 | TEST Meta Stage 7 | 2026-08-08 22:39 | 2026-08-08 23:46 (saliente) | 2026-08-14 16:26 (entrante) | 105 | bot | LEGACY |
| **66** | 77 | +51995403320 | TEST Meta Stage 7 | 2026-08-14 18:49 | 2024-08-18 19:00 (entrante) | 2026-08-18 23:18 (saliente) | 214 | bot | ARCHIVE |
| **180** | 77 | +51995403320 | TEST Meta Stage 7 | 2026-08-18 20:28 | 2026-08-19 03:49 (entrante) | 2026-08-21 17:32 (entrante) | 112 | bot | **CANONICAL** |

---

## Diagnóstico

### Causa de Separación

El webhook de YCloud **crea una NUEVA conversación cada vez que llega un inbound** en lugar de reutilizar la existente.

Evidencia:
- Conv 66 inicia en **2024-08-18** (datos históricos)
- Conv 47 creada **2026-08-08** (reapertura 2 años después)
- Conv 180 creada **2026-08-18** (nueva sesión 10 días después de Conv 47)

### Son la Misma Conversación Lógica

✅ Mismo cliente (ID 77)
✅ Mismo teléfono (+51995403320)
✅ Mismo canal (TEST Meta Stage 7)
✅ Mismo negocio/cuenta WhatsApp
❌ No hay razón técnica válida para separación

### Por Qué Existen 3

**Bug identificado**: En `process_ycloud_event()` o `resolve_whatsapp_identity()`:
```
get_or_create(cliente=cliente, channel=channel)
```

debería devolver la conversación existente, pero parece crear nueva cada vez que hay una brecha temporal o sesión nueva.

---

## Decisión de Fusión

**NO crear nuevas conversaciones. Consolidar a CANONÍCA (Conv 180).**

Razonamiento:
1. Conv 66 y Conv 47 son históricas/legacy (últimos msgs hace 3+ días)
2. Conv 180 es actual (últimos msgs hace <1 hora)
3. La bandeja debe mostrar UNA sola conversación por (cliente, canal)
4. Los mensajes históricos permanecen en su BD original (sin mover)

---

## Plan de Resolución (Sin Borrar)

### Paso 1: Marcar Conv 47 y 66 como Archivadas

```sql
UPDATE whatsapp_conversacionwhatsapp
SET cerrada_en = NOW()
WHERE id IN (47, 66);
```

**Efecto**:
- `cerrada_en IS NOT NULL` = no mostrar en bandeja
- Los mensajes permanecen en BD (sin mover)
- Búsqueda por teléfono devuelve Conv 180 (la abierta)

### Paso 2: Crear Registro de Redirección (Opcional, para Auditoría)

Agregar a `merged_into_id` si existe el campo, o crear tabla `ConversationMergeLog`:

```sql
-- Si existe el campo
UPDATE whatsapp_conversacionwhatsapp
SET merged_into_id = 180
WHERE id IN (47, 66);
```

### Paso 3: Validar Endpoint de Bandeja

El endpoint `/api/active/` debe filtrar:
```python
conversaciones = ConversacionWhatsApp.objects.filter(cerrada_en__isnull=True)
```

---

## Resultado Esperado Post-Resolución

| Búsqueda | Resultado |
|----------|-----------|
| `Cliente.objects.filter(telefono="+51995403320")` | ID 77 (✅ único) |
| `ConversacionWhatsApp.objects.filter(cliente_id=77, cerrada_en__isnull=True)` | ID 180 (✅ único) |
| Bandeja activa para Walter | ID 180 únicamente |
| Timeline completo de Walter | 431 mensajes (47 + 66 + 180) |
| Búsqueda histórica | Conv 47 y 66 accesibles pero no en bandeja |

---

## Validación Pendiente

- ✅ Decisión documentada
- ⏳ SQL de cierre aplicado
- ⏳ Endpoint validado
- ⏳ Prueba real confirmada

