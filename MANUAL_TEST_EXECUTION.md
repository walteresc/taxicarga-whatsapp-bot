# Ejecución Manual de 10 Escenarios de Prueba

**Setup Activo:**
- Puerto: 8001
- ngrok: https://abrasive-contents-edge.ngrok-free.dev
- Meta Test Number: +1 (555) 661-2885
- Webhook: https://abrasive-contents-edge.ngrok-free.dev/webhooks/whatsapp/v4/

---

## **Paso 0: Monitorear Logs en Tiempo Real**

Terminal abierta:
```bash
cd d:\DESARROLLO_IA\Proyecto_taxi_carga\Taxi_carga_bot\taxicarga_whatsapp_bot
tail -f django_debug.log | grep -E "webhook|bot_v4_|conversation_ownership|latency" 2>&1
```

O en PowerShell:
```powershell
Get-Content .\django_debug.log -Wait -Tail 20 | Select-String "webhook|bot_v4_|conversation_ownership|latency"
```

---

## **Escenario 1: Cliente pregunta precio (QUOTED mode)**

**Setup DB:**
```bash
python manage.py shell
>>> from apps.clientes.models import Cliente
>>> from apps.leads.models import Lead
>>> from apps.whatsapp.models import ConversacionWhatsApp
>>> from apps.whatsapp_bot_v4.models import BotConversationState, ConversationOwnership
>>> 
>>> cliente = Cliente.objects.create(telefono="+1555661288X")  # Número test Meta
>>> lead = Lead.objects.create(cliente=cliente)
>>> conv = ConversacionWhatsApp.objects.create(cliente=cliente, lead=lead)
>>> 
>>> BotConversationState.objects.create(
...     conversation_key=f"whatsapp:{conv.pk}",
...     status="quoted",
...     quote_price=3500.00,
...     state_data={"origin_district": "Lima", "destination_district": "Callao"}
... )
>>> ConversationOwnership.objects.create(conversation=conv)
>>> 
>>> print(f"Conversation: {conv.pk}")
>>> exit()
```

**Ejecución:**
- Enviar WhatsApp desde Meta test: "¿cuánto cuesta?"
- Esperado: Bot responde con precio S/ 3500
- Verificar logs: `bot_v4_webhook_latency` < 300ms
- ✅ PASS si: Respuesta rápida con precio correcto

---

## **Escenario 2: Asesor toma control (Takeover)**

**Setup:**
```bash
curl -X POST http://localhost:8001/api/v4/conversation-control/transfer-to-advisor/ \
  -H "Authorization: Bearer <YOUR_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": <CONV_ID_FROM_SCENARIO_1>,
    "advisor_id": <YOUR_USER_ID>,
    "mode": "manual"
  }'
```

**Ejecución:**
- Enviar WhatsApp: "hola"
- Esperado: Bot NO responde (suppressed)
- Verificar logs: `owner_type=advisor`
- ✅ PASS si: Sin respuesta del bot

---

## **Escenario 3: Asesor se va, bot vuelve**

**Setup:**
```bash
curl -X POST http://localhost:8001/api/v4/conversation-control/return-to-bot/ \
  -H "Authorization: Bearer <YOUR_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": <CONV_ID>}'
```

**Ejecución:**
- Enviar WhatsApp: "¿hola?"
- Esperado: Bot responde
- Verificar logs: `owner_type=bot`
- ✅ PASS si: Bot activo sin error

---

## **Escenario 4: Cliente quiere nueva cotización (NEW_QUOTE)**

**Setup:**
- Mismo conversation_id de Scenario 1 (QUOTED mode aún activo)

**Ejecución:**
- Enviar WhatsApp: "Necesito cotizar otra mudanza"
- Esperado: Bot reinicia preguntas desde cero
- Verificar logs: `conversation_action=new_request` o `status=collecting`
- ✅ PASS si: Bot pregunta "¿De dónde te mudás?" sin mencionar precio viejo

---

## **Escenario 5: Cliente corrige un dato (CORRECTION)**

**Setup:**
- Crear conversación COLLECTING mode:
```bash
python manage.py shell
>>> cliente = Cliente.objects.create(telefono="+1555661289X")
>>> lead = Lead.objects.create(cliente=cliente)
>>> conv = ConversacionWhatsApp.objects.create(cliente=cliente, lead=lead)
>>> BotConversationState.objects.create(
...     conversation_key=f"whatsapp:{conv.pk}",
...     status="collecting",
...     state_data={"origin_district": "San Isidro"}
... )
>>> ConversationOwnership.objects.create(conversation=conv)
>>> print(f"Conversation: {conv.pk}")
>>> exit()
```

**Ejecución:**
- Bot pregunta: "¿De qué distrito?"
- Responder: "De Surco... ah no, de Miraflores"
- Esperado: Bot detecta CORRECTION, no repite pregunta
- Verificar logs: `conversation_action=correction`
- ✅ PASS si: Bot continúa sin repetir

---

## **Escenario 6: Conversación cerrada (no responde)**

**Setup:**
```bash
python manage.py shell
>>> from apps.whatsapp.models import ConversacionWhatsApp
>>> conv = ConversacionWhatsApp.objects.get(pk=<CONV_ID>)
>>> conv.estado_atencion = ConversacionWhatsApp.ATENCION_CERRADA
>>> conv.save()
>>> exit()
```

**Ejecución:**
- Enviar WhatsApp: "¿Hola?"
- Esperado: Webhook devuelve 200, pero crea NUEVA conversación
- Verificar logs: `Closed conversation ignored`
- ✅ PASS si: 2 conversaciones en DB para ese cliente

---

## **Escenario 7: Webhook transaction_completed (cierra conversación)**

**Setup:**
```bash
curl -X POST http://localhost:8001/api/v4/conversation-control/transaction-completed/ \
  -H "Authorization: Bearer <YOUR_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": <CONV_ID>}'
```

**Ejecución:**
- Verificar DB: Conversación tiene `estado_atencion=ATENCION_CERRADA`
- ✅ PASS si: Estado cambió sin error

---

## **Escenario 8: Webhook transaction_cancelled (reabre)**

**Setup:**
```bash
curl -X POST http://localhost:8001/api/v4/conversation-control/transaction-cancelled/ \
  -H "Authorization: Bearer <YOUR_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": <CONV_ID>}'
```

**Ejecución:**
- Verificar DB: Conversación reabierta a `estado_atencion=ATENCION_BOT`
- Enviar WhatsApp: "Tengo otra duda"
- Esperado: Bot responde (no cerrada)
- ✅ PASS si: Conversación reactiva sin error

---

## **Escenario 9: Tono Natural (Verificar en TODOS los replies)**

Buscar en logs ALL bot replies:
- ✅ Presencia de: "te late", "está bien", "dale"
- ✅ NUNCA: "¿Confirmas?", "¿Deseas modificar?", "Por favor"
- ✅ Conversacional: "¿Te late así?" no "¿Confirmas la cotización?"

**Verificar:**
```bash
grep "bot_reply\|reply=" django_debug.log | tail -50
```

---

## **Escenario 10: Latencia Production**

Monitorear en logs para TODOS los escenarios:

```
QUOTED mode:
  - setup: < 50ms
  - context: < 50ms
  - process_turn: < 100ms
  - total: < 300ms

COLLECTING mode:
  - process_turn: 2-5s (OpenAI)
  - total: < 10s (alert threshold)
```

Buscar en logs:
```bash
grep "bot_v4_webhook_latency" django_debug.log
```

✅ PASS si: Todos QUOTED < 300ms, COLLECTING < 10s

---

## **Checklist de Ejecución**

```
ESCENARIOS:
[ ] 1. QUOTED mode precio comunicado
[ ] 2. Asesor takeover → bot suppressed
[ ] 3. Return to bot → reactiva
[ ] 4. NEW_QUOTE → bot reinicia
[ ] 5. CORRECTION → detecta y continúa
[ ] 6. Closed → ignora, crea nueva
[ ] 7. transaction_completed → cierra
[ ] 8. transaction_cancelled → reabre
[ ] 9. Tono natural verificado en todos
[ ] 10. Latencia < thresholds

RESULTADOS:
[ ] 10/10 PASS → LISTO PARA PRODUCCIÓN
[ ] <10/10 → Ir a logs, reportar falla, corregir
```

---

## **Troubleshooting Rápido**

| Error | Fix |
|-------|-----|
| `webhook_received` no aparece | Verificar ngrok URL en Meta |
| `401 Unauthorized` | Token expirado, actualizar |
| `bot_reply=None` | OpenAI error, revisar logs |
| `latency > 10s` | Timeout OpenAI, revisar red |
| API endpoint 404 | Verificar URL exacta y método POST |

---

## **Próximos Pasos**

1. Ejecutar 10 escenarios arriba
2. Si 10/10 PASS → Crear PR con todos los cambios
3. Si alguno FAIL → Reportar error exacto + logs

✅ **Duración estimada:** 30-45 min
