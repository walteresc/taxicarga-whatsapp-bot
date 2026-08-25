import os, django
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_e2e'
django.setup()

from django.contrib.auth.models import User
from apps.whatsapp.models import WhatsAppChannel
from apps.clientes.models import Cliente

user, _ = User.objects.get_or_create(username='testadmin')
print(f"User: {user.username}")

cliente, _ = Cliente.objects.get_or_create(telefono='34123456789', defaults={'nombre': 'Test E2E'})
print(f"Cliente: {cliente.telefono}")

channel, _ = WhatsAppChannel.objects.get_or_create(
    phone_number_id='123456789',
    defaults={'phone_number': '34123456789', 'asesor': user, 'activo': True}
)
print(f"Channel: {channel.phone_number_id}, active={channel.activo}")
print(f"Active channels: {WhatsAppChannel.objects.filter(activo=True).count()}")
