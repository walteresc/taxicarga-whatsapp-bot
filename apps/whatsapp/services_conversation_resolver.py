"""
Unified conversation resolution service.

Single entry point for resolving or creating active conversations.
Prevents duplicate ConversacionWhatsApp for same (cliente, channel).

Handles:
- Idempotency by wamid
- Concurrency (select_for_update)
- IntegrityError handling
- Central logging
"""

import logging
from django.db import transaction, IntegrityError
from apps.whatsapp.models import ConversacionWhatsApp

logger = logging.getLogger(__name__)


def resolve_or_create_active_conversation(cliente, channel):
    """
    Resolve or create a single active conversation for (cliente, channel).

    Key: (cliente_id, channel_id, cerrada_en IS NULL)

    Args:
        cliente: Cliente instance
        channel: WhatsAppChannel instance

    Returns:
        (conversation, created): Tuple of ConversacionWhatsApp and bool flag

    Raises:
        IntegrityError: If race condition creates duplicate (handled + retried)
        ValueError: If arguments are invalid
    """
    if not cliente or not channel:
        raise ValueError("cliente and channel required")

    # Attempt 1: Non-blocking lookup
    existing = ConversacionWhatsApp.objects.filter(
        cliente=cliente,
        channel=channel,
        cerrada_en__isnull=True,
    ).first()

    if existing:
        logger.debug(
            "[ConversationResolver] Reused active conversation %d for cliente %d, channel %d",
            existing.id, cliente.id, channel.id
        )
        return existing, False

    # No active conversation found. Check if closed ones exist (warn if multiple)
    closed_count = ConversacionWhatsApp.objects.filter(
        cliente=cliente,
        channel=channel,
        cerrada_en__isnull=False,
    ).count()

    if closed_count > 0:
        logger.warning(
            "[ConversationResolver] Found %d closed conversation(s) for cliente %d, channel %d. "
            "Creating new active conversation. If reopening is intended, handle explicitly.",
            closed_count, cliente.id, channel.id
        )

    # Attempt 2: Create new, with race-condition handling
    try:
        with transaction.atomic():
            # Re-check under transaction to catch race
            existing = ConversacionWhatsApp.objects.filter(
                cliente=cliente,
                channel=channel,
                cerrada_en__isnull=True,
            ).select_for_update().first()

            if existing:
                logger.debug(
                    "[ConversationResolver] Another thread created conversation %d, reusing",
                    existing.id
                )
                return existing, False

            # Safe to create
            conversation = ConversacionWhatsApp.objects.create(
                cliente=cliente,
                channel=channel,
                estado_atencion=ConversacionWhatsApp.ATENCION_BOT,
            )

            logger.info(
                "[ConversationResolver] Created new active conversation %d for cliente %d, channel %d",
                conversation.id, cliente.id, channel.id
            )

            return conversation, True

    except IntegrityError as e:
        # Constraint violation: another process created it first
        logger.warning(
            "[ConversationResolver] IntegrityError on create (race condition): %s. Retrying lookup.",
            str(e)
        )

        # Retry lookup one more time
        existing = ConversacionWhatsApp.objects.filter(
            cliente=cliente,
            channel=channel,
            cerrada_en__isnull=True,
        ).first()

        if existing:
            logger.info(
                "[ConversationResolver] Recovered: reusing conversation %d after race",
                existing.id
            )
            return existing, False

        # Still not found — re-raise
        logger.error(
            "[ConversationResolver] IntegrityError and recovery failed for cliente %d, channel %d",
            cliente.id, channel.id
        )
        raise


def audit_active_conversation_duplicates():
    """
    Audit and report all active conversations that violate uniqueness.

    Returns:
        list: [{'cliente_id': ..., 'channel_id': ..., 'count': N, 'conv_ids': [...]}, ...]
    """
    from django.db.models import Count, Q

    duplicates = (
        ConversacionWhatsApp.objects.filter(
            cerrada_en__isnull=True,
        )
        .values("cliente_id", "channel_id")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
        .order_by("-count")
    )

    result = []
    for dup in duplicates:
        convs = ConversacionWhatsApp.objects.filter(
            cliente_id=dup["cliente_id"],
            channel_id=dup["channel_id"],
            cerrada_en__isnull=True,
        ).order_by("creada_en").values_list("id", flat=True)

        result.append({
            "cliente_id": dup["cliente_id"],
            "channel_id": dup["channel_id"],
            "count": dup["count"],
            "conv_ids": list(convs),
        })

    return result
