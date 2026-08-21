# Prueba Live: Walter Escobar desde WhatsApp Web

**Objetivo:** Validar que el flujo completo funciona (normalización → dedup → ordering)  
**Duración estimada:** 10 minutos  
**Resultado esperado:** Walter aparece en #1 de Bandeja después de enviar mensaje

---

## ✅ PRE-REQUISITOS (Verificar antes de empezar)

### 1. Sistema corriendo
```bash
cd d:\DESARROLLO_IA\Proyecto_taxi_carga\Taxi_carga_bot\taxicarga_whatsapp_bot
python manage.py runserver 8001
# Esperar: "Starting development server at http://127.0.0.1:8001/"
```

### 2. Bandeja de Entrada accesible
```
Abrir: http://localhost:8001/dashboard/whatsapp/conversaciones/
Buscar por nombre: "Walter Escobar"
Resultado esperado: ID=77 visible en la lista (posición #2 o más abajo)
```

### 3. Webhook recibiendo
```bash
# En otra terminal, tail de logs
tail -f django_debug.log | grep -i "walter\|995403320"
# Debe estar esperando eventos
```

---

## 🔄 PROCEDIMIENTO DE PRUEBA

### PASO 1: Captura inicial (Línea Base)

**En CRM:**
```
1. Abre: http://localhost:8001/dashboard/whatsapp/conversaciones/
2. Busca: "Walter" (ctrl+f en página)
3. Anota: 
   - ¿Aparece Walter Escobar?
   - ¿En qué posición está? (#1, #2, ..., #N)
   - ¿Última actividad mostrada?
```

**Expected:**
```
✅ Walter Escobar visible (ID=77)
✅ Posición: #2 (porque Conv ID=196 es más reciente)
✅ última_actividad: 2026-08-20 16:50:52
```

**Captura:**  
📷 Screenshot para comparación posterior

---

### PASO 2: Envía mensaje desde WhatsApp Web

**Desde tu teléfono o WhatsApp Web:**

```
Contacto: +51995403320 (Walter Escobar)
Mensaje: "Hola, tengo una mudanza urgente"
Envía: [ENTER]
```

**Sistema procesa:**
- Webhook recibe evento
- Normaliza: `+51995403320` → `+51995403320` ✅
- Resuelve: Cliente ID=77 (canónico)
- Persiste: Mensaje en BD
- Actualiza: `ultima_actividad = now`
- Response: HTTP 200 (< 100ms)

**Verificar en logs:**
```
[webhook] message received from +51995403320
[normalizer] normalized +51995403320 → +51995403320
[resolver] found canonical cliente: ID=77 (Walter Escobar)
[persist] message created: ID=XXXX
[activity] updated conversation.ultima_actividad
[response] 200 OK
```

---

### PASO 3: Verifica en CRM (Polling automático)

**Dentro de 5 segundos (polling):**

CRM debe auto-refrescar. Si no:
- Presiona `F5` (refresh manual)

**Verificar:**
```
✅ Walter Escobar debe estar en #1 (arriba de todo)
✅ última_actividad: 2026-08-20 17:XX:XX (ahora)
✅ Preview debe mostrar: "Hola, tengo una mudanza urgente"
✅ Unread count: 1 (mensaje no leído)
```

**Captura:**  
📷 Screenshot para comparación

---

### PASO 4: Abre conversación de Walter

**Click en "Walter Escobar"**

**Debe mostrar:**
```
📱 Conversación ID=180
   ├─ Últimos mensajes (historial)
   ├─ ✅ Nuevo mensaje: "Hola, tengo una mudanza urgente"
   ├─ Display name: "Walter Escobar" (NO "TEST Stage 7" u otro)
   └─ Cliente ID: 77 (NO 90, NO 106)
```

**Verificar NO hay duplicados:**
```bash
# En terminal:
python manage.py shell
>>> from apps.whatsapp.models import ConversacionWhatsApp
>>> ConversacionWhatsApp.objects.filter(cliente__phone_e164="+51995403320").count()
3  # Debe ser 3 (solo las conversaciones de ID=77)
```

---

### PASO 5: Responde en CRM

**Escribe respuesta:**
```
"Hola Walter, claro, te ayudamos. ¿Cuál es tu origen y destino?"
[Enviar]
```

**Sistema debe:**
- ✅ Guardar en BD
- ✅ Enviar a WhatsApp (YCloud)
- ✅ Mostrar estado: "enviado" / "entregado"
- ✅ Actualizar `ultima_actividad` nuevamente

**Verificar en WhatsApp Web:**
```
El mensaje debe llegar a Walter (~1-2 seg)
```

---

## 🔍 VERIFICACIONES DETALLADAS

### Verificación 1: Normalización

```bash
python manage.py shell
>>> from apps.clientes.phone_normalizer import normalize_phone
>>> normalize_phone("995403320")
{'normalized_e164': '+51995403320', 'is_valid': True, ...}
>>> normalize_phone("51995403320")
{'normalized_e164': '+51995403320', 'is_valid': True, ...}
✅ Todas las variantes normalizan igual
```

### Verificación 2: Cliente Canónico

```bash
python manage.py shell
>>> from apps.clientes.models import Cliente
>>> c = Cliente.objects.get(id=77)
>>> print(f"Name: {c.display_name}")
>>> print(f"Phone: {c.phone_e164}")
>>> print(f"Active: {c.is_active}")
>>> print(f"Convs: {c.conversaciones.count()}")

Expected:
Name: Walter Escobar
Phone: +51995403320
Active: True
Convs: 3
```

### Verificación 3: Duplicados Desactivados

```bash
python manage.py shell
>>> from apps.clientes.models import Cliente
>>> Cliente.objects.get(id=90).is_active
False  ✅
>>> Cliente.objects.get(id=90).merged_into_id
77  ✅
>>> Cliente.objects.get(id=106).is_active
False  ✅
>>> Cliente.objects.get(id=106).merged_into_id
77  ✅
```

### Verificación 4: Ordering Correcto

```bash
python manage.py shell
>>> from apps.whatsapp.models import ConversacionWhatsApp
>>> convs = ConversacionWhatsApp.objects.all()[:5]
>>> for c in convs:
...     print(f"ID={c.id}, última={c.ultima_actividad}")

Expected: Ordenadas DESC por ultima_actividad
ID=180, última=2026-08-20 17:XX:XX  (most recent)
ID=196, última=2026-08-20 17:XX:XX
ID=191, última=2026-08-20 15:50:20
...
```

### Verificación 5: API Endpoint

```bash
# Terminal
curl -s "http://localhost:8001/dashboard/whatsapp/conversaciones/api/active/?page=1" | jq '.conversations[0:3]'

Expected:
[
  {
    "id": 180,
    "name": "Walter Escobar",
    "phone": "+51995403320",
    "last_activity": "2026-08-20T17:XX:XXZ",
    ...
  },
  ...
]
```

---

## ⚠️ TROUBLESHOOTING

### Problema: Walter no aparece en #1

**Diagnóstico:**
```bash
# 1. ¿Mensaje llegó al webhook?
tail django_debug.log | grep "995403320"

# 2. ¿Se normalizó?
python manage.py shell
>>> from apps.whatsapp.models import MensajeWhatsApp
>>> MensajeWhatsApp.objects.filter(telefono__icontains="995403320").last()

# 3. ¿Se actualizó ultima_actividad?
>>> from apps.whatsapp.models import ConversacionWhatsApp
>>> ConversacionWhatsApp.objects.get(id=180).ultima_actividad
```

**Soluciones:**
1. Verifica webhook está activo: `python manage.py runserver`
2. Verifica YCloud token válido: `.env` YCLOUD_API_KEY
3. Recarga manualmente: F5 en CRM
4. Rebuild summaries: `python manage.py rebuild_conversation_summaries`

### Problema: Aparecen múltiples IDs para Walter

**Causa:** Merge no funcionó  
**Diagnóstico:**
```bash
python manage.py shell
>>> from apps.clientes.models import Cliente
>>> Cliente.objects.filter(phone_e164="+51995403320")
<QuerySet [<Cliente: ID=106>, <Cliente: ID=90>, <Cliente: ID=77>]>
```

**Solución:**
```bash
# Re-ejecutar merge
python manage.py normalize_and_merge_customers --only-phone +51995403320
```

### Problema: Display_name sigue siendo "TEST Stage 7"

**Causa:** Campo no actualizado  
**Solución:**
```bash
python manage.py shell
>>> from apps.clientes.models import Cliente
>>> c = Cliente.objects.get(id=77)
>>> c.display_name = "Walter Escobar"
>>> c.save()
```

---

## 📊 RESULTADO ESPERADO FINAL

**Línea Base (Antes):**
```
Bandeja de Entrada:
  └─ Solo 11-12 conversaciones visibles
  └─ Walter Escobar AUSENTE (oculto por filtro 24h)
  └─ Orden INCONSISTENTE
```

**Después de Prueba (Esperado):**
```
Bandeja de Entrada:
  ✅ 197 conversaciones visibles (página 1 de 8)
  ✅ Walter Escobar en #1 o #2 (por recencia)
  ✅ Orden CONSISTENTE (-ultima_actividad DESC)
  ✅ Display name: "Walter Escobar"
  ✅ 3 conversaciones de Walter INTACTAS
  ✅ 425 mensajes PRESERVADOS
  ✅ Clientes 90, 106 INACTIVOS (merged)
  ✅ Polling automático cada 5 seg
```

---

## ✅ CHECKLIST FINAL

- [ ] Sistema corriendo en http://localhost:8001
- [ ] Bandeja de Entrada cargada
- [ ] Walter Escobar visible (ID=77, display_name correcto)
- [ ] Mensaje enviado desde WhatsApp Web
- [ ] Walter sube a #1 o #2 (dentro de 5 seg)
- [ ] Conversación abre sin errores
- [ ] Display name = "Walter Escobar"
- [ ] Respuesta desde CRM enviada correctamente
- [ ] Verificación en BD: 3 conversaciones de Walter intactas
- [ ] Verificación en BD: 425 mensajes preservados
- [ ] Verificación en BD: IDs 90, 106 inactivos
- [ ] API endpoint retorna pagination metadata
- [ ] No hay duplicados (solo ID=77)

---

**Cuando todo esté ✅ COMPLETADO:**

Reporta:
```
✅ Prueba exitosa
✅ Walter Escobar aparece correctamente
✅ Ordenamiento funciona
✅ Integridad de datos preservada
```

Y procede a **MERGE A MAIN** 🚀

