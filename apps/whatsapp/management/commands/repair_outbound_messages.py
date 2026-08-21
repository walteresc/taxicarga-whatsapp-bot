#!/usr/bin/env python
"""Repair outbound messages that weren't processed through process_whatsapp_message"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp


class Command(BaseCommand):
    help = "Repair outbound messages: update sender_type, update conversation state"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without modifying DB'
        )
        parser.add_argument(
            '--conversation-id',
            type=int,
            help='Repair specific conversation'
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        conv_id = options.get('conversation_id')

        # Find saliente messages with incorrect sender_type
        query = MensajeWhatsApp.objects.filter(
            direccion=MensajeWhatsApp.SALIENTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,  # WRONG
        ).order_by('fecha_mensaje')

        if conv_id:
            query = query.filter(conversacion_id=conv_id)

        count = query.count()
        self.stdout.write(f"Found {count} outbound messages with wrong sender_type")

        updated_count = 0
        updated_conversations = set()

        for msg in query:
            # Heuristic: detect if bot or advisor based on content
            is_likely_bot = self._is_bot_message(msg.contenido)

            if is_likely_bot:
                new_sender_type = MensajeWhatsApp.SENDER_BOT
                new_source = MensajeWhatsApp.SOURCE_BOT
            else:
                new_sender_type = MensajeWhatsApp.SENDER_ADVISOR
                new_source = MensajeWhatsApp.SOURCE_CRM

            if dry_run:
                self.stdout.write(
                    f"  Conv {msg.conversacion_id}: msg {msg.id} "
                    f"{msg.sender_type} -> {new_sender_type} | '{msg.contenido[:40]}'"
                )
            else:
                msg.sender_type = new_sender_type
                msg.source = new_source
                msg.save(update_fields=['sender_type', 'source'])
                updated_conversations.add(msg.conversacion_id)
                updated_count += 1

        self.stdout.write(f"Updated {updated_count} messages")

        if updated_conversations and not dry_run:
            self.stdout.write("\nRebuilding conversation state...")
            for conv_id in sorted(updated_conversations):
                self._rebuild_conversation(conv_id)
                self.stdout.write(f"  Rebuilt conversation {conv_id}")

        if dry_run:
            self.stdout.write("\n(dry-run mode - no changes made)")

    def _is_bot_message(self, content):
        """Heuristic to detect bot messages"""
        if not content:
            return False

        bot_keywords = [
            '¡hola!', 'hola!', 'gracias', 'para ayudarte',
            'asistente', 'bot', 'servicio', 'cotización',
            'cotizador', 'información', 'disponibilidad',
            'ok', 'correcto', 'entendido', 'listo'
        ]
        content_lower = content.lower()
        return any(keyword in content_lower for keyword in bot_keywords)

    def _rebuild_conversation(self, conv_id):
        """Rebuild conversation ultima_actividad and resumen"""
        conv = ConversacionWhatsApp.objects.get(pk=conv_id)
        last_msg = conv.mensajes.order_by('-fecha_mensaje').first()

        if last_msg:
            conv.ultima_actividad = last_msg.fecha_mensaje
            conv.resumen = last_msg.contenido[:100]
            conv.save(update_fields=['ultima_actividad', 'resumen'])
