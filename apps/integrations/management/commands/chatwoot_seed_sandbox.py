from django.core.management.base import BaseCommand

from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel


class Command(BaseCommand):
    help = "Crea una conversación Django aislada para smoke tests Chatwoot."

    def handle(self, *args, **options):
        cliente, _ = Cliente.objects.get_or_create(
            telefono="stage5-sandbox-local-only",
            defaults={"nombre": "TEST TaxiCarga Stage 5"},
        )
        channel, _ = WhatsAppChannel.objects.get_or_create(
            phone_number_id="stage5-sandbox-no-meta",
            defaults={"nombre": "TEST Chatwoot Sandbox", "activo": False},
        )
        conversation, created = ConversacionWhatsApp.objects.get_or_create(cliente=cliente, channel=channel)
        if created:
            MensajeWhatsApp.objects.create(
                conversacion=conversation, direccion="entrante", origen="cliente", tipo="texto",
                contenido="TEST ETAPA 5: necesito transportar cajas.", estado="recibido",
            )
            MensajeWhatsApp.objects.create(
                conversacion=conversation, direccion="saliente", origen="bot", tipo="texto",
                contenido="TEST ETAPA 5: mensaje proyectado por Django.", estado="enviado",
            )
        self.stdout.write(f"SANDBOX django_conversation_id={conversation.id} action={'created' if created else 'reused'}")
