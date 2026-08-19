# Staging Deployment & Testing Guide

## **Paso 1: Clonar repositorio**

```bash
cd /staging
git clone https://github.com/tu-repo/taxicarga.git staging
cd staging
git checkout main
```

---

## **Paso 2: Crear .env.staging**

```bash
# Generar SECRET_KEY
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Crear archivo .env.staging
cat > .env.staging << 'EOF'
# Django
DJANGO_DEBUG=False
SECRET_KEY=<copiar output del comando anterior>
ALLOWED_HOSTS=localhost,127.0.0.1,.ngrok-free.app

# Database (staging PostgreSQL)
DATABASE_URL=postgresql://staging_user:staging_pass@localhost:5432/taxicarga_staging

# OpenAI (usar key real o sandbox)
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4.1-mini

# WhatsApp (Meta test token + test number)
WHATSAPP_ACCESS_TOKEN=<test token from Meta>
WHATSAPP_PHONE_NUMBER_ID=<test phone_number_id>
WHATSAPP_API_VERSION=v25.0
WHATSAPP_VERIFY_TOKEN=staging-verify-token-123

# Logging
DJANGO_LOG_LEVEL=INFO
EOF

# Exportar variables
export $(cat .env.staging | xargs)
```

---

## **Paso 3: Preparar Base de Datos**

```bash
# Crear BD de staging
createdb taxicarga_staging
createuser staging_user --createdb --login --no-superuser
psql -U postgres -c "ALTER USER staging_user WITH PASSWORD 'staging_pass';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE taxicarga_staging TO staging_user;"

# Correr migraciones
python manage.py migrate --settings=config.settings

# Crear superuser para testing
python manage.py createsuperuser --settings=config.settings
# Ingresar: username=admin, email=admin@test.com, password=admin123
```

---

## **Paso 4: Activar ngrok & Django en Staging**

**Terminal 1: Django en puerto 8002**

```bash
cd /staging/staging
python manage.py runserver 0.0.0.0:8002 --settings=config.settings
```

Debería ver:
```
Starting development server at http://0.0.0.0:8002/
Quit the server with CONTROL-C.
```

**Terminal 2: ngrok (en otra terminal)**

```bash
# Asumiendo ngrok instalado
ngrok http 8002

# Output:
# Forwarding   https://xxxx-xx-xxx-xxx-xx.ngrok-free.app -> http://localhost:8002
# Copiar: https://xxxx-xx-xxx-xxx-xx.ngrok-free.app
```

---

## **Paso 5: Configurar Meta Webhook Callback**

1. Ir a: https://developers.facebook.com/
2. Seleccionar tu app
3. Settings → Webhooks
4. **Callback URL:** `https://xxxx-xx-xxx-xxx-xx.ngrok-free.app/webhook/whatsapp/v4/`
5. **Verify Token:** `staging-verify-token-123` (del .env.staging)
6. Hacer clic en "Verify and Save"

**Debería mostrar:**
```
Webhook registered successfully
```

---

## **Paso 6: Crear Conversación de Test en DB**

```bash
python manage.py shell --settings=config.settings

# Ejecutar en Django shell:
from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel
from apps.whatsapp_bot_v4.models import BotConversationState, ConversationOwnership

# Crear cliente
cliente = Cliente.objects.create(telefono="+51987654321")
print(f"Cliente creado: {cliente.pk}")

# Obtener channel de staging
channel = WhatsAppChannel.objects.first()  # O filtrar por tu phone_number_id
print(f"Channel: {channel.phone_number_id}")

# Crear lead
lead = Lead.objects.create(cliente=cliente, whatsapp_channel=channel)
print(f"Lead creado: {lead.pk}")

# Crear conversación
conversation = ConversacionWhatsApp.objects.create(
    cliente=cliente,
    lead=lead,
    channel=channel
)
print(f"Conversación creada: {conversation.pk}")

# Crear bot state (COLLECTING mode para test)
bot_state = BotConversationState.objects.create(
    conversation_key=f"whatsapp:{conversation.pk}",
    status="collecting",
    state_data={}
)
print(f"BotState creado: {bot_state.pk}")

# Crear ownership
ownership = ConversationOwnership.objects.create(conversation=conversation)
print(f"Ownership creado: {ownership.pk}")

# Imprimir resumeb
print(f"\n=== TEST SETUP READY ===")
print(f"Cliente: +51987654321")
print(f"Conversation ID: {conversation.pk}")
print(f"Conversation Key: whatsapp:{conversation.pk}")

exit()
```

**Guardar:**
- Cliente: `+51987654321`
- Conversation ID: (anotar el número que imprime)

---

## **Paso 7: Monitorear Logs en Tiempo Real**

**Terminal 3: Ver logs**

```bash
cd /staging/staging
tail -f django_debug.log | grep -E "webhook|bot_v4_|conversation_ownership"
```

Debería aparecer cuando lleguen mensajes.

---

## **Paso 8: Enviar Test Mensaje desde WhatsApp**

### **Opción A: Desde Meta Dashboard (Test Message)**

1. Ir a: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/test-webhook
2. Usar Meta's Test Message tool
3. Hacer clic en "Send Test Message"
4. Ver logs en Terminal 3

### **Opción B: Desde WhatsApp Real**

Enviar un WhatsApp desde el número de cliente (`+51987654321`) al número de negocio Meta.

**Meta proporciona:**
- Sender: Tu número de test (ej: +51912345678)
- Recipient: Número cliente (ej: +51987654321)

---

## **Paso 9: Verificar Webhook Response**

En Terminal 3 (logs), deberías ver:

```
[INFO] ... webhook_received conversation_id=<ID> message_id=<ID>
[INFO] ... bot_v4_mode_decision conversation_id=<ID> commercial_status=collecting
[INFO] ... bot_v4_extraction_attempt conversation_id=<ID>
[INFO] ... bot_v4_webhook_latency conversation_id=<ID> status=sent total=<ms>ms
```

Si hay errores:
```
[ERROR] ... error_type=<error> error=<mensaje>
```

---

## **Paso 10: Ejecutar Manual Test Scenarios**

Usar `STAGING_TEST_CHECKLIST.md` para verificar cada escenario:

```bash
# Scenario 1: Cliente pregunta precio
# Enviar: "¿cuánto cuesta?"
# Esperado: Bot responde con precio

# Scenario 2: Asesor toma control
# Llamar API: POST /api/control/transfer-to-advisor/
# Esperado: Bot suppressed

# Scenario 3: Asesor se va
# Llamar API: POST /api/control/return-to-bot/
# Esperado: Bot reactiva

# ... y así para los 10 escenarios
```

---

## **Troubleshooting**

### **ngrok no conecta**
```
Error: Connection refused
Fix: Verificar Django está running en 8002
```

### **Meta webhook no valida**
```
Error: Invalid verify token
Fix: Verificar WHATSAPP_VERIFY_TOKEN en .env.staging
```

### **No llega mensaje del cliente**
```
Error: Webhook POST no aparece en logs
Fix: 
1. Verificar Meta Callback URL está actualizada
2. Verificar WHATSAPP_PHONE_NUMBER_ID coincide
3. Reiniciar ngrok (genera nueva URL)
```

### **Bot no responde**
```
Error: turn.suppressed=True
Fix:
1. Verificar ConversationOwnership.owner_type=bot
2. Verificar no hay error en bot_v4_extraction_attempt logs
3. Revisar OpenAI error (si aplica)
```

---

## **Checklist Completo**

```
SETUP:
[ ] .env.staging creado
[ ] BD staging creada y migraciones OK
[ ] Django corriendo en 8002
[ ] ngrok activo
[ ] Meta webhook callback actualizada
[ ] Test conversation creada en DB
[ ] Logs monitoreados

TESTING (10 escenarios):
[ ] 1. Cliente pregunta precio (QUOTED)
[ ] 2. Asesor toma control
[ ] 3. Asesor se va, bot vuelve
[ ] 4. Cliente quiere nueva cotización
[ ] 5. Cliente corrige un dato
[ ] 6. Conversación cerrada
[ ] 7. Webhook transaction_completed
[ ] 8. Webhook transaction_cancelled
[ ] 9. Tono natural verificado
[ ] 10. Error handling verificado

VALIDATION:
[ ] 124/124 tests PASS (automated)
[ ] 10/10 manual scenarios PASS
[ ] Latency < 300ms (QUOTED)
[ ] Latency 2-5s (COLLECTING)
[ ] No errors in logs

STATUS: LISTO PARA PRODUCCIÓN
```

---

## **Deploy a Producción (Después de Staging)**

```bash
# 1. Crear .env.production
cp .env.staging .env.production
# Editar con credenciales de PRODUCCIÓN

# 2. Deploy
git checkout main
python manage.py migrate --settings=config.settings_production
python manage.py runserver --settings=config.settings_production

# 3. Actualizar Meta webhook a URL de producción

# 4. Monitorear
tail -f /var/log/django/bot_v4.log | grep bot_v4_webhook_latency

# 5. Setup alerts para latency > 10s
```
