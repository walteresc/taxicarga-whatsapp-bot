from django.core.management.base import BaseCommand

from apps.cotizador.delivery import reintentar_envios_vencidos


class Command(BaseCommand):
    help = "Reintenta envíos de cotizaciones WhatsApp vencidos."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        envios = reintentar_envios_vencidos(limit=max(1, options["limit"]))
        self.stdout.write(self.style.SUCCESS(f"Procesados: {len(envios)}"))
