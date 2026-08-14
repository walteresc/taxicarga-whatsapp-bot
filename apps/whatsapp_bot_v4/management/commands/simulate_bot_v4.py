from django.core.management.base import BaseCommand, CommandError

from ...ai.agent import OpenAIConversationAgent
from ...adapters.crm import CRMV4Adapter
from ...repositories.state import DjangoBotStateRepository
from ...services.conversation_service import ConversationService
from ...services.persistent_conversation_service import PersistentConversationService
from ...services.quote_bridge import QuoteBridge


class Command(BaseCommand):
    help = "Simulador local del core conversacional WhatsApp Bot V4."

    def add_arguments(self, parser):
        parser.add_argument("--show-state", action="store_true")
        parser.add_argument("--conversation", default="demo001")
        parser.add_argument("--reset", action="store_true")

    def handle(self, *args, **options):
        try:
            core_service = ConversationService(OpenAIConversationAgent())
        except Exception as exc:
            raise CommandError(f"No se pudo iniciar agente V4: {exc}") from exc
        repository = DjangoBotStateRepository()
        conversation_key = f"simulator:{options['conversation']}"
        if options["reset"]:
            repository.reset(conversation_key)
            self.stdout.write(f"Estado reiniciado: {conversation_key}")
        from apps.clientes.models import Cliente
        from apps.leads.models import Lead
        from apps.whatsapp.models import ConversacionWhatsApp

        customer, _ = Cliente.objects.get_or_create(telefono=f"sim-v4-{options['conversation']}"[:30])
        conversation = ConversacionWhatsApp.objects.filter(
            cliente=customer, estado_atencion__in=["bot", "asesor"],
        ).order_by("-id").first()
        if conversation is None:
            lead = Lead.objects.create(cliente=customer)
            conversation = ConversacionWhatsApp.objects.create(cliente=customer, lead=lead)
        else:
            lead = conversation.lead
        service = PersistentConversationService(
            core_service, repository, crm_adapter=CRMV4Adapter(), quote_bridge=QuoteBridge(),
        )
        state = repository.load(conversation_key)
        history = []
        last_bot_message = ""
        self.stdout.write("Bot V4 local. Escribe /exit para salir; /state para ver estado.")
        while True:
            try:
                message = input("CLIENT: ").strip()
            except (EOFError, KeyboardInterrupt):
                self.stdout.write("")
                break
            if message.lower() in {"/exit", "/quit"}:
                break
            if message.lower() == "/state":
                self.stdout.write(str(state.to_dict()))
                continue
            if not message:
                continue
            try:
                persistent_result = service.process_turn(
                    conversation_key=conversation_key,
                    customer_message=message,
                    recent_conversation=history,
                    last_bot_message=last_bot_message,
                    conversation=conversation,
                    lead=lead,
                )
                result = persistent_result.turn
            except Exception as exc:
                self.stderr.write(f"ERROR: {exc}")
                continue
            state = result.state
            last_bot_message = result.reply or ""
            history.extend([
                {"role": "customer", "content": message},
                {"role": "assistant", "content": last_bot_message},
            ])
            self.stdout.write(f"BOT: {last_bot_message}")
            if options["show_state"] or result.ready_to_quote:
                commercial = repository.get_commercial(conversation_key)
                self.stdout.write(f"STATE: {state.to_dict()}")
                self.stdout.write(f"STATUS: {commercial['status']}")
                self.stdout.write(f"REQUIRED_MISSING: {result.required_missing}")
                self.stdout.write(f"QUOTE_DECISION: {commercial['mode'] or 'none'}")
                if commercial.get("price") is not None:
                    self.stdout.write(f"QUOTE: S/ {commercial['price']}")
