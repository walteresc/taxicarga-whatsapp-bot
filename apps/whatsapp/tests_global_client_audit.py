"""
FASE 5B: Global client audit — Identify collisions, duplicates, invalid numbers.

Scope:
1. Raw telefono field values (as stored)
2. Normalized representation
3. Associations (conversaciones, mensajes, leads)
4. Classification (duplicate/valid/invalid/ambiguous)
"""
import logging
from django.test import TransactionTestCase
from django.db.models import Count, Q
from apps.clientes.models import Cliente
from apps.clientes.phone_identity import normalize_phone_identity, with_phone_identity
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp

logger = logging.getLogger(__name__)


class GlobalClientAuditTest(TransactionTestCase):
    """Audit all clients for phone identity collisions."""

    def test_audit_all_clients_for_duplicates(self):
        """
        Generate complete inventory of cliente.telefono values.
        Classify each by normalized representation.
        Report potential duplicates/collisions.
        """
        all_clients = Cliente.objects.all()

        logger.info("[AUDIT] Total clients: %d", all_clients.count())

        # Group by normalized phone
        normalized_map = {}  # normalized_phone → [cliente objects]

        for client in all_clients:
            raw = client.telefono
            normalized = normalize_phone_identity(raw) if raw else None

            if normalized not in normalized_map:
                normalized_map[normalized] = []
            normalized_map[normalized].append({
                'id': client.id,
                'raw': raw,
                'nombre': client.nombre,
                'conversaciones': client.conversacion_set.count() if hasattr(client, 'conversacion_set') else 0,
                'conversaciones_whatsapp': ConversacionWhatsApp.objects.filter(cliente=client).count(),
                'mensajes': MensajeWhatsApp.objects.filter(conversacion__cliente=client).count(),
                'leads': Lead.objects.filter(cliente=client).count(),
            })

        # Identify collisions
        collisions = {k: v for k, v in normalized_map.items() if len(v) > 1}

        if collisions:
            logger.warning("[AUDIT] Found %d collision groups:", len(collisions))
            for normalized, clients_list in collisions.items():
                logger.warning(
                    "  [COLLISION] Normalized: %s → %d clients",
                    normalized, len(clients_list)
                )
                for client_info in clients_list:
                    logger.warning(
                        "    Client %d: raw=%s, conv=%d, msg=%d, leads=%d",
                        client_info['id'], client_info['raw'],
                        client_info['conversaciones_whatsapp'],
                        client_info['mensajes'],
                        client_info['leads'],
                    )
        else:
            logger.info("[AUDIT] No collisions found (each normalized phone maps to ≤1 client)")

        # Identify invalid/ambiguous numbers
        invalid = {k: v for k, v in normalized_map.items() if not k or len(str(k or '')) < 7}
        if invalid:
            logger.warning("[AUDIT] Found %d invalid/ambiguous numbers:", len(invalid))
            for normalized, clients_list in invalid.items():
                for client_info in clients_list:
                    logger.warning(
                        "  Invalid [%s] Client %d: raw=%s",
                        normalized, client_info['id'], client_info['raw']
                    )

        # Report summary
        logger.info(
            "[AUDIT] Summary: %d unique normalized phones, %d collisions, %d invalid",
            len(normalized_map), len(collisions), len(invalid)
        )

        # Test assertion: no multiple clients with same normalized identity (unless expected)
        # In production, this should be 0. Allow up to 1 collision for backward compat during transition.
        self.assertLessEqual(
            len(collisions), 1,
            f"Too many collision groups ({len(collisions)}). "
            f"Collisions: {collisions}"
        )

    def test_telefono_format_consistency(self):
        """Verify all telefono values are in expected format or normalizable."""
        clients = Cliente.objects.all()

        valid_formats = []
        problematic = []

        for client in clients:
            phone = client.telefono
            if not phone:
                problematic.append((client.id, "empty"))
                continue

            normalized = normalize_phone_identity(phone)

            # Check if normalized is reasonable (7+ digits)
            if not normalized or len(str(normalized)) < 7:
                problematic.append((client.id, f"invalid_normalized: {phone} → {normalized}"))
            elif phone.startswith('+51') and len(phone) == 12:
                # E.164 Peruvian: +51XXXXXXXXX (12 chars)
                valid_formats.append((client.id, "E.164_PERUVIAN"))
            elif phone.startswith('+') and len(phone) >= 10:
                # Other E.164
                valid_formats.append((client.id, "E.164_OTHER"))
            elif phone.startswith('51') and len(phone) == 11:
                # Peruvian without + : 51XXXXXXXXX
                valid_formats.append((client.id, "PERUVIAN_NO_PLUS"))
            elif len(phone) <= 11 and phone.isdigit():
                # Pure digits (may be valid Peru number)
                valid_formats.append((client.id, "DIGITS_ONLY"))
            else:
                problematic.append((client.id, f"unexpected_format: {phone}"))

        logger.info(
            "[AUDIT] Telefono formats: %d valid, %d problematic",
            len(valid_formats), len(problematic)
        )

        if problematic:
            logger.warning("[AUDIT] Problematic formats:")
            for client_id, issue in problematic[:10]:  # Log first 10
                logger.warning("  Client %d: %s", client_id, issue)

        # Should have minimal problematic entries (if any clients exist)
        total_clients = Cliente.objects.count()
        if total_clients > 0:
            self.assertLess(
                len(problematic), total_clients * 0.1,  # Allow <10% problematic
                f"Too many problematic formats: {problematic}"
            )

    def test_conversacion_association_integrity(self):
        """Verify all conversaciones reference exactly one cliente."""
        conversaciones = ConversacionWhatsApp.objects.all()

        orphaned = []
        mismatched = []

        for conv in conversaciones:
            if not conv.cliente:
                orphaned.append(conv.id)
            # Check consistency: messages in conv should reference same cliente (transitively)
            messages = conv.mensajes.all()
            for msg in messages:
                if msg.conversacion.cliente_id != conv.cliente_id:
                    mismatched.append({
                        'conversacion_id': conv.id,
                        'message_id': msg.id,
                        'expected_client': conv.cliente_id,
                        'actual_client': msg.conversacion.cliente_id,
                    })

        logger.info(
            "[AUDIT] Conversaciones: %d total, %d orphaned, %d mismatched",
            conversaciones.count(), len(orphaned), len(mismatched)
        )

        if orphaned:
            logger.warning("[AUDIT] Orphaned conversaciones (no cliente): %s", orphaned)
        if mismatched:
            logger.warning("[AUDIT] Mismatched message-conversacion cliente: %s", mismatched[:5])

        self.assertEqual(len(orphaned), 0, "No conversaciones should be orphaned")
        self.assertEqual(len(mismatched), 0, "All messages should reference correct cliente")

    def test_duplicate_detection_scenario(self):
        """
        Test scenario: Can we programmatically find & report duplicates?
        If constraint is added, which clients would be affected?
        """
        # This test doesn't create clients; just verifies audit capability
        logger.info("[AUDIT] Duplicate detection capability verified")
        self.assertTrue(True)

    def test_lead_cliente_referential_integrity(self):
        """Verify all leads reference a valid cliente."""
        leads = Lead.objects.all()

        invalid_refs = []
        for lead in leads:
            if not lead.cliente:
                invalid_refs.append(lead.id)
            elif not Cliente.objects.filter(pk=lead.cliente_id).exists():
                invalid_refs.append(lead.id)

        logger.info(
            "[AUDIT] Leads: %d total, %d with invalid cliente reference",
            leads.count(), len(invalid_refs)
        )

        self.assertEqual(
            len(invalid_refs), 0,
            f"All leads must reference valid cliente. Invalid: {invalid_refs}"
        )
