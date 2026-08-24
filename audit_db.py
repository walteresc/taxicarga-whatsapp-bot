#!/usr/bin/env python
"""Audit database state and reconcile test data."""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
from django.conf import settings
from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp

print("="*70)
print("DATABASE AUDIT - FASE 5B LOCAL TEST RECONCILIATION")
print("="*70)

# ============================================================
# 1. CONNECTION INFO
# ============================================================

print("\n[CONNECTION]")
print(f"  Vendor: {connection.vendor}")
print(f"  Database: {connection.settings_dict.get('NAME')}")
print(f"  Host: {connection.settings_dict.get('HOST', 'default')}")
print(f"  Port: {connection.settings_dict.get('PORT', 'default')}")
print(f"  User: {connection.settings_dict.get('USER', 'default')}")
print(f"  Process PID: {os.getpid()}")

# Check current database
with connection.cursor() as cursor:
    if connection.vendor == 'postgresql':
        cursor.execute("SELECT current_database();")
    else:
        cursor.execute("PRAGMA database_list;")
    result = cursor.fetchone()
    print(f"  Current DB Query Result: {result}")

# ============================================================
# 2. TABLE MAXIMUMS
# ============================================================

print("\n[MAX IDS]")

max_cliente = Cliente.objects.aggregate(max_id=__import__('django.db.models', fromlist=['Max']).Max('id'))['max_id']
max_conv = ConversacionWhatsApp.objects.aggregate(max_id=__import__('django.db.models', fromlist=['Max']).Max('id'))['max_id']
max_msg = MensajeWhatsApp.objects.aggregate(max_id=__import__('django.db.models', fromlist=['Max']).Max('id'))['max_id']

print(f"  Cliente: MAX(id) = {max_cliente}")
print(f"  ConversacionWhatsApp: MAX(id) = {max_conv}")
print(f"  MensajeWhatsApp: MAX(id) = {max_msg}")

# ============================================================
# 3. ROWS IN QUESTION
# ============================================================

print("\n[SUSPICIOUS ROWS]")

# Cliente 168
try:
    c168 = Cliente.objects.get(id=168)
    print(f"\n  Cliente 168: FOUND")
    print(f"    - nombre: {c168.nombre}")
    print(f"    - telefono: {c168.telefono}")
    print(f"    - documento: {c168.documento}")
    print(f"    - fecha_creacion: {c168.fecha_creacion}")
except Cliente.DoesNotExist:
    print(f"\n  Cliente 168: NOT FOUND")

# Conversation 234
try:
    conv234 = ConversacionWhatsApp.objects.get(id=234)
    print(f"\n  Conversation 234: FOUND")
    print(f"    - cliente_id: {conv234.cliente_id}")
    print(f"    - resumen: {conv234.resumen}")
    print(f"    - creada_en: {conv234.creada_en}")
except ConversacionWhatsApp.DoesNotExist:
    print(f"\n  Conversation 234: NOT FOUND")

# Conversation 236
try:
    conv236 = ConversacionWhatsApp.objects.get(id=236)
    print(f"\n  Conversation 236: FOUND")
    print(f"    - cliente_id: {conv236.cliente_id}")
    print(f"    - resumen: {conv236.resumen}")
    print(f"    - creada_en: {conv236.creada_en}")
except ConversacionWhatsApp.DoesNotExist:
    print(f"\n  Conversation 236: NOT FOUND")

# Message 811
try:
    msg811 = MensajeWhatsApp.objects.get(id=811)
    print(f"\n  Message 811: FOUND")
    print(f"    - conversacion_id: {msg811.conversacion_id}")
    print(f"    - meta_message_id: {msg811.meta_message_id}")
    print(f"    - contenido: {msg811.contenido}")
    print(f"    - creado_en: {msg811.creado_en}")
except MensajeWhatsApp.DoesNotExist:
    print(f"\n  Message 811: NOT FOUND")

# Message 844
try:
    msg844 = MensajeWhatsApp.objects.get(id=844)
    print(f"\n  Message 844: FOUND")
    print(f"    - conversacion_id: {msg844.conversacion_id}")
    print(f"    - meta_message_id: {msg844.meta_message_id}")
    print(f"    - contenido: {msg844.contenido}")
    print(f"    - creado_en: {msg844.creado_en}")
except MensajeWhatsApp.DoesNotExist:
    print(f"\n  Message 844: NOT FOUND")

# ============================================================
# 4. SEARCH FOR F5B-195530
# ============================================================

print("\n[SEARCH: F5B-195530]")

clientes_f5b = Cliente.objects.filter(nombre__icontains="F5B-195530")
print(f"  Clientes with F5B-195530: {clientes_f5b.count()}")
for c in clientes_f5b:
    print(f"    - id={c.id}, nombre={c.nombre}, telefono={c.telefono}")

convs_f5b = ConversacionWhatsApp.objects.filter(resumen__icontains="F5B-195530")
print(f"  Conversations with F5B-195530: {convs_f5b.count()}")
for conv in convs_f5b:
    print(f"    - id={conv.id}, cliente_id={conv.cliente_id}, resumen={conv.resumen}")

msgs_f5b = MensajeWhatsApp.objects.filter(contenido__icontains="F5B-195530")
print(f"  Messages with F5B-195530: {msgs_f5b.count()}")
for msg in msgs_f5b:
    print(f"    - id={msg.id}, conversacion_id={msg.conversacion_id}, wamid={msg.meta_message_id}")

# ============================================================
# 5. CONCLUSION
# ============================================================

print("\n" + "="*70)
print("AUDIT COMPLETE - No modifications made to data")
print("="*70)
