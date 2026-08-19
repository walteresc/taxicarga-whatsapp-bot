# Checklist de Pruebas Manuales en Staging

**Prerrequisito:**
- [ ] Django corriendo en staging (puerto 8002)
- [ ] ngrok activo apuntando a staging
- [ ] Meta Callback URL configurada al ngrok domain
- [ ] Test WhatsApp number configurado en Meta

---

## Pruebas de Funcionalidad

### 1. Cliente pregunta precio (QUOTED mode)
**Setup:** Crear conversación con estado=QUOTED, price=3500

**Pasos:**
- [ ] Enviar WhatsApp: "¿cuánto cuesta?"
- [ ] Bot responde: "El presupuesto sale en S/ 3500..."
- [ ] Verificar NO hay "Un momento" ni extracción
- [ ] Logs muestren `bot_v4_webhook_latency` < 300ms

**Éxito si:**
- Respuesta instantánea
- Precio correcto en reply
- Latencia < 300ms

---

### 2. Asesor toma control (Takeover)
**Setup:** Conversación normal (sin cerrar)

**Pasos:**
- [ ] Backend/CRM llamar: `POST /api/control/transfer-to-advisor/`
- [ ] Cliente: "hola"
- [ ] Bot NO responde
- [ ] Logs: `conversation_ownership check ... owner_type=advisor`

**Éxito si:**
- Respuesta suppressed
- No hay error 500

---

### 3. Asesor se va, bot vuelve
**Setup:** Conversación con owner=advisor

**Pasos:**
- [ ] Backend/CRM llamar: `POST /api/control/return-to-bot/`
- [ ] Cliente: "hola?"
- [ ] Bot responde
- [ ] Contexto QUOTED intacto (si aplica)

**Éxito si:**
- Bot no suppressed
- Conversación no reinicia

---

### 4. Cliente quiere nueva cotización (NEW_QUOTE)
**Setup:** Estado=QUOTED, price=3500

**Pasos:**
- [ ] Cliente: "Necesito cotizar otra mudanza"
- [ ] Bot reinicia preguntas (no repite datos viejos)
- [ ] Logs: `NEW_QUOTE reextraction`

**Éxito si:**
- Bot pregunta desde cero
- Precio viejo no se menciona

---

### 5. Cliente corrige un dato (CORRECTION)
**Setup:** En medio de extracción de datos

**Pasos:**
- [ ] Bot pregunta: "¿De qué distrito?"
- [ ] Cliente: "De Surco... ah no, de Miraflores"
- [ ] Bot detecta CORRECTION
- [ ] Logs: `conversation_action=correction`

**Éxito si:**
- Bot no repite la pregunta
- Continúa con datos siguientes

---

### 6. Conversación cerrada (no responde)
**Setup:** Conversación estado=cerrada

**Pasos:**
- [ ] Cliente: "¿Hola?"
- [ ] Webhook devuelve 200
- [ ] Pero crea NUEVA conversación
- [ ] Bot NO responde a la cerrada

**Éxito si:**
- Webhook 200 OK
- 2 conversaciones en DB
- Sin error

---

### 7. Timeout automático (inactivo 15+ min)
**Setup:** owner_type=advisor, last_human_message_at = now() - 16min

**Pasos:**
- [ ] Cliente: "hola"
- [ ] Bot responde (timeout pasó)
- [ ] Logs: owner_type cambió a bot

**Éxito si:**
- Bot no suppressed
- Timeout logic correcta

---

### 8. Tono natural
**Verificar en TODOS los replies:**
- [ ] "te late" / "está bien" / "dale" presente
- [ ] NUNCA "¿Confirmas?" o "¿Deseas modificar?"
- [ ] Conversacional, no botoso

---

### 9. Latencia Production
**Medir en logs:**
- [ ] QUOTED: `process_turn < 100ms`
- [ ] COLLECTING: `process_turn 2-5s` (OpenAI)
- [ ] Total: < 10s (alert threshold)

---

### 10. Manejo de errores
**Casos:**
- [ ] Mensaje vacío → sin crash
- [ ] Caracteres especiales (emojis, ñ) → se procesan
- [ ] URL en mensaje → sin crash
- [ ] Timeout OpenAI → fallback, no cuelga

---

## Criterios de Éxito

✅ Todo PASS → **LISTO PARA PRODUCCIÓN**

❌ Alguno FAIL → Ir a logs, reportar, volver a staging

---

## Duración Estimada

**Setup:** 15 min
**Pruebas manuales:** 30-45 min
**Total:** 45-60 min

Si todo PASS: DEPLOY a producción
