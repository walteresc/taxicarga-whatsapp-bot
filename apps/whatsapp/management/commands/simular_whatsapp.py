from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.clientes.models import Cliente, Conversacion
from apps.ia.conversation_engine import handle_incoming_message


class Command(BaseCommand):
    help = "Simula un mensaje entrante de WhatsApp sin llamar a Meta."

    def add_arguments(self, parser):
        parser.add_argument("message", help="Mensaje del cliente.")
        parser.add_argument(
            "--phone",
            default="51999999999",
            help="Telefono del cliente en formato WhatsApp.",
        )

    def handle(self, *args, **options):
        phone = options["phone"]
        message = options["message"]

        cliente, _ = Cliente.objects.get_or_create(telefono=phone)
        cliente.ultima_interaccion = timezone.now()
        cliente.save(update_fields=["ultima_interaccion"])

        reply = handle_incoming_message(cliente, message)
        Conversacion.objects.create(
            cliente=cliente,
            mensaje_entrada=message,
            mensaje_salida=reply,
            canal=Conversacion.CANAL_WHATSAPP,
        )

        lead = cliente.leads.first()
        self.stdout.write(self.style.SUCCESS("Mensaje procesado."))
        self.stdout.write(f"Cliente: {cliente.telefono}")
        if lead:
            self.stdout.write(f"Lead: {lead.id} | Estado: {lead.estado}")
            self.stdout.write(
                "Datos: "
                f"{lead.tipo_servicio or '-'} | "
                f"{lead.distrito_origen or '-'} -> {lead.distrito_destino or '-'}"
            )
        self.stdout.write(f"Respuesta: {reply}")
