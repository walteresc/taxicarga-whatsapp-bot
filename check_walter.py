import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_e2e'

import django
django.setup()

from apps.clientes.models import Cliente
from apps.whatsapp.models import Conversacion

# Query Walter
clients = Cliente.objects.all()
print(f"Total clientes: {clients.count()}")

# Search for Walter (try different patterns)
walter = None
for c in clients:
    if '995403320' in (c.telefono or ''):
        walter = c
        break

if walter:
    print(f"FOUND - {walter.id}: {walter.telefono} ({walter.nombre})")
    conv = Conversacion.objects.filter(cliente=walter).first()
    if conv:
        print(f"  Conversation: {conv.id}")
        print(f"  Messages: {conv.mensajes.count()}")
else:
    print("NOT_FOUND")
    # Show sample of telefono values
    for c in clients[:3]:
        print(f"  Sample: '{c.telefono}'")
