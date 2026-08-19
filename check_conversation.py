#!/usr/bin/env python
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp
from apps.whatsapp_bot_v4.models import BotConversationState

try:
    conv = ConversacionWhatsApp.objects.get(pk=66)
    print('Conversation 66 FOUND')
    print('  cliente: ' + str(conv.cliente.telefono))
    print('  channel_id: ' + str(conv.channel_id))
    print('  bot_pausado: ' + str(conv.bot_pausado))
    print('  estado_atencion: ' + str(conv.estado_atencion))

    msgs = list(conv.mensajes.all().order_by('-fecha_mensaje'))
    print('  Total messages: ' + str(len(msgs)))
    if msgs:
        print('  Last 3:')
        for msg in msgs[:3]:
            origen = 'CLIENT' if msg.origen == MensajeWhatsApp.ORIGEN_CLIENTE else 'BOT'
            print('    [' + origen + '] ' + msg.estado + ': ' + msg.contenido[:60])
except ConversacionWhatsApp.DoesNotExist:
    print('Conversation 66 NOT FOUND')

print()

# Check bot state
state = BotConversationState.objects.filter(conversation_key='whatsapp:66').first()
if state:
    print('Bot State whatsapp:66 FOUND')
    print('  status: ' + state.status)
    print('  updated_at: ' + str(state.updated_at))
    print('  boundary_at: ' + str(state.request_boundary_at))
else:
    print('No bot state for whatsapp:66')
