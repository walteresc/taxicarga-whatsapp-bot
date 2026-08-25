# Diagnóstico HMAC YCloud — Información Necesaria

**Estado**: Webhooks llegan a Nginx/Django pero son rechazados con HTTP 401 (Invalid signature)

**Causa preliminar**: Mismatch entre:
- Secreto que YCloud está usando para firmar
- Secreto en Django (test_secret_e2e)
- Formato de firma esperado vs. actual

---

## INFORMACIÓN REQUERIDA DEL YCLOUD DELIVERY LOG

**Para el evento "probando11" enviado por Walter a las 17:27 UTC (2026-08-24 22:27 Lima time):**

### 1. Detalles del Evento

Abre YCloud Dashboard → Delivery Log (o Message History) → Busca "probando11"

Captura/proporciona:
```
Event ID:           [UUID exacto, ej: evt_6a8cdedae9f19c6fc977963e]
Message ID (WAMID): [Identificador del mensaje, ej: 6a8cdeda620393694b34c7d8]
From:               [Teléfono de Walter, ej: +51995403320]
To:                 [Teléfono de negocio Lima Express, ej: +51967619238]
Content:            probando11
Timestamp:          [Epoch o ISO8601, ej: 1724172420 o 2026-08-24T22:27:00Z]
Status:             [sent/delivered/failed/etc]
```

### 2. Webhook Configuration en YCloud

En la configuración del webhook (YCloud → Settings → Webhooks o similar):

Captura:
```
Webhook URL:        https://abrasive-contents-edge.ngrok-free.dev/webhooks/ycloud/v1/
Webhook Secret:     [NO exponer completamente, pero confirmar]:
                    - Longitud exacta del secret configurado
                    - Primeros 4 caracteres
                    - Últimos 4 caracteres
                    ✓ Si es test_secret_e2e → "test" ... "_e2e"
                    ✓ Si es diferente → proporcionar longitud y extremos
Active:             [yes/no]
Events subscribed:  [list, debe incluir whatsapp.inbound_message.received]
```

### 3. Delivery Log Entry (Webhook Attempt)

En el mismo delivery log, busca la fila "Webhook Attempt" o "HTTP Request":

Captura:
```
URL:                https://abrasive-contents-edge.ngrok-free.dev/webhooks/ycloud/v1/
Method:             POST
HTTP Status:        401 (esperado, porque Django rechaza la firma)
Request Headers:    [Busca especialmente]
  - Authorization   [si aplica]
  - X-Signature     [si existe este header]
  - Ycloud-Signature [patrón exacto]
  - Content-Type    [ej: application/json]

Signature Header:   [Valor EXACTO, ej: t=1724172420,s=34303edb91c95bbd7d9e26aa987b9735b030cfd275d01748dac6d2ab884e4c54]
```

### 4. Request Body (opcional pero útil)

Si YCloud muestra el body enviado:
```
Raw Body:           [JSON completo que fue enviado como webhook payload]
Body Size:          [bytes exactos]
Body Hash:          [SHA256, si disponible]
```

### 5. YCloud Webhook Documentation

Proporciona o confirma:
```
- Documentación oficial de YCloud sobre webhook signing
- Algoritmo usado: HMAC-SHA256 (esperado)
- Formato de la firma (CRITICAL):
  a) ¿Solo el body raw?
     Signature = HMAC-SHA256(secret, body)
  b) ¿timestamp + "." + body?
     Signature = HMAC-SHA256(secret, timestamp + "." + body)
  c) ¿Algo else?
     Signature = HMAC-SHA256(secret, ???)
- Codificación: Hex (esperado) vs Base64 u otra
- Cómo se extrae timestamp: ¿Del header t=... o de dentro del JSON?
```

---

## INFORMACIÓN QUE YA TENEMOS

```
Docker Django Secret:          test_secret_e2e (15 chars)
ALLOWED_HOSTS:                 CORRECTO (acepta ngrok)
Formatos intentados:           
  1. body_only                 → FAIL (no coincide)
  2. timestamp.body            → FAIL (no coincide)
Recent webhook HTTP 401:       Todos rechazados
Body integridad:               Verified (hash estable, bytes correctos)
Nginx access:                  Recibe POST correctamente
```

---

## CHECKLIST: ¿DÓNDE BUSCAR EN YCLOUD?

- [ ] Dashboard principal → Delivery Log o Webhooks Log
- [ ] Crear nueva pestaña: YCloud → [Nombre de tu aplicación/número de negocio]
- [ ] Settings o Configuration → Webhooks
- [ ] Filtrar por timestamp ~22:27 (hora Lima) en 2026-08-24
- [ ] Buscar "probando11" en contenido o event_id
- [ ] Click en ese evento → Ver detalles completos
- [ ] Si hay "View Request/Response" → abrir eso
- [ ] Si hay "Signature" o "X-Signature" header visible → anotar

---

## SIGUIENTE PASO

Una vez que proporciones la información anterior:

1. **Compararé** la firma real de YCloud contra los formatos posibles
2. **Identificaré** cuál formato usa YCloud
3. **Ajustaré** el código de validación si es necesario
4. **Crearé test** para validar la firma correctamente
5. **Recreará** el contenedor Django con la fix
6. **Solicitaré Retry** en YCloud para retransmitir el evento "probando11" original
7. **Verificaré** que aparezca en PostgreSQL → Redis → SSE → DOM

---

## TIMELINE

- 17:27 UTC: Evento "probando11" enviado por Walter a WhatsApp
- 17:27+: YCloud recibe confirmación
- 17:39-19:18: YCloud intenta entregar webhook (múltiples reintentos)
- 22:27+: Esperando tu información del Delivery Log

**NO ENVÍES OTRO MENSAJE** desde Walter hasta que confirmemos la firma. Usaremos Retry en el evento original.
