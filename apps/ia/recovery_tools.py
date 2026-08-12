"""Recovery tools for interrupted message processing."""
import logging
from apps.leads.models import Lead
from apps.whatsapp.models import MensajeWhatsApp
from .data_extractor import extract_lead_data

logger = logging.getLogger(__name__)


def recover_lead_data_from_message(lead_id, message_id):
    """
    Safely recover and persist lead data from a specific message.

    Used when a conversation was interrupted before data extraction completed.
    The message is the authoritative evidence source.

    Args:
        lead_id: Lead to update
        message_id: Message containing the data (evidence source)

    Returns:
        dict with extracted data and what was persisted
    """
    try:
        lead = Lead.objects.get(pk=lead_id)
        message = MensajeWhatsApp.objects.get(pk=message_id)

        # Extract data from message
        extracted = extract_lead_data(message.contenido)

        # Only update fields that are currently empty (don't overwrite)
        updates = {}

        if extracted.get('distrito_origen') and not lead.distrito_origen:
            updates['distrito_origen'] = extracted['distrito_origen']

        if extracted.get('distrito_destino') and not lead.distrito_destino:
            updates['distrito_destino'] = extracted['distrito_destino']

        if extracted.get('lista_objetos') and not lead.lista_objetos:
            updates['lista_objetos'] = extracted['lista_objetos']

        # Persist updates with audit trail
        if updates:
            updates['motivo_perdida'] = (
                f"[Recovery] Updated from message {message_id}: {message.contenido[:100]}"
                if lead.motivo_perdida and lead.estado in [Lead.PERDIDO, Lead.CERRADO]
                else lead.motivo_perdida or ""
            )
            Lead.objects.filter(pk=lead_id).update(**updates)
            logger.info(f"Recovered data for Lead {lead_id} from msg {message_id}: {updates}")

        return {
            "lead_id": lead_id,
            "message_id": message_id,
            "extracted": extracted,
            "persisted": updates,
            "evidence_source": f"msg {message_id}: {message.contenido[:80]}"
        }

    except Exception as e:
        logger.error(f"Recovery failed for lead {lead_id}, msg {message_id}: {e}")
        return {
            "lead_id": lead_id,
            "message_id": message_id,
            "error": str(e)
        }
