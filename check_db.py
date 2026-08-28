#!/usr/bin/env python
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from django.db import connection

print("[DATABASE CONFIG]")
print(f"ENGINE: {settings.DATABASES['default']['ENGINE']}")
print(f"NAME: {settings.DATABASES['default']['NAME']}")
print(f"HOST: {settings.DATABASES['default'].get('HOST', 'N/A')}")
print()

cursor = connection.cursor()
cursor.execute("SELECT current_database();")
db_name = cursor.fetchone()
if db_name:
    print(f"[PostgreSQL current_database]: {db_name[0]}")
else:
    print("[PostgreSQL]: No database selected")
print()

from apps.whatsapp.models import ConversacionWhatsApp
from apps.clientes.models import Conversacion

legacy_count = Conversacion.objects.count()
whatsapp_count = ConversacionWhatsApp.objects.count()
activas_count = ConversacionWhatsApp.objects.filter(cerrada_en__isnull=True).count()
api_count = ConversacionWhatsApp.objects.filter(cerrada_en__isnull=True).order_by('-ultima_actividad')[:100].count()

print("[COUNTS]")
print(f"Conversacion (legacy): {legacy_count}")
print(f"ConversacionWhatsApp (total): {whatsapp_count}")
print(f"ConversacionWhatsApp (activas): {activas_count}")
print(f"API [:100]: {api_count}")
