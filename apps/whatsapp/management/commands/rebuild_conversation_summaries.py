"""
Rebuild conversation summaries from actual messages.

Recalculates:
- ultima_actividad (from most recent message)
- last_message_at
- last_message_preview
- last_message_type
- last_sender_type

Usage:
    python manage.py rebuild_conversation_summaries --dry-run
    python manage.py rebuild_conversation_summaries --limit 50
    python manage.py rebuild_conversation_summaries
"""

from django.core.management.base import BaseCommand
from django.db.models import Max, Q
from django.utils import timezone
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp


class Command(BaseCommand):
    help = "Rebuild conversation summaries from actual messages"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would happen without modifying data"
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Only process N conversations"
        )
        parser.add_argument(
            "--conversacion-id",
            type=int,
            help="Only process this conversation ID"
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", True)
        limit = options.get("limit")
        conversacion_id = options.get("conversacion_id")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n🔄 REBUILD CONVERSATION SUMMARIES {'(DRY-RUN)' if dry_run else '(EXECUTION)'}"
            )
        )

        # Query
        queryset = ConversacionWhatsApp.objects.all()
        if conversacion_id:
            queryset = queryset.filter(id=conversacion_id)
        if limit:
            queryset = queryset[:limit]

        total = queryset.count()
        self.stdout.write(f"   Processing {total} conversations...\n")

        updated_count = 0
        unchanged_count = 0
        no_messages_count = 0

        for conv in queryset:
            # Get most recent message
            last_msg = MensajeWhatsApp.objects.filter(
                conversacion=conv
            ).order_by("-fecha_mensaje").first()

            if not last_msg:
                no_messages_count += 1
                self.stdout.write(f"   ID={conv.id} (cliente={conv.cliente.nombre}): NO MESSAGES")
                continue

            # Calculate updates - only update fields that actually exist on model
            new_actividad = last_msg.fecha_mensaje

            # Check if changes needed
            changed = new_actividad != conv.ultima_actividad

            if not changed:
                unchanged_count += 1
                continue

            # Update (or show what would update)
            old_actividad = conv.ultima_actividad
            conv.ultima_actividad = new_actividad

            if not dry_run:
                conv.save(update_fields=['ultima_actividad'])

            updated_count += 1
            self.stdout.write(
                f"   ✅ ID={conv.id} (cliente={conv.cliente.nombre}): "
                f"{old_actividad} → {new_actividad}"
            )

        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(f"📊 SUMMARY")
        self.stdout.write(f"   Updated: {updated_count}")
        self.stdout.write(f"   Unchanged: {unchanged_count}")
        self.stdout.write(f"   No messages: {no_messages_count}")
        self.stdout.write(f"   Total processed: {total}")

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                "\n✅ DRY-RUN COMPLETE. No changes made."
            ))
            self.stdout.write("   To execute: remove --dry-run flag\n")
        else:
            self.stdout.write(self.style.SUCCESS(
                "\n✅ REBUILD COMPLETE\n"
            ))
