from django.conf import settings
from django.core.management.base import BaseCommand

from apps.whatsapp.services import send_whatsapp_message


class Command(BaseCommand):
    help = "Revisa la configuracion de WhatsApp Cloud API y puede enviar un mensaje de prueba."

    def add_arguments(self, parser):
        parser.add_argument(
            "--send-to",
            default="",
            help="Telefono destino en formato WhatsApp, por ejemplo 51999999999.",
        )
        parser.add_argument(
            "--message",
            default="Prueba de conexion TaxiCarga.",
            help="Mensaje de prueba para enviar por WhatsApp.",
        )
        parser.add_argument(
            "--public-url",
            default="",
            help="URL publica base, por ejemplo https://xxxx.ngrok-free.app.",
        )

    def handle(self, *args, **options):
        checks = [
            ("WHATSAPP_VERIFY_TOKEN", bool(settings.WHATSAPP_VERIFY_TOKEN)),
            ("WHATSAPP_ACCESS_TOKEN", bool(settings.WHATSAPP_ACCESS_TOKEN)),
            ("WHATSAPP_PHONE_NUMBER_ID", bool(settings.WHATSAPP_PHONE_NUMBER_ID)),
            ("WHATSAPP_API_VERSION", bool(settings.WHATSAPP_API_VERSION)),
        ]

        self.stdout.write("Diagnostico WhatsApp Cloud API")
        for name, configured in checks:
            status = self.style.SUCCESS("OK") if configured else self.style.ERROR("FALTA")
            self.stdout.write(f"- {name}: {status}")

        public_url = options["public_url"].rstrip("/")
        if public_url:
            self.stdout.write("")
            self.stdout.write("Webhook para Meta:")
            self.stdout.write(f"{public_url}/webhook/whatsapp/")
            self.stdout.write(f"Verify token: {settings.WHATSAPP_VERIFY_TOKEN}")

        if options["send_to"]:
            self.stdout.write("")
            self.stdout.write(f"Enviando mensaje de prueba a {options['send_to']}...")
            result = send_whatsapp_message(options["send_to"], options["message"])
            self.stdout.write(str(result))
            if result.get("sent") is False:
                self.stdout.write(self.style.WARNING("El mensaje no se envio. Revisa credenciales y permisos."))
            else:
                self.stdout.write(self.style.SUCCESS("Solicitud enviada a Meta."))
