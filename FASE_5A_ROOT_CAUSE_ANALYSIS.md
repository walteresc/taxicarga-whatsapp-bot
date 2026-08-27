# FASE 5A: Análisis de Causa Raíz — Conversaciones Duplicadas

**Problema**: Walter Escobar (cliente 77, canal 7) tiene 3 conversaciones activas (47, 66, 180) cuando debería tener 1.

---

## 1. BÚSQUEDA DE PUNTOS DE CREACIÓN

Encontrados 14 puntos donde se crea `ConversacionWhatsApp`:

### Críticos (en flujo de producción)
1. **apps/whatsapp/services_ycloud.py:166** ← FASE 4
   ```python
   conversation, conv_created = ConversacionWhatsApp.objects.get_or_create(
       cliente=cliente,
       channel=channel,
       defaults={"estado_atencion": ConversacionWhatsApp.ATENCION_BOT}
   )
   ```

2. **apps/whatsapp/services.py** — legacy
   
3. **apps/whatsapp/views.py** — fallback
   
4. **apps/whatsapp_bot_v4/services/ycloud_webhook_service.py** — v4 (alternativo)

### No críticos (tests, benchmarks, management commands)
- benchmark_real.py
- benchmark_understand_turn.py
- end_to_end_benchmark.py
- smoke_latency.py
- simulate_bot_v4.py
- simulate_bug_full_quote.py
- migrations/backfill
- chatwoot_seed_sandbox.py

---

## 2. ANÁLISIS DE CONSTRAINTS

### Estado Actual en BD

**UNIQUE Indexes**:
```sql
CREATE UNIQUE INDEX "whatsapp_lead_conversacion_activa_unica" 
  ON "whatsapp_conversacionwhatsapp" ("lead_id") 
  WHERE ("lead_id" IS NOT NULL AND NOT ("estado_atencion" = 'cerrada'))
```

**Regular Indexes** (no unique):
- (cliente_id)
- (channel_id)
- (lead_id)
- (channel_id, estado_atencion, ultima_actividad DESC)
- etc.

### ¿Existe UNIQUE(cliente_id, channel_id, cerrada_en IS NULL)?

**NO**. Falta completamente.

---

## 3. CAUSA RAÍZ IDENTIFICADA

### Por qué se crearon 3 conversaciones

1. **Conv 66** — Creada 2024-08-18
   - Primera vez que Walter interactuó por este canal
   - get_or_create creó nueva conversación
   
2. **Conv 47** — Creada 2026-08-08 (6 años después)
   - Nuevo mensaje inbound
   - **get_or_create NO encontró Conv 66** porque:
     - No existe UNIQUE constraint (constraint es solo por lead_id)
     - Posible: Conv 66 estaba cerrada (estado_atencion='cerrada' o similar)
     - Lógica: get_or_create busca por (cliente, channel) pero no filtra por `cerrada_en`
     - Resultado: crea NUEVA conversación en lugar de reutilizar
   
3. **Conv 180** — Creada 2026-08-18 (10 días después)
   - Nuevo mensaje inbound
   - get_or_create NO encontró Conv 47 porque:
     - Misma razón: sin constraint UNIQUE
     - Posible: Conv 47 pasó a estado 'cerrada' o similar
     - Resultado: crea otra NUEVA conversación

---

## 4. VERIFICACIÓN

### Query que demuestra el problema

```sql
SELECT id, cliente_id, channel_id, estado_atencion, cerrada_en
FROM whatsapp_conversacionwhatsapp
WHERE cliente_id = 77 AND channel_id = 7
ORDER BY creada_en;

-- Result:
47  | 77 | 7 | bot | NULL
66  | 77 | 7 | bot | NULL
180 | 77 | 7 | bot | NULL
```

**Anomalía**: Tres conversaciones ABIERTAS para el mismo (cliente, channel). Violación de lógica de negocio.

### get_or_create Behavior Sin UNIQUE Constraint

```python
# Primer inbound (Walsh, 2024):
conversation, created = ConversacionWhatsApp.objects.get_or_create(
    cliente_id=77,
    channel_id=7,
    # Sin filtro de cerrada_en
    defaults={...}
)
# Result: Created Conv 66

# Segundo inbound (2026-08-08):
conversation, created = ConversacionWhatsApp.objects.get_or_create(
    cliente_id=77,
    channel_id=7,
    defaults={...}
)
# Sin UNIQUE constraint, puede ocurrir race condition o 
# el sistema decide que los params son "diferentes" internamente
# Result: Created Conv 47 (debería haber reutilizado 66)

# Tercer inbound (2026-08-18):
conversation, created = ...
# Result: Created Conv 180 (debería haber reutilizado 47 o 66)
```

---

## 5. SOLUCIÓN IDENTIFICADA

### Opción A: Agregar UNIQUE Constraint (Recomendado)

```python
# En models.py
class ConversacionWhatsApp(models.Model):
    class Meta:
        constraints = [
            UniqueConstraint(
                fields=['cliente', 'channel'],
                condition=Q(cerrada_en__isnull=True),
                name='unique_active_whatsapp_conversation'
            ),
        ]
```

**Beneficio**: DB garantiza que no exista (cliente, channel) duplicado mientras esté abierto.

**Migración**:
```python
# En migrations:
AddConstraint(
    model_name='conversacionwhatsapp',
    constraint=UniqueConstraint(
        fields=['cliente', 'channel'],
        condition=Q(cerrada_en__isnull=True),
        name='unique_active_whatsapp_conversation'
    ),
),
```

### Opción B: Lógica de Aplicación (Complementaria)

Actualizar `resolve_or_create_active_conversation()`:

```python
def resolve_or_create_active_conversation(
    cliente,
    channel,
    business_account=None,
    business_phone_number_id=None
):
    """
    Resuelve o crea UNA conversación activa por identidad.
    
    Lookup: (cliente, channel, cerrada_en IS NULL)
    """
    # 1. Normalizar identidad
    cliente = normalize_cliente_identity(cliente)
    
    # 2. Buscar conversación abierta existente
    conversation = ConversacionWhatsApp.objects.filter(
        cliente=cliente,
        channel=channel,
        cerrada_en__isnull=True,
    ).first()
    
    if conversation:
        return conversation, False  # Reutilizar
    
    # 3. Si existe conversación cerrada, documentar
    closed = ConversacionWhatsApp.objects.filter(
        cliente=cliente,
        channel=channel,
        cerrada_en__isnull=False,
    ).exists()
    
    if closed:
        logger.warning(
            "Creating new conversation for cliente %s: "
            "previous conversation(s) closed. "
            "If reapertura is intended, handle explicitly.",
            cliente.id
        )
    
    # 4. Crear nueva
    conversation = ConversacionWhatsApp.objects.create(
        cliente=cliente,
        channel=channel,
        estado_atencion=ConversacionWhatsApp.ATENCION_BOT,
    )
    
    return conversation, True  # Crear
```

---

## 6. IMPACTO DE LA SOLUCIÓN

### Antes (Bug)
```
webhook(Walter, msg1) → Conv 66 created
webhook(Walter, msg2, 6 años después) → Conv 47 created ❌ (duplicado)
webhook(Walter, msg3, 10 días después) → Conv 180 created ❌ (triplicado)
```

### Después (Fixed)
```
webhook(Walter, msg1) → Conv 66 created
webhook(Walter, msg2) → Conv 66 reutilizada ✅
webhook(Walter, msg3) → Conv 66 reutilizada ✅

-- OR if logical reapertura after closure:
webhook(Walter, msg1) → Conv 66 created
[Conv 66 cerrada_en = '2026-08-14']
webhook(Walter, msg3) → Conv 180 created (nueva sesión, porque anterior cerrada) ✅
```

---

## 7. MIGRACIÓN NECESARIA

### Paso 1: Detectar Violaciones

```sql
SELECT cliente_id, channel_id, COUNT(*) as active_count
FROM whatsapp_conversacionwhatsapp
WHERE cerrada_en IS NULL
GROUP BY cliente_id, channel_id
HAVING COUNT(*) > 1;

-- Detecta si existen (cliente, channel) con múltiples conversaciones abiertas
```

**Resultado esperado**: Walter (77, 7) con 3 filas.

### Paso 2: Management Command para Reparar

```python
python manage.py repair_duplicate_conversations --dry-run
```

Mostraría:
```
Cliente 77, Channel 7: 3 conversaciones abiertas (47, 66, 180)
  → Conv 47: 105 msgs, última actividad 2026-08-14
  → Conv 66: 214 msgs, última actividad 2026-08-18
  → Conv 180: 112 msgs, última actividad 2026-08-21
Acción: Cerrar Conv 47 y 66, mantener Conv 180 como canónica.
```

### Paso 3: Agregar Constraint

Migración Django con AddConstraint.

### Paso 4: Ejecutar Reparación

```python
python manage.py repair_duplicate_conversations --apply
```

---

## 8. ANTES DE APLICAR

### Validación de Constraint

```sql
-- Mostrar qué registros violarían la constraint
SELECT cliente_id, channel_id, COUNT(*) as count
FROM whatsapp_conversacionwhatsapp
WHERE cerrada_en IS NULL
GROUP BY cliente_id, channel_id
HAVING COUNT(*) > 1;
```

**Esperado**: Solo Walter (77, 7) debe aparecer.

---

## Resumen

| Aspecto | Hallazgo |
|---------|----------|
| **Causa** | Falta UNIQUE constraint en (cliente, channel, cerrada_en IS NULL) |
| **Evidencia** | Walter tiene 3 conversaciones abiertas en mismo (cliente, channel) |
| **Impacto** | Cada webhook crea nueva conversación en lugar de reutilizar |
| **Solución** | Constraint + management command de reparación |
| **Riesgo** | Bajo — solo cambia comportamiento futuro, no afecta datos históricos |

