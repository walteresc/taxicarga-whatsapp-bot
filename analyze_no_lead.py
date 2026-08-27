#!/usr/bin/env python
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, 'd:/DESARROLLO_IA/Proyecto_taxi_carga/Taxi_carga_bot/taxicarga_whatsapp_bot')
django.setup()

from apps.whatsapp.models import ConversacionWhatsApp

# All conversaciones without Lead
no_lead = ConversacionWhatsApp.objects.filter(lead_id__isnull=True).order_by('id')

print(f'Total conversaciones sin Lead: {no_lead.count()}')
print()

# Breakdown by estado
print('ESTADO_ATENCION:')
for estado in ['bot', 'asesor', 'cerrada']:
    count = no_lead.filter(estado_atencion=estado).count()
    if count > 0:
        print(f'  {estado}: {count}')

# With/without messages
with_msgs = 0
without_msgs = 0
for conv in no_lead:
    if conv.mensajes.count() > 0:
        with_msgs += 1
    else:
        without_msgs += 1

print(f'\nCON MENSAJES: {with_msgs}')
print(f'SIN MENSAJES: {without_msgs}')

# Sample of each
print(f'\nPRIMERAS 15 (sin Lead):')
for i, conv in enumerate(no_lead[:15], 1):
    msg_count = conv.mensajes.count()
    print(f'{i:2d}. Conv {conv.id:3d} | cliente={conv.cliente_id:3d} | estado={conv.estado_atencion:6s} | msgs={msg_count:2d} | creada={conv.creada_en.date()}')

# Date range
print(f'\nFECHAS:')
oldest_date = no_lead.values_list('creada_en', flat=True).order_by('creada_en').first()
newest_date = no_lead.values_list('creada_en', flat=True).order_by('-creada_en').first()
print(f'  Más antigua: {oldest_date}')
print(f'  Más reciente: {newest_date}')

# Are they active?
print(f'\nESTADO:')
active = no_lead.exclude(estado_atencion='cerrada').count()
closed = no_lead.filter(estado_atencion='cerrada').count()
print(f'  Activas: {active}')
print(f'  Cerradas: {closed}')
