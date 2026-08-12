#!/usr/bin/env python
"""Script para poblar datos de prueba en WhatsApp views."""
import os
import django
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import WhatsAppChannel
from apps.cotizador.models import SolicitudCotizacion, CotizacionComercial, RevisionCotizacion

# Get or create admin user
admin = User.objects.filter(username='admin').first()
if not admin:
    admin = User.objects.create_superuser('admin', 'admin@test.com', 'admin')
    print("✓ Admin user created")
else:
    print("✓ Admin user found")

# Get or create WhatsApp channel
channel, created = WhatsAppChannel.objects.get_or_create(
    phone_number_id='123456789',
    defaults={
        'numero_visible': '+51 977 777 777',
        'asesor': admin,
        'activo': True
    }
)
print(f"✓ WhatsApp channel: {channel.numero_visible}")

# Create test clients and leads for "Por cotizar"
clientes_data = [
    {'nombre': 'Juan Pérez Flores', 'telefono': '987654321'},
    {'nombre': 'María García López', 'telefono': '987654322'},
    {'nombre': 'Carlos López Sánchez', 'telefono': '987654323'},
    {'nombre': 'Ana Rodríguez Martinez', 'telefono': '987654324'},
    {'nombre': 'Miguel Sánchez Díaz', 'telefono': '987654325'},
    {'nombre': 'Sofia Martínez González', 'telefono': '987654326'},
    {'nombre': 'Roberto Fernández', 'telefono': '987654327'},
    {'nombre': 'Patricia Gómez Ruiz', 'telefono': '987654328'},
]

leads = []
for data in clientes_data:
    cliente, _ = Cliente.objects.get_or_create(
        telefono=data['telefono'],
        defaults={'nombre': data['nombre']}
    )

    lead, _ = Lead.objects.get_or_create(
        cliente=cliente,
        whatsapp_channel=channel,
        defaults={
            'estado': Lead.NUEVO,
            'distrito_origen': 'Miraflores',
            'distrito_destino': 'San Isidro',
            'direccion_origen': 'Jr. Principal 123',
            'direccion_destino': 'Av. Secundaria 456',
            'vendedor_asignado': admin,
        }
    )
    leads.append(lead)

print(f"✓ Created/found {len(leads)} leads")

# Create SolicitudCotizacion (for "Por cotizar" view)
solicitudes_data = [
    {'lead': leads[0], 'estado': SolicitudCotizacion.PENDIENTE, 'prioridad': Lead.PRIORIDAD_NORMAL, 'motivo': 'Cliente solicita presupuesto'},
    {'lead': leads[1], 'estado': SolicitudCotizacion.PENDIENTE, 'prioridad': Lead.PRIORIDAD_URGENTE, 'motivo': 'Mudanza mañana urgente'},
    {'lead': leads[2], 'estado': SolicitudCotizacion.EN_PROCESO, 'prioridad': Lead.PRIORIDAD_NORMAL, 'motivo': 'Esperando confirmación'},
    {'lead': leads[3], 'estado': SolicitudCotizacion.PENDIENTE, 'prioridad': Lead.PRIORIDAD_BAJA, 'motivo': 'Solicitud informativa'},
    {'lead': leads[4], 'estado': SolicitudCotizacion.PENDIENTE, 'prioridad': Lead.PRIORIDAD_URGENTE, 'motivo': 'Cliente insiste en cotización'},
]

solicitudes = []
for data in solicitudes_data:
    solicitud, created = SolicitudCotizacion.objects.get_or_create(
        lead=data['lead'],
        defaults={
            'estado': data['estado'],
            'prioridad': data['prioridad'],
            'motivo': data['motivo'],
            'creada_por': admin,
        }
    )
    if created:
        print(f"  ✓ Solicitud creada: {data['lead'].cliente.nombre}")
    solicitudes.append(solicitud)

print(f"✓ Created {len(solicitudes)} solicitudes de cotización")

# Create CotizacionComercial (for "Cotizaciones" view)
cotizaciones_data = [
    {'lead': leads[5], 'estado': CotizacionComercial.ENVIADA, 'codigo': 'COT-2026-001'},
    {'lead': leads[4], 'estado': CotizacionComercial.ENTREGADA, 'codigo': 'COT-2026-002'},
    {'lead': leads[3], 'estado': CotizacionComercial.EN_NEGOCIACION, 'codigo': 'COT-2026-003'},
    {'lead': leads[2], 'estado': CotizacionComercial.ACEPTADA, 'codigo': 'COT-2026-004'},
    {'lead': leads[1], 'estado': CotizacionComercial.RECHAZADA, 'codigo': 'COT-2026-005'},
    {'lead': leads[0], 'estado': CotizacionComercial.VENCIDA, 'codigo': 'COT-2026-006'},
    {'lead': leads[6], 'estado': CotizacionComercial.ENVIADA, 'codigo': 'COT-2026-007'},
    {'lead': leads[7], 'estado': CotizacionComercial.EN_NEGOCIACION, 'codigo': 'COT-2026-008'},
]

cotizaciones = []
for data in cotizaciones_data:
    cotizacion, created = CotizacionComercial.objects.get_or_create(
        lead=data['lead'],
        channel=channel,
        defaults={
            'codigo': data['codigo'],
            'estado': data['estado'],
            'asesor': admin,
            'origen': 'whatsapp',
        }
    )

    # Create revisions for each quotation
    if created:
        revision, _ = RevisionCotizacion.objects.get_or_create(
            cotizacion=cotizacion,
            numero=1,
            defaults={
                'precio_final': Decimal('350.00') + (Decimal('50.00') * len(cotizaciones)),
                'descripcion': f'Presupuesto para {data["lead"].cliente.nombre}',
                'usuario_creo': admin,
            }
        )
        print(f"  ✓ Cotización creada: {data['codigo']} - {data['lead'].cliente.nombre}")

    cotizaciones.append(cotizacion)

print(f"✓ Created {len(cotizaciones)} cotizaciones comerciales")

# Summary
print("\n" + "="*60)
print("DATOS DE PRUEBA CARGADOS EXITOSAMENTE")
print("="*60)
print(f"Clientes:          {Cliente.objects.count()}")
print(f"Leads:             {Lead.objects.count()}")
print(f"Solicitudes:       {SolicitudCotizacion.objects.count()}")
print(f"Cotizaciones:      {CotizacionComercial.objects.count()}")
print(f"Revisiones:        {RevisionCotizacion.objects.count()}")
print(f"\nCanal WhatsApp: {channel.numero_visible}")
print(f"Admin user: admin / admin")
print("\nAccede a:")
print("  - Por cotizar:    http://localhost:8001/dashboard/whatsapp/")
print("  - Cotizaciones:   http://localhost:8001/dashboard/whatsapp/cotizaciones/")
print("  - Conversaciones: http://localhost:8001/dashboard/whatsapp/conversaciones/")
print("="*60)
