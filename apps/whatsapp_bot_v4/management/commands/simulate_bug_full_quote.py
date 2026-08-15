from django.core.management.base import BaseCommand, CommandError
import json
import logging

from ...ai.agent import OpenAIConversationAgent
from ...adapters.crm import CRMV4Adapter
from ...repositories.state import DjangoBotStateRepository
from ...services.conversation_service import ConversationService
from ...services.persistent_conversation_service import PersistentConversationService
from ...services.quote_bridge import QuoteBridge
from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reproduce bug: complete quote then NEW_QUOTE action with same districts."

    def add_arguments(self, parser):
        parser.add_argument("--conv-id", type=int, default=999, help="Test conversation ID")

    def handle(self, *args, **options):
        conv_id = options['conv_id']
        conversation_key = f"simulator:bug_test_{conv_id}"

        # Setup
        try:
            core_service = ConversationService(OpenAIConversationAgent())
        except Exception as exc:
            raise CommandError(f"Agent init failed: {exc}")

        repository = DjangoBotStateRepository()
        repository.reset(conversation_key)

        customer, _ = Cliente.objects.get_or_create(telefono=f"sim-bug-{conv_id}"[:30])
        lead = Lead.objects.create(cliente=customer)
        conversation = ConversacionWhatsApp.objects.create(cliente=customer, lead=lead)

        service = PersistentConversationService(
            core_service, repository, crm_adapter=CRMV4Adapter(), quote_bridge=QuoteBridge(),
        )

        self.stdout.write(f"\n{'='*70}")
        self.stdout.write("PHASE 1: COMPLETE A FULL QUOTE")
        self.stdout.write(f"{'='*70}\n")

        # Sequence to complete a quote
        full_quote_sequence = [
            ("Necesito un presupuesto para una mudanza", "greeting"),
            ("de surco a miraflores", "districts"),
            ("salgo del tercero y llego al segundo", "floors"),
            ("sin ascensor en origen, con ascensor en destino", "access"),
            ("una cama, un escritorio y varios libros", "items"),
        ]

        history = []
        last_bot = ""

        for msg, label in full_quote_sequence:
            self.stdout.write(f"[PHASE1-{label}] CLIENT: {msg}")

            try:
                result = service.process_turn(
                    conversation_key=conversation_key,
                    customer_message=msg,
                    recent_conversation=history,
                    last_bot_message=last_bot,
                    conversation=conversation,
                    lead=lead,
                )
                turn = result.turn
                self.stdout.write(f"[PHASE1-{label}] BOT: {turn.reply}\n")

                history.append({"role": "customer", "content": msg})
                history.append({"role": "assistant", "content": turn.reply or ""})
                last_bot = turn.reply or ""

            except Exception as e:
                self.stderr.write(f"[ERROR {label}] {e}")
                return

        # Check state after complete quote
        state_final = repository.load(conversation_key)
        commercial_final = repository.get_commercial(conversation_key)

        self.stdout.write(f"\n--- PHASE 1 COMPLETE STATE ---")
        self.stdout.write(f"State: {state_final.to_dict()}")
        self.stdout.write(f"Commercial: {commercial_final}")
        self.stdout.write(f"Ready to quote: {turn.ready_to_quote}")

        self.stdout.write(f"\n{'='*70}")
        self.stdout.write("PHASE 2: NEW_QUOTE ACTION WITH SAME DISTRICTS")
        self.stdout.write(f"{'='*70}\n")

        # Now simulate NEW_QUOTE: client says they need a new quote
        new_quote_sequence = [
            ("Hola, necesito un presupuesto para una mudanza", "new_request"),
            ("de surco a miraflores", "districts_again"),
        ]

        results = []

        for msg, label in new_quote_sequence:
            self.stdout.write(f"[PHASE2-{label}] CLIENT: {msg}")

            try:
                result = service.process_turn(
                    conversation_key=conversation_key,
                    customer_message=msg,
                    recent_conversation=history,
                    last_bot_message=last_bot,
                    conversation=conversation,
                    lead=lead,
                )
                turn = result.turn
                self.stdout.write(f"[PHASE2-{label}] BOT: {turn.reply}\n")

                state_after = turn.state
                commercial_after = repository.get_commercial(conversation_key)

                self.stdout.write(f"[STATE] {state_after.to_dict()}\n")
                self.stdout.write(f"[COMMERCIAL] {commercial_after}\n")
                self.stdout.write(f"[ACTION] {turn.conversation_action}\n")

                history.append({"role": "customer", "content": msg})
                history.append({"role": "assistant", "content": turn.reply or ""})
                last_bot = turn.reply or ""

                # SNAPSHOT: Capture DB state IMMEDIATELY after this turno
                db_state = repository.load(conversation_key)
                db_snapshot = db_state.to_dict() if db_state else None

                results.append({
                    "label": label,
                    "message": msg,
                    "bot_reply": turn.reply,
                    "state": state_after.to_dict(),
                    "action": str(turn.conversation_action),
                    "db_snapshot": db_snapshot,
                })

            except Exception as e:
                self.stderr.write(f"[ERROR {label}] {e}")
                results.append({"label": label, "error": str(e)})

        self.stdout.write(f"\n{'='*70}")
        self.stdout.write("DIAGNOSIS SUMMARY")
        self.stdout.write(f"{'='*70}\n")

        # Verify NEW_QUOTE behavior by capturing DB snapshots IMMEDIATELY after each turno
        test_failed = False
        if len(results) >= 2:
            # SNAPSHOT 1: Captured DURING turno 1 (new_request)
            snapshot_after_new_quote = results[0].get("db_snapshot")

            self.stdout.write(f"\n[VERIFY] After NEW_QUOTE (captured immediately), state from DB:")
            if snapshot_after_new_quote:
                self.stdout.write(f"  origin_district: {snapshot_after_new_quote.get('origin_district')}")
                self.stdout.write(f"  destination_district: {snapshot_after_new_quote.get('destination_district')}")
                self.stdout.write(f"  origin_floor: {snapshot_after_new_quote.get('origin_floor')}")
                self.stdout.write(f"  destination_floor: {snapshot_after_new_quote.get('destination_floor')}")
                self.stdout.write(f"  origin_access: {snapshot_after_new_quote.get('origin_access')}")
                self.stdout.write(f"  destination_access: {snapshot_after_new_quote.get('destination_access')}")
                self.stdout.write(f"  items: {snapshot_after_new_quote.get('items')}")
                self.stdout.write(f"  request_boundary_at: {snapshot_after_new_quote.get('request_boundary_at')}")

                # After NEW_QUOTE, state must be COMPLETELY EMPTY
                if all(
                    snapshot_after_new_quote.get(k) in (None, [], "")
                    for k in ["origin_district", "destination_district", "origin_floor",
                              "destination_floor", "origin_access", "destination_access", "items"]
                ):
                    self.stdout.write("[OK] NEW_QUOTE properly resets state to empty")
                else:
                    self.stderr.write(f"[BUG] NEW_QUOTE did not reset! state={snapshot_after_new_quote}")
                    test_failed = True

            # SNAPSHOT 2: Captured DURING turno 2 (districts_again)
            snapshot_after_districts = results[1].get("db_snapshot")

            self.stdout.write(f"\n[VERIFY] After districts_again (captured immediately), state from DB:")
            if snapshot_after_districts:
                self.stdout.write(f"  origin_district: {snapshot_after_districts.get('origin_district')}")
                self.stdout.write(f"  destination_district: {snapshot_after_districts.get('destination_district')}")
                self.stdout.write(f"  origin_floor: {snapshot_after_districts.get('origin_floor')}")
                self.stdout.write(f"  destination_floor: {snapshot_after_districts.get('destination_floor')}")
                self.stdout.write(f"  origin_access: {snapshot_after_districts.get('origin_access')}")
                self.stdout.write(f"  destination_access: {snapshot_after_districts.get('destination_access')}")
                self.stdout.write(f"  items: {snapshot_after_districts.get('items')}")

                # After districts, should have ONLY distritos, no floors/access/items
                if (snapshot_after_districts.get("origin_district") == "Surco" and
                    snapshot_after_districts.get("destination_district") == "Miraflores" and
                    all(snapshot_after_districts.get(k) in (None, [], "") for k in
                        ["origin_floor", "destination_floor", "origin_access", "destination_access", "items"])):
                    self.stdout.write("[OK] Districts extracted, floors/access/items remain empty")
                else:
                    self.stderr.write(f"[BUG] Wrong state after districts! state={snapshot_after_districts}")
                    test_failed = True

        if test_failed:
            self.stderr.write("\n[FAIL] Test failed - exiting with code 1")
            raise SystemExit(1)

        self.stdout.write(f"\n[PASS] All assertions passed!")
        self.stdout.write(f"\nFull results:\n{json.dumps(results, indent=2, default=str)}")
