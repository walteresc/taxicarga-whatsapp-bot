from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from random import choice, randint

from apps.clientes.models import Cliente, Conversacion
from apps.leads.models import Lead
from apps.whatsapp.models import WhatsAppChannel

SERVICIOS = ["mudanza", "carga", "flete", "mudanza", "carga"]
DISTRITOS = [
    "Miraflores", "San Isidro", "Surco", "San Miguel", "La Molina",
    "Barranco", "Jesus Maria", "Lince", "Pueblo Libre", "Magdalena",
    "San Borja", "Santiago de Surco", "Los Olivos", "Comas", "San Juan de Lurigancho",
    "Ate", "Chorrillos", "Callao", "Breña", "Rimac",
]
TIPOS_CAMION = ["camion 8m", "camion 12m", "camion 6m", "camioneta", "camion 10m"]
ESTADOS = [Lead.NUEVO, Lead.EN_CONVERSACION, Lead.DATOS_INCOMPLETOS, Lead.COTIZADO]
PRIORIDADES = [Lead.PRIORIDAD_BAJA, Lead.PRIORIDAD_MEDIA, Lead.PRIORIDAD_ALTA, Lead.PRIORIDAD_URGENTE]
OBJETOS = [
    "cama, ropero, mesa, sillas, cajas",
    "refrigeradora, cocina, lavadora, cajas",
    "sillones, mesa comedor, televisor, cajas",
    "camas, colchones, ropero, escritorio",
    "cajas, libros, archivos, equipo computo",
    "maquinaria, herramientas, cajas",
    "mercaderia, cajas, estantes",
    "muebles de oficina, sillas, escritorios",
]
NOMBRES = [
    "Juan Perez", "Maria Garcia", "Carlos Lopez", "Ana Martinez", "Pedro Ramirez",
    "Lucia Fernandez", "Diego Torres", "Sofia Castillo", "Miguel Vargas", "Carolina Rios",
    "Fernando Diaz", "Gabriela Herrera", "Jorge Mendoza", "Valentina Ruiz", "Andres Vega",
    "Camila Navarro", "Roberto Guerrero", "Daniela Campos", "Alejandro Silva", "Paula Ortiz",
    "Francisco Muñoz", "Renata Delgado", "Sergio Paredes", "Belen Aguilar", "Luis Romero",
    "Elena Quispe", "Hugo Vera", "Ximena Cardenas", "Pablo Rojas", "Adriana Flores",
]


class Command(BaseCommand):
    help = "Crea leads de prueba para Taxi Carga (25) y Lima Express (2)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Elimina los leads y clientes de prueba antes de crear nuevos",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self._clear_data()

        channel_taxi, _ = WhatsAppChannel.objects.get_or_create(
            phone_number_id="seed_taxi_carga",
            defaults={"nombre": "Taxi Carga", "numero_visible": "51999000001"},
        )
        channel_lima, _ = WhatsAppChannel.objects.get_or_create(
            phone_number_id="seed_lima_express",
            defaults={"nombre": "Lima Express", "numero_visible": "51999000002"},
        )

        created_taxi = 0
        for i in range(25):
            nombre = NOMBRES[i]
            telefono = f"519900{i:04d}01"
            cliente, c_created = Cliente.objects.get_or_create(
                telefono=telefono, defaults={"nombre": nombre}
            )
            if not c_created:
                continue
            lead = self._create_lead(cliente, channel_taxi, i)
            self._add_conversaciones(cliente, randint(2, 8))
            created_taxi += 1
            self.stdout.write(f"  [{created_taxi}] Lead {lead.id} - {nombre} ({lead.estado})")

        created_lima = 0
        for i in range(2):
            nombre = NOMBRES[25 + i]
            telefono = f"519900{i:04d}51"
            cliente, c_created = Cliente.objects.get_or_create(
                telefono=telefono, defaults={"nombre": nombre}
            )
            if not c_created:
                continue
            lead = self._create_lead(cliente, channel_lima, 25 + i)
            self._add_conversaciones(cliente, randint(2, 5))
            created_lima += 1
            self.stdout.write(f"  [{created_lima}] Lead {lead.id} - {nombre} ({lead.estado})")

        self.stdout.write(self.style.SUCCESS(
            f"\nCreados {created_taxi} leads en Taxi Carga + {created_lima} en Lima Express"
        ))

    def _create_lead(self, cliente, channel, idx):
        origen = choice(DISTRITOS)
        destino = choice([d for d in DISTRITOS if d != origen])
        dias_atras = choice([0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 5, 7, 10])
        fecha_servicio = timezone.now().date() + timedelta(days=randint(0, 14))
        peso = Decimal(str(randint(50, 500)))
        volumen = Decimal(str(randint(1, 20)))

        estado = choice(ESTADOS)
        lead = Lead.objects.create(
            cliente=cliente,
            whatsapp_channel=channel,
            estado=estado,
            prioridad=choice(PRIORIDADES),
            tipo_servicio=choice(SERVICIOS),
            distrito_origen=origen,
            distrito_destino=destino,
            direccion_origen=f"Av. {origen} {randint(100,2000)}",
            direccion_destino=f"Calle {destino} {randint(100,2000)}",
            piso_origen=choice([1, 2, 2, 3, 3, 4, 5, None]),
            piso_destino=choice([1, 1, 2, 2, 3, None]),
            ascensor_origen=choice([True, False, None]),
            ascensor_destino=choice([True, False, None]),
            lista_objetos=choice(OBJETOS),
            tipo_camion=choice(TIPOS_CAMION),
            fecha_servicio=fecha_servicio,
            horario_servicio=choice(["08:00", "09:00", "10:00", "14:00", "16:00"]),
            peso_carga_kg=peso,
            volumen_carga_m3=volumen,
            fecha_creacion=timezone.now() - timedelta(days=dias_atras),
        )
        return lead

    def _add_conversaciones(self, cliente, count):
        ahora = timezone.now()
        for i in range(count):
            Conversacion.objects.create(
                cliente=cliente,
                mensaje_entrada=f"Mensaje de entrada {i + 1}",
                mensaje_salida=f"Respuesta automatica {i + 1}",
                canal=Conversacion.CANAL_WHATSAPP,
                fecha=ahora - timedelta(minutes=(count - i) * 5),
            )

    def _clear_data(self):
        canales = WhatsAppChannel.objects.filter(
            phone_number_id__in=["seed_taxi_carga", "seed_lima_express"]
        )
        leads = Lead.objects.filter(whatsapp_channel__in=canales)
        clientes_ids = leads.values_list("cliente_id", flat=True)
        Conversacion.objects.filter(cliente_id__in=clientes_ids).delete()
        leads.delete()
        Cliente.objects.filter(id__in=clientes_ids).delete()
        canales.delete()
        self.stdout.write("Datos de prueba eliminados.")
