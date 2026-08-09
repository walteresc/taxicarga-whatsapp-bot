import hashlib

from django.db import IntegrityError, connection, transaction

from apps.clientes.models import Cliente
from apps.clientes.phone_identity import normalize_phone_identity, phone_to_e164, with_phone_identity
from apps.leads.models import Lead

from .domain import obtener_o_crear_conversacion
from .models import ConversacionWhatsApp


class AmbiguousWhatsAppIdentity(Exception):
    pass


def _lock_phone_identity(channel_id, identity):
    if connection.vendor != "postgresql":
        return
    scope = f"{channel_id}:{identity}"
    key = int.from_bytes(hashlib.sha256(scope.encode("utf-8")).digest()[:8], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def _matching_clients(identity):
    return with_phone_identity(Cliente.objects.select_for_update()).filter(_phone_identity=identity)


def _preferred_client(clients, channel):
    if clients.count() > 1:
        raise AmbiguousWhatsAppIdentity("Multiple clients share the same canonical phone identity.")
    if not channel:
        return clients.order_by("id").first()
    client_ids = list(clients.values_list("id", flat=True))
    conversations = list(
        ConversacionWhatsApp.objects.select_for_update(of=("self",))
        .filter(cliente_id__in=client_ids, channel=channel)
        .exclude(estado_atencion=ConversacionWhatsApp.ATENCION_CERRADA)
        .select_related("integration_control")
        .order_by("-ultima_actividad", "id")
    )
    if conversations:
        conversations.sort(
            key=lambda item: (
                not (
                    item.estado_atencion == ConversacionWhatsApp.ATENCION_ASESOR
                    or item.bot_pausado
                    or (
                        hasattr(item, "integration_control")
                        and item.integration_control.owner_state == "ASESOR_ACTIVO"
                    )
                ),
                -item.id,
            )
        )
        return next(client for client in clients if client.id == conversations[0].cliente_id)
    return clients.order_by("id").first()


@transaction.atomic
def resolve_whatsapp_identity(phone, channel, *, create=True):
    """Resolve one client/lead/conversation under a canonical phone lock."""
    identity = normalize_phone_identity(phone)
    if not identity:
        raise ValueError("WhatsApp phone identity is empty.")
    _lock_phone_identity(getattr(channel, "id", "unknown"), identity)
    clients = _matching_clients(identity)
    client = _preferred_client(clients, channel)
    if client is None:
        if not create:
            return None, None, None
        try:
            with transaction.atomic():
                client = Cliente.objects.create(telefono=phone_to_e164(identity))
        except IntegrityError:
            client = _matching_clients(identity).get()

    conversation = (
        ConversacionWhatsApp.objects.select_for_update()
        .filter(cliente=client, channel=channel)
        .exclude(estado_atencion=ConversacionWhatsApp.ATENCION_CERRADA)
        .order_by("-ultima_actividad", "id")
        .first()
    )
    if conversation:
        return client, conversation.lead, conversation

    lead = (
        Lead.objects.select_for_update()
        .filter(cliente=client, whatsapp_channel=channel)
        .exclude(estado__in=[Lead.CERRADO, Lead.PERDIDO])
        .order_by("-fecha_creacion")
        .first()
    )
    if lead is None and create:
        lead = Lead.objects.create(cliente=client, estado=Lead.NUEVO, whatsapp_channel=channel)
    if lead and channel and not lead.whatsapp_channel_id:
        lead.whatsapp_channel = channel
        lead.save(update_fields=["whatsapp_channel"])
    conversation = obtener_o_crear_conversacion(lead) if lead else None
    return client, lead, conversation
