from django.core.management.base import BaseCommand, CommandError
import json

from ...ai.agent import OpenAIConversationAgent
from ...adapters.crm import CRMV4Adapter
from ...repositories.state import DjangoBotStateRepository
from ...services.conversation_service import ConversationService
from ...services.persistent_conversation_service import PersistentConversationService
from ...services.quote_bridge import QuoteBridge
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp


class Command(BaseCommand):
    help = "Reproduce bug on conversation 66 with REAL historical context."

    def add_arguments(self, parser):
        parser.add_argument("--conv-id", type=int, default=66, help="Conversation ID to test (default: 66)")

    def handle(self, *args, **options):
        conv_id = options['conv_id']

        try:
            conversation = ConversacionWhatsApp.objects.get(pk=conv_id)
        except ConversacionWhatsApp.DoesNotExist:
            raise CommandError(f"Conversation {conv_id} not found")

        self.stdout.write(f"[OK] Found conversation {conv_id}")

        lead = conversation.lead
        conversation_key = f"whatsapp:{conversation.pk}"

        # Load services
        try:
            core_service = ConversationService(OpenAIConversationAgent())
        except Exception as exc:
            raise CommandError(f"Agent init failed: {exc}")

        repository = DjangoBotStateRepository()
        service = PersistentConversationService(
            core_service, repository, crm_adapter=CRMV4Adapter(), quote_bridge=QuoteBridge(),
        )

        # Load REAL historical context
        history, last_bot = self._get_recent_context(conversation)
        commercial_before = repository.get_commercial(conversation_key)

        self.stdout.write(f"\n--- CURRENT STATE BEFORE TEST ---")
        self.stdout.write(f"Commercial Status: {commercial_before.get('status')}")
        self.stdout.write(f"Commercial Mode: {commercial_before.get('mode')}")
        self.stdout.write(f"Price: {commercial_before.get('price')}")
        self.stdout.write(f"Last Bot Message: {(last_bot[:80] if last_bot else '(empty)')}")

        self.stdout.write(f"\n--- RECENT HISTORY ({len(history)} messages) ---")
        for i, msg in enumerate(history[-5:], start=len(history)-4):
            role = msg['role'].upper()
            content = msg['content'][:70]
            self.stdout.write(f"  {i}. [{role}] {content}")

        state_before = repository.load(conversation_key)
        self.stdout.write(f"\nState before: {state_before.to_dict()}")

        self.stdout.write(f"\n{'='*70}")
        self.stdout.write("SENDING MESSAGES WITH REAL HISTORY")
        self.stdout.write(f"{'='*70}\n")

        test_messages = [
            "Hola, necesito un presupuesto para una mudanza",
            "de surco a miraflores",
        ]

        results = []

        for turn_num, msg in enumerate(test_messages, 1):
            self.stdout.write(f"[TURN {turn_num}] CLIENT: {msg}\n")

            try:
                persistent_result = service.process_turn(
                    conversation_key=conversation_key,
                    customer_message=msg,
                    recent_conversation=history,
                    last_bot_message=last_bot,
                    conversation=conversation,
                    lead=lead,
                )
                turn = persistent_result.turn

                self.stdout.write(f"[TURN {turn_num}] BOT: {turn.reply}\n")

                # State after
                state_after = turn.state
                self.stdout.write(f"[STATE]\n{json.dumps(state_after.to_dict(), indent=2)}\n")

                # Required missing
                self.stdout.write(f"[REQUIRED_MISSING] {turn.required_missing}\n")

                commercial_after = repository.get_commercial(conversation_key)
                self.stdout.write(f"[COMMERCIAL]\n")
                self.stdout.write(f"  Status: {commercial_after.get('status')}\n")
                self.stdout.write(f"  Mode: {commercial_after.get('mode')}\n")
                self.stdout.write(f"  Price: {commercial_after.get('price')}\n")

                # Update history for next turn
                history.append({"role": "customer", "content": msg})
                history.append({"role": "assistant", "content": turn.reply or ""})
                last_bot = turn.reply or ""

                results.append({
                    "turn": turn_num,
                    "message": msg,
                    "reply": turn.reply,
                    "state": state_after.to_dict(),
                    "required_missing": turn.required_missing,
                    "commercial": commercial_after,
                })

            except Exception as exc:
                self.stderr.write(f"[ERROR TURN {turn_num}] {exc}")
                results.append({"turn": turn_num, "message": msg, "error": str(exc)})

        self.stdout.write("\n" + "="*70)
        self.stdout.write("SUMMARY")
        self.stdout.write("="*70)

        bug_detected = False
        for r in results:
            if "error" in r:
                self.stdout.write(f"Turn {r['turn']}: ERROR - {r['error']}")
            else:
                state = r['state']
                origin = state.get('origin_district')
                dest = state.get('destination_district')
                msg = r['message']

                # Check if turn 2 lost districts after extracting them
                if turn_num == 2 and msg == "de surco a miraflores":
                    if origin is None or dest is None:
                        self.stdout.write(f"Turn {r['turn']}: [FAIL] BUG! Distritos perdidos. origin={origin}, dest={dest}")
                        bug_detected = True
                    else:
                        self.stdout.write(f"Turn {r['turn']}: [OK] origin={origin}, dest={dest}")
                else:
                    self.stdout.write(f"Turn {r['turn']}: origin={origin}, dest={dest}")

        if bug_detected:
            self.stderr.write("\n[ALERT] BUG DETECTED: Districts lost after extraction with historical context")

    @staticmethod
    def _get_recent_context(conversation, exclude_message_id=None):
        """Load recent conversation history - same as MetaWebhookV4Service."""
        qs = conversation.mensajes
        if exclude_message_id:
            qs = qs.exclude(pk=exclude_message_id)
        messages = list(
            qs.filter(
                origen__in=[MensajeWhatsApp.ORIGEN_CLIENTE, MensajeWhatsApp.ORIGEN_BOT]
            ).order_by("-fecha_mensaje", "-id")[:10]
        )
        messages = messages[::-1]

        history = [
            {
                "role": "customer" if item.origen == MensajeWhatsApp.ORIGEN_CLIENTE else "assistant",
                "content": item.contenido,
            }
            for item in messages
        ]
        last_bot = next(
            (item.contenido for item in reversed(messages) if item.origen == MensajeWhatsApp.ORIGEN_BOT),
            ""
        )
        return history, last_bot
