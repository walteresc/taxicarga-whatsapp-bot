#!/usr/bin/env python
"""Script para poblar datos de prueba en la BD."""
import os
import django
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from apps.clientes.models import Cliente, Conversacion
from apps.leads.models import Lead
from apps.whatsapp.models import WhatsAppChannel
from apps.servicios.models import Servicio, PagoReserva
from apps.cotizador.models import SolicitudCotizacion, CotizacionComercial

# Crear usuario admin si no existe
admin, _ = User.objects.get_or_create(
    username='admin',
    defaults={'email': 'admin@taxicarga.test', 'is_staff': True, 'is_superuser': True}
)
if not admin.check_password('admin'):
    admin.set_password('admin')
    admin.save()

# Crear canal WhatsApp
channel, _ = WhatsAppChannel.objects.get_or_create(
    phone_number_id='123456789',
    defaults={
        'numero_visible': '+51 977 777 777',
        'asesor': admin,
        'activo': True
    }
)

# Clientes de prueba
clientes_data = [
    {'nombre': 'Juan Pérez', 'telefono': '987654321', 'documento': '12345678'},
    {'nombre': 'María García', 'telefono': '987654322', 'documento': '12345679'},
    {'nombre': 'Carlos López', 'telefono': '987654323', 'documento': '12345680'},
    {'nombre': 'Ana Rodríguez', 'telefono': '987654324', 'documento': '12345681'},
    {'nombre': 'Miguel Sánchez', 'telefono': '987654325', 'documento': '12345682'},
    {'nombre': 'Sofia Martínez', 'telefono': '987654326', 'documento': '12345683'},
]

clientes = []
for data in clientes_data:
    cliente, _ = Cliente.objects.get_or_create(
        telefono=data['telefono'],
        defaults={'nombre': data['nombre'], 'documento': data['documento']}
    )
    clientes.append(cliente)

# Leads de prueba
leads_data = [
    {'cliente': clientes[0], 'estado': Lead.NUEVO, 'distrito_origen': 'Miraflores', 'distrito_destino': 'San Isidro'},
    {'cliente': clientes[1], 'estado': Lead.EN_CONVERSACION, 'distrito_origen': 'Barranco', 'distrito_destino': 'La Molina'},
    {'cliente': clientes[2], 'estado': Lead.COTIZADO, 'distrito_origen': 'Breña', 'distrito_destino': 'Ate'},
    {'cliente': clientes[3], 'estado': Lead.ASIGNADO, 'distrito_origen': 'Rímac', 'distrito_destino': 'Chorrillos'},
    {'cliente': clientes[4], 'estado': Lead.DATOS_INCOMPLETOS, 'distrito_origen': 'San Martín', 'distrito_destino': 'Magdalena'},
    {'cliente': clientes[5], 'estado': Lead.PERDIDO, 'distrito_origen': 'Independencia', 'distrito_destino': 'Puente Piedra'},
]

leads = []
for data in leads_data:
    lead, _ = Lead.objects.get_or_create(
        cliente=data['cliente'],
        defaults={
            'estado': data['estado'],
            'direccion_origen': f"Jr. Principal 100, {data['distrito_origen']}",
            'direccion_destino': f"Av. Secundaria 200, {data['distrito_destino']}",
            'whatsapp_channel': channel,
            'vendedor_asignado': admin,
        }
    )
    leads.append(lead)

# Conversaciones
for cliente in clientes:
    Conversacion.objects.get_or_create(
        cliente=cliente,
        canal='whatsapp',
        defaults={
            'mensaje_entrada': 'Hola, quiero un presupuesto para una mudanza',
            'mensaje_salida': 'Claro, en un momento te doy el presupuesto',
        }
    )

# Servicios de prueba
servicios_data = [
    {'lead': leads[0], 'estado': Servicio.PENDIENTE, 'precio': Decimal('400'), 'direccion_origen': 'Jr. Principal, Miraflores', 'direccion_destino': 'Av. Secundaria, San Isidro'},
    {'lead': leads[1], 'estado': Servicio.PROGRAMADO, 'precio': Decimal('500'), 'direccion_origen': 'Av. Bolognesi, Barranco', 'direccion_destino': 'Av. Las Artes, La Molina'},
    {'lead': leads[2], 'estado': Servicio.ASIGNADO, 'precio': Decimal('350'), 'direccion_origen': 'Av. Grau, Breña', 'direccion_destino': 'Av. San Carlos, Ate'},
    {'lead': leads[3], 'estado': Servicio.EN_RUTA, 'precio': Decimal('600'), 'direccion_origen': 'Paseo de la República, Rímac', 'direccion_destino': 'Av. Javier Prado, Chorrillos'},
    {'lead': leads[4], 'estado': Servicio.FINALIZADO, 'precio': Decimal('450'), 'direccion_origen': 'Calle 28, San Martín', 'direccion_destino': 'Av. Universitaria, Magdalena'},
]

for data in servicios_data:
    servicio, created = Servicio.objects.get_or_create(
        lead_origen=data['lead'],
        defaults={
            'cliente': data['lead'].cliente,
            'estado': data['estado'],
            'precio': data['precio'],
            'direccion_origen': data['direccion_origen'],
            'direccion_destino': data['direccion_destino'],
            'asesor': admin,
        }
    )

    # Agregar pagos a algunos servicios
    if data['estado'] in (Servicio.FINALIZADO, Servicio.EN_RUTA):
        PagoReserva.objects.get_or_create(
            servicio=servicio,
            defaults={
                'monto': data['precio'] * Decimal('0.5'),
                'concepto': 'adelanto',
                'metodo_pago': 'yape',
                'usuario_registro': admin,
            }
        )

# Solicitudes de cotización
for i, lead in enumerate(leads[:3]):
    SolicitudCotizacion.objects.get_or_create(
        lead=lead,
        defaults={
            'estado': 'pendiente' if i == 0 else 'aceptada',
            'monto_solicitado': Decimal('450'),
            'cliente': lead.cliente,
        }
    )

# Cotizaciones comerciales
for i, lead in enumerate(leads[1:4]):
    CotizacionComercial.objects.get_or_create(
        lead=lead,
        defaults={
            'monto_propuesto': Decimal('500') + (i * Decimal('50')),
            'estado': ['en_negociacion', 'aceptada', 'rechazada'][i],
            'usuario_creo': admin,
        }
    )

print("✓ Datos de prueba cargados exitosamente")
print(f"  - {len(clientes)} clientes")
print(f"  - {leads.count()} leads")
print(f"  - {Conversacion.objects.count()} conversaciones")
print(f"  - {Servicio.objects.count()} servicios")
print(f"  - {PagoReserva.objects.count()} pagos")
