#!/usr/bin/env python
"""
Quick test: Chat API works with lead_id=NULL
"""
import os
import sys
import django
import uuid

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.test import Client
from django.contrib.auth.models import User, Group
from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel
from django.utils import timezone

# Create user with proper group (use unique username)
username = f"testuser_{uuid.uuid4().hex[:8]}"
user = User.objects.create_user(username, "test@test.com", "testpass")
asesor_group, _ = Group.objects.get_or_create(name="Asesor de Ventas")
user.groups.add(asesor_group)

# Create or get channel (use unique phone_number_id)
channel, _ = WhatsAppChannel.objects.get_or_create(
    phone_number_id=str(uuid.uuid4())[:20],
    defaults={
        'nombre': "Test Channel Lead Null",
        'numero_visible': "+51987654321",
        'asesor': user,
        'activo': True,
    }
)

# Create cliente (use unique phone)
unique_phone = f"+5199{uuid.uuid4().hex[:8]}"
cliente = Cliente.objects.create(
    nombre="Cliente Sin Lead",
    telefono=unique_phone
)

# Create conversation WITHOUT Lead (lead_id=NULL)
conv = ConversacionWhatsApp.objects.create(
    cliente=cliente,
    channel=channel,
    lead=None,  # Explicitly NULL
    estado_atencion=ConversacionWhatsApp.ATENCION_BOT,
)

# Create message (use unique meta_message_id)
msg = MensajeWhatsApp.objects.create(
    conversacion=conv,
    meta_message_id=str(uuid.uuid4()),
    direccion=MensajeWhatsApp.ENTRANTE,
    sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
    contenido="Test message with NULL lead",
    fecha_mensaje=timezone.now(),
)

# Update conversation
conv.ultima_actividad = msg.fecha_mensaje
conv.resumen = msg.contenido[:100]
conv.save()

# Test API access
client = Client()
client.login(username="testuser_null", password="testpass")

# Test 1: Bandeja lists the conversation
print("\n1. Testing Bandeja API with lead_id=NULL...")
resp = client.get("/dashboard/whatsapp/conversaciones/api/active/")
assert resp.status_code == 200, f"Bandeja returned {resp.status_code}"
data = resp.json()
conv_in_bandeja = next((c for c in data['conversations'] if c['id'] == conv.id), None)
assert conv_in_bandeja is not None, "Conversation NOT found in bandeja"
print(f"   ✓ Conversation {conv.id} appears in bandeja")
print(f"   ✓ lead_id={conv_in_bandeja['lead_id']} (NULL)")

# Test 2: Timeline loads messages
print("\n2. Testing Timeline API with lead_id=NULL...")
resp = client.get(f"/dashboard/whatsapp/conversaciones/{conv.id}/mensajes/")
assert resp.status_code == 200, f"Timeline returned {resp.status_code}"
data = resp.json()
assert len(data['messages']) > 0, "No messages in timeline"
print(f"   ✓ Timeline has {len(data['messages'])} message(s)")

# Test 3: Unread counter works
print("\n3. Testing Unread with lead_id=NULL...")
resp = client.get("/dashboard/whatsapp/conversaciones/api/unread/")
assert resp.status_code == 200, f"Unread API returned {resp.status_code}"
data = resp.json()
conv_unread = next((c for c in data['unread_counts'] if c['conversation_id'] == conv.id), None)
assert conv_unread is not None, "Conversation NOT in unread counts"
print(f"   ✓ Conversation tracked in unread (count={conv_unread['unread']})")

print("\n✅ ALL TESTS PASSED: Chat fully functional with lead_id=NULL\n")

# Cleanup
user.delete()
channel.delete()
cliente.delete()
conv.delete()
