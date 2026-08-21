from django.core.management.base import BaseCommand
from django.db.models import Q
from apps.whatsapp.models import MensajeWhatsApp, ConversacionWhatsApp


class Command(BaseCommand):
    help = "Repair sender_type and source attribution for all messages globally"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without applying",
        )
        parser.add_argument(
            "--conversation-id",
            type=int,
            default=None,
            help="Limit to specific conversation",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        conv_id = options["conversation_id"]

        # Query messages to analyze
        query = MensajeWhatsApp.objects.all()
        if conv_id:
            query = query.filter(conversacion_id=conv_id)

        # Categorize messages
        inbound_correct = 0
        outbound_bot = 0
        outbound_advisor_crm = 0
        outbound_advisor_web = 0
        outbound_incorrect = 0
        ambiguous = 0
        changes_needed = []

        self.stdout.write(self.style.SUCCESS(f"\n{'='*80}"))
        self.stdout.write(self.style.SUCCESS(f"GLOBAL MESSAGE ATTRIBUTION ANALYSIS"))
        self.stdout.write(self.style.SUCCESS(f"{'='*80}"))
        self.stdout.write(f"Total messages to analyze: {query.count()}")

        for msg in query.order_by("conversacion_id", "fecha_mensaje"):
            # INBOUND: should be customer + whatsapp_customer
            if msg.direccion == MensajeWhatsApp.ENTRANTE:
                if (msg.sender_type == MensajeWhatsApp.SENDER_CUSTOMER and
                    msg.source == MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER):
                    inbound_correct += 1
                else:
                    # Fix inbound
                    changes_needed.append({
                        "msg_id": msg.id,
                        "wamid": msg.meta_message_id,
                        "current": f"{msg.sender_type}/{msg.source}",
                        "expected": f"{MensajeWhatsApp.SENDER_CUSTOMER}/{MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER}",
                        "reason": "Inbound from customer",
                    })

            # OUTBOUND: more complex
            elif msg.direccion == MensajeWhatsApp.SALIENTE:
                # Detect if from bot or human
                is_bot_message = self._is_bot_message(msg)

                if is_bot_message:
                    if (msg.sender_type == MensajeWhatsApp.SENDER_BOT and
                        msg.source == MensajeWhatsApp.SOURCE_BOT):
                        outbound_bot += 1
                    else:
                        changes_needed.append({
                            "msg_id": msg.id,
                            "wamid": msg.meta_message_id,
                            "current": f"{msg.sender_type}/{msg.source}",
                            "expected": f"{MensajeWhatsApp.SENDER_BOT}/{MensajeWhatsApp.SOURCE_BOT}",
                            "reason": "Bot auto-response",
                        })
                else:
                    # Human sent this (advisor)
                    # Try to detect if from Web or CRM
                    is_web = self._is_web_message(msg)

                    if is_web:
                        if (msg.sender_type == MensajeWhatsApp.SENDER_ADVISOR and
                            msg.source == MensajeWhatsApp.SOURCE_WHATSAPP_BUSINESS_APP):
                            outbound_advisor_web += 1
                        else:
                            changes_needed.append({
                                "msg_id": msg.id,
                                "wamid": msg.meta_message_id,
                                "current": f"{msg.sender_type}/{msg.source}",
                                "expected": f"{MensajeWhatsApp.SENDER_ADVISOR}/{MensajeWhatsApp.SOURCE_WHATSAPP_BUSINESS_APP}",
                                "reason": "Advisor from WhatsApp Web",
                            })
                    else:
                        if (msg.sender_type == MensajeWhatsApp.SENDER_ADVISOR and
                            msg.source == MensajeWhatsApp.SOURCE_CRM):
                            outbound_advisor_crm += 1
                        else:
                            # Could be CRM or ambiguous
                            if msg.autor_id:
                                changes_needed.append({
                                    "msg_id": msg.id,
                                    "wamid": msg.meta_message_id,
                                    "current": f"{msg.sender_type}/{msg.source}",
                                    "expected": f"{MensajeWhatsApp.SENDER_ADVISOR}/{MensajeWhatsApp.SOURCE_CRM}",
                                    "reason": "Advisor from CRM (has autor_id)",
                                })
                            else:
                                ambiguous += 1

        # Report
        self.stdout.write(f"\n--- CLASSIFICATION ---")
        self.stdout.write(f"Inbound (correct): {inbound_correct}")
        self.stdout.write(f"Outbound Bot: {outbound_bot}")
        self.stdout.write(f"Outbound Advisor/CRM: {outbound_advisor_crm}")
        self.stdout.write(f"Outbound Advisor/Web: {outbound_advisor_web}")
        self.stdout.write(f"Ambiguous (no autor): {ambiguous}")
        self.stdout.write(f"\nChanges needed: {len(changes_needed)}")

        if changes_needed:
            self.stdout.write(f"\n--- SAMPLE CHANGES (first 10) ---")
            for change in changes_needed[:10]:
                self.stdout.write(
                    f"Message {change['msg_id']}: {change['current']} -> {change['expected']}"
                )
                self.stdout.write(f"  Reason: {change['reason']}")

        # Apply changes if not dry-run
        if not dry_run and changes_needed:
            self.stdout.write(f"\n--- APPLYING {len(changes_needed)} CHANGES ---")
            applied = 0
            for change in changes_needed:
                msg = MensajeWhatsApp.objects.get(pk=change["msg_id"])
                expected_parts = change["expected"].split("/")
                msg.sender_type = expected_parts[0]
                msg.source = expected_parts[1]
                msg.save(update_fields=["sender_type", "source"])
                applied += 1
                if applied % 100 == 0:
                    self.stdout.write(f"  Applied {applied}...")

            self.stdout.write(self.style.SUCCESS(f"✓ Applied {applied} changes"))
        elif dry_run:
            self.stdout.write(self.style.WARNING(f"\n[DRY-RUN] Changes NOT applied. Run without --dry-run to apply."))

    def _is_bot_message(self, msg):
        """Heuristic: detect if message looks like bot response"""
        bot_keywords = [
            "¡Hola!",
            "Gracias",
            "Para ayudarte",
            "asesor",
            "cotización",
            "TaxiCarga",
            "lima express",
        ]
        content_lower = msg.contenido.lower()

        # Bot markers
        if any(kw.lower() in content_lower for kw in bot_keywords):
            return True

        # Long message (bot typically sends longer responses)
        if len(msg.contenido) > 100:
            return True

        # Has pattern of question
        if msg.contenido.count("¿") > 0:
            return True

        return False

    def _is_web_message(self, msg):
        """Heuristic: detect if message came from WhatsApp Web/mobile vs CRM"""
        # If has autor_id, likely from CRM
        if msg.autor_id:
            return False

        # If short or conversational, likely from Web
        if len(msg.contenido) < 50 and msg.contenido.endswith("?"):
            return True

        # Default: ambiguous, assume Web if no autor
        return not msg.autor_id
