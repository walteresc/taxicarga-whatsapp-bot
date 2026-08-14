import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from ..models import BotConversationState


AUTO_QUOTE = "auto"
HUMAN_QUOTE = "human"


@dataclass(frozen=True)
class QuoteDecision:
    mode: str
    price: Decimal | None
    reason: str
    input_hash: str
    status: str
    request_id: int | None = None
    revision_id: int | None = None
    reused: bool = False

    def commercial_data(self) -> dict:
        return {
            "status": self.status,
            "input_hash": self.input_hash,
            "mode": self.mode,
            "price": self.price,
        }


def quote_input_hash(state) -> str:
    payload = {
        "origin_district": state.origin_district,
        "destination_district": state.destination_district,
        "origin_floor": state.origin_floor,
        "destination_floor": state.destination_floor,
        "origin_access": str(state.origin_access) if state.origin_access is not None else None,
        "destination_access": str(state.destination_access) if state.destination_access is not None else None,
        "items": list(state.items),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class QuoteBridge:
    def __init__(self, *, pricing_service=None, auto_quote_factory=None):
        if pricing_service is None:
            from apps.cotizador.services import cotizar_lead
            pricing_service = cotizar_lead
        if auto_quote_factory is None:
            from apps.cotizador.commercial import crear_cotizacion_automatica
            auto_quote_factory = crear_cotizacion_automatica
        self.pricing_service = pricing_service
        self.auto_quote_factory = auto_quote_factory

    @transaction.atomic
    def evaluate(self, *, state, lead, conversation, request_id=None) -> QuoteDecision:
        from apps.cotizador.models import RevisionCotizacion, SolicitudCotizacion

        input_hash = quote_input_hash(state)
        source_key = f"bot-v4:{conversation.pk}:{lead.pk}:{input_hash}"
        existing = RevisionCotizacion.objects.filter(source_key=source_key).first()
        if existing:
            return QuoteDecision(
                AUTO_QUOTE, existing.precio_final, "same commercial revision",
                input_hash, BotConversationState.STATUS_QUOTED,
                revision_id=existing.pk, reused=True,
            )
        try:
            technical = self.pricing_service(lead)
            price = Decimal(str(technical.precio_max)) if technical and technical.precio_max else None
            if price is None or price <= 0:
                raise ValueError("pricing_without_positive_price")
            message = f"Perfecto. Con los datos que me diste, el servicio tiene un costo de S/ {price:.2f}."
            _quote, revision, created = self.auto_quote_factory(
                conversation, technical, message, source_key=source_key,
            )
            return QuoteDecision(
                AUTO_QUOTE, revision.precio_final, "existing deterministic pricing",
                input_hash, BotConversationState.STATUS_QUOTED,
                revision_id=revision.pk, reused=not created,
            )
        except Exception as exc:
            request = SolicitudCotizacion.objects.filter(pk=request_id).first()
            if request is None:
                request, _ = SolicitudCotizacion.objects.get_or_create(
                    lead=lead,
                    estado__in=[SolicitudCotizacion.PENDIENTE, SolicitudCotizacion.EN_PROCESO],
                    defaults={"conversacion": conversation, "datos_faltantes": []},
                )
            if request.conversacion_id != conversation.pk or request.datos_faltantes:
                request.conversacion = conversation
                request.datos_faltantes = []
            request.motivo = f"Bot V4: por cotizar ({input_hash[:12]})"
            request.save(update_fields=["conversacion", "datos_faltantes", "motivo", "actualizada_en"])
            return QuoteDecision(
                HUMAN_QUOTE, None, exc.__class__.__name__, input_hash,
                BotConversationState.STATUS_PENDING_HUMAN,
                request_id=request.pk,
            )


def quote_reply(decision: QuoteDecision) -> str:
    if decision.mode == AUTO_QUOTE:
        return f"Perfecto. Con los datos que me diste, el servicio tiene un costo de S/ {decision.price:.2f}."
    return "Perfecto, ya tengo la información. Voy a pasar tu solicitud para que un asesor prepare la cotización."
