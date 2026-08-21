"""
Repair duplicate active conversations.

Identifies and closes duplicate conversations, keeping the most recent as canonical.
No messages or data are deleted — only cerrada_en is set.

Usage:
  python manage.py repair_duplicate_conversations --dry-run
  python manage.py repair_duplicate_conversations --apply [--cliente-id=77]
"""

import json
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.whatsapp.models import ConversacionWhatsApp
from apps.whatsapp.services_conversation_resolver import audit_active_conversation_duplicates


class Command(BaseCommand):
    help = "Repair duplicate active conversations (keep newest, close older)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would change without applying',
        )
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Apply the changes',
        )
        parser.add_argument(
            '--cliente-id',
            type=int,
            help='Limit to specific cliente ID (e.g., 77 for Walter)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        apply_changes = options['apply']
        cliente_id = options.get('cliente_id')

        if not dry_run and not apply_changes:
            self.stdout.write(
                self.style.ERROR("Must specify --dry-run or --apply")
            )
            return

        # Audit duplicates
        self.stdout.write(self.style.SUCCESS("\n" + "=" * 80))
        self.stdout.write(self.style.SUCCESS("DUPLICATE CONVERSATIONS AUDIT"))
        self.stdout.write(self.style.SUCCESS("=" * 80))

        duplicates = audit_active_conversation_duplicates()

        if not duplicates:
            self.stdout.write(self.style.SUCCESS("[OK] No duplicates found"))
            return

        # Filter by cliente_id if requested
        if cliente_id:
            duplicates = [d for d in duplicates if d['cliente_id'] == cliente_id]

        if not duplicates:
            self.stdout.write(self.style.WARNING(f"No duplicates for cliente {cliente_id}"))
            return

        # Process each duplicate group
        changes = []
        for dup in duplicates:
            client_id = dup['cliente_id']
            channel_id = dup['channel_id']
            count = dup['count']
            conv_ids = dup['conv_ids']

            self.stdout.write(f"\nCliente {client_id}, Channel {channel_id}: {count} active conversations")

            # Get conversation details
            convs = ConversacionWhatsApp.objects.filter(
                id__in=conv_ids
            ).order_by('creada_en').values(
                'id', 'creada_en', 'ultima_actividad', 'resumen', 'estado_atencion'
            )

            convs_list = list(convs)
            canonical_conv = convs_list[-1]  # Most recent
            to_close = convs_list[:-1]  # All others

            self.stdout.write(f"  Canonical (keep open): Conv {canonical_conv['id']}")
            self.stdout.write(f"    Created: {canonical_conv['creada_en']}")
            self.stdout.write(f"    Last activity: {canonical_conv['ultima_actividad']}")
            self.stdout.write(f"    Status: {canonical_conv['estado_atencion']}")

            for conv in to_close:
                self.stdout.write(f"  To close: Conv {conv['id']}")
                self.stdout.write(f"    Created: {conv['creada_en']}")
                self.stdout.write(f"    Last activity: {conv['ultima_actividad']}")
                self.stdout.write(f"    Status: {conv['estado_atencion']}")

                changes.append({
                    'conv_id': conv['id'],
                    'client_id': client_id,
                    'channel_id': channel_id,
                    'created': str(conv['creada_en']),
                    'last_activity': str(conv['ultima_actividad']),
                })

        # Dry-run or apply
        if dry_run:
            self.stdout.write(self.style.WARNING(f"\n[DRY-RUN] Would close {len(changes)} conversations"))
            self.stdout.write(self.style.WARNING("Use --apply to execute"))
            return

        if apply_changes:
            self.stdout.write(f"\n" + "=" * 80)
            self.stdout.write(self.style.SUCCESS("APPLYING CHANGES"))
            self.stdout.write("=" * 80)

            closed_at = timezone.now()

            for change in changes:
                conv = ConversacionWhatsApp.objects.get(id=change['conv_id'])
                conv.cerrada_en = closed_at
                conv.save(update_fields=['cerrada_en'])

                self.stdout.write(self.style.SUCCESS(f"[OK] Closed Conv {conv.id}"))

            # Verify no more duplicates
            remaining = audit_active_conversation_duplicates()
            if cliente_id:
                remaining = [d for d in remaining if d['cliente_id'] == cliente_id]

            if remaining:
                self.stdout.write(self.style.ERROR(f"[WARNING] {len(remaining)} duplicate groups remain"))
            else:
                self.stdout.write(self.style.SUCCESS("[OK] No more duplicates"))

            # Backup file
            backup_file = f"repair_duplicates_backup_{closed_at.strftime('%Y%m%d_%H%M%S')}.json"
            with open(backup_file, 'w') as f:
                json.dump({
                    'closed_at': str(closed_at),
                    'changes': changes,
                    'total_closed': len(changes),
                }, f, indent=2)

            self.stdout.write(
                self.style.SUCCESS(f"\n[OK] Backup saved to: {backup_file}")
            )
            self.stdout.write(
                self.style.SUCCESS(f"[OK] Closed {len(changes)} conversations")
            )
