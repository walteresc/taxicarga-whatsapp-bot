from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp


class Command(BaseCommand):
    help = "Repair WhatsApp conversation summary, timestamps, and takeover state"

    def add_arguments(self, parser):
        parser.add_argument(
            "--conversation-id",
            type=int,
            required=True,
            help="Conversation ID to repair",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without applying",
        )

    def handle(self, *args, **options):
        conv_id = options["conversation_id"]
        dry_run = options["dry_run"]

        try:
            conv = ConversacionWhatsApp.objects.get(pk=conv_id)
        except ConversacionWhatsApp.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Conversation {conv_id} not found"))
            return

        # Get all messages ordered by fecha_mensaje
        messages = MensajeWhatsApp.objects.filter(
            conversacion=conv
        ).order_by("fecha_mensaje")

        if not messages.exists():
            self.stdout.write(self.style.WARNING(f"No messages in conversation {conv_id}"))
            return

        last_msg = messages.last()
        self.stdout.write(self.style.SUCCESS(f"\n{'='*80}"))
        self.stdout.write(self.style.SUCCESS(f"CONVERSATION {conv_id} REPAIR ANALYSIS"))
        self.stdout.write(self.style.SUCCESS(f"{'='*80}"))
        self.stdout.write(f"Total messages: {messages.count()}")
        self.stdout.write(f"Cliente: {conv.cliente.nombre if conv.cliente else 'N/A'}")
        self.stdout.write(f"Channel: {conv.channel.nombre if conv.channel else 'N/A'}")

        # Current state
        self.stdout.write(f"\n--- CURRENT STATE ---")
        self.stdout.write(f"ultima_actividad: {conv.ultima_actividad}")
        self.stdout.write(f"resumen: '{conv.resumen}'")
        self.stdout.write(f"bot_pausado: {conv.bot_pausado}")
        self.stdout.write(f"estado_atencion: {conv.estado_atencion}")

        # Expected state from last message
        self.stdout.write(f"\n--- EXPECTED STATE (from last message) ---")
        self.stdout.write(f"Last message ID: {last_msg.id}")
        self.stdout.write(f"Last message wamid: {last_msg.meta_message_id}")
        self.stdout.write(f"Last message direction: {last_msg.direccion}")
        self.stdout.write(f"Last message sender_type: {last_msg.sender_type}")
        self.stdout.write(f"Last message source: {last_msg.source}")
        self.stdout.write(f"Last message timestamp: {last_msg.fecha_mensaje}")
        self.stdout.write(f"Last message content: '{last_msg.contenido[:80]}'")

        # Compute changes
        changes = {}

        if conv.ultima_actividad != last_msg.fecha_mensaje:
            changes["ultima_actividad"] = {
                "current": conv.ultima_actividad,
                "expected": last_msg.fecha_mensaje,
            }

        expected_resumen = last_msg.contenido[:100]
        if conv.resumen != expected_resumen:
            changes["resumen"] = {
                "current": conv.resumen,
                "expected": expected_resumen,
            }

        # Check takeover: if last outbound is from whatsapp_business_app, should be paused
        last_outbound = (
            messages.filter(direccion=MensajeWhatsApp.SALIENTE)
            .order_by("-fecha_mensaje")
            .first()
        )
        if (last_outbound and
            last_outbound.source == MensajeWhatsApp.SOURCE_WHATSAPP_BUSINESS_APP and
            last_outbound.sender_type == MensajeWhatsApp.SENDER_ADVISOR):
            if not conv.bot_pausado:
                changes["bot_pausado"] = {
                    "current": conv.bot_pausado,
                    "expected": True,
                }
            if conv.estado_atencion != ConversacionWhatsApp.ATENCION_ASESOR:
                changes["estado_atencion"] = {
                    "current": conv.estado_atencion,
                    "expected": ConversacionWhatsApp.ATENCION_ASESOR,
                }

        # Report changes
        if not changes:
            self.stdout.write(self.style.SUCCESS(f"\n✓ No changes needed"))
        else:
            self.stdout.write(self.style.WARNING(f"\n--- CHANGES NEEDED ---"))
            for field, change in changes.items():
                self.stdout.write(
                    f"\n{field}:")
                self.stdout.write(
                    f"  Current:  {change['current']}")
                self.stdout.write(
                    f"  Expected: {change['expected']}")

        # Show message timeline
        self.stdout.write(f"\n--- MESSAGE TIMELINE (last 10) ---")
        for msg in messages.order_by("-fecha_mensaje")[:10]:
            dir_short = "IN" if msg.direccion == MensajeWhatsApp.ENTRANTE else "OUT"
            self.stdout.write(
                f"{msg.fecha_mensaje.strftime('%H:%M:%S')} | {dir_short} | {msg.sender_type:10s} | {msg.source:20s} | {msg.contenido[:60]}"
            )

        # Apply or dry-run
        if not changes:
            self.stdout.write(self.style.SUCCESS(f"\n✓ Conversation is consistent"))
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"\n[DRY-RUN] Changes NOT applied. Run without --dry-run to apply.")
            )
            return

        # Apply changes
        self.stdout.write(self.style.SUCCESS(f"\n--- APPLYING CHANGES ---"))
        if "ultima_actividad" in changes:
            conv.ultima_actividad = changes["ultima_actividad"]["expected"]
        if "resumen" in changes:
            conv.resumen = changes["resumen"]["expected"]
        if "bot_pausado" in changes:
            conv.bot_pausado = changes["bot_pausado"]["expected"]
        if "estado_atencion" in changes:
            conv.estado_atencion = changes["estado_atencion"]["expected"]

        conv.save()
        self.stdout.write(self.style.SUCCESS(f"✓ Conversation {conv_id} repaired"))
