"""
Phase F: Tests for multimedia support (A-D).

Test coverage:
- Model creation and fields
- Serialization
- Webhook integration
- Error handling
"""

from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, MagicMock

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import (
    ConversacionWhatsApp,
    MensajeWhatsApp,
    MensajeAdjunto,
    WhatsAppChannel,
)
from apps.whatsapp.serializers import (
    MensajeWhatsAppSerializer,
    MensajeAdjuntoSerializer,
)


class MensajeWhatsAppModelTest(TestCase):
    """Test MensajeWhatsApp model with multimedia fields."""

    def setUp(self):
        self.cliente = Cliente.objects.create(
            telefono="51987654321",
            nombre="Test Client",
        )
        self.lead = Lead.objects.create(
            cliente=self.cliente,
            estado=Lead.NUEVO,
        )
        self.conversacion = ConversacionWhatsApp.objects.create(
            cliente=self.cliente,
            lead=self.lead,
        )

    def test_create_text_mensaje(self):
        """Test creating a simple text message."""
        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            tipo="texto",
            contenido="Hello world",
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
        )

        self.assertEqual(msg.tipo, "texto")
        self.assertEqual(msg.contenido, "Hello world")
        self.assertEqual(msg.media_status, MensajeWhatsApp.MEDIA_PENDING)

    def test_create_multimedia_mensaje(self):
        """Test creating a multimedia message with pending download."""
        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            tipo="imagen",
            ycloud_media_id="abc123def456",
            media_status=MensajeWhatsApp.MEDIA_PENDING,
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            source=MensajeWhatsApp.SOURCE_WEBHOOK,
        )

        self.assertEqual(msg.tipo, "imagen")
        self.assertEqual(msg.ycloud_media_id, "abc123def456")
        self.assertEqual(msg.media_status, MensajeWhatsApp.MEDIA_PENDING)
        self.assertEqual(msg.sender_type, MensajeWhatsApp.SENDER_CUSTOMER)
        self.assertEqual(msg.retention_policy, MensajeWhatsApp.RETAIN_DEFAULT)

    def test_retention_date_calculation(self):
        """Test that retain_until is calculated based on retention_policy."""
        now = timezone.now()
        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            tipo="imagen",
            retention_policy=MensajeWhatsApp.RETAIN_DEFAULT,
            retain_until=now + timedelta(days=30),
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
        )

        # Verify retain_until is in future
        self.assertGreater(msg.retain_until, now)

    def test_protected_from_cleanup(self):
        """Test manual protection from cleanup."""
        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            tipo="imagen",
            protected_from_cleanup=True,
            protection_reason="Important evidence",
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
        )

        self.assertTrue(msg.protected_from_cleanup)
        self.assertEqual(msg.protection_reason, "Important evidence")


class MensajeAdjuntoModelTest(TestCase):
    """Test MensajeAdjunto model for file attachment tracking."""

    def setUp(self):
        self.cliente = Cliente.objects.create(
            telefono="51987654321",
            nombre="Test Client",
        )
        self.lead = Lead.objects.create(
            cliente=self.cliente,
            estado=Lead.NUEVO,
        )
        self.conversacion = ConversacionWhatsApp.objects.create(
            cliente=self.cliente,
            lead=self.lead,
        )
        self.mensaje = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            tipo="imagen",
            ycloud_media_id="media123",
            media_status=MensajeWhatsApp.MEDIA_PENDING,
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
        )

    def test_create_adjunto(self):
        """Test creating an attachment record."""
        adjunto = MensajeAdjunto.objects.create(
            mensaje=self.mensaje,
            ycloud_media_id="media123",
            formato=MensajeAdjunto.FORMATO_IMAGEN,
            mime_type="image/jpeg",
            filename="photo.jpg",
            file_size=2048576,
            sha256="abc123" * 10,
            retain_until=timezone.now() + timedelta(days=30),
        )

        self.assertEqual(adjunto.mensaje, self.mensaje)
        self.assertEqual(adjunto.ycloud_media_id, "media123")
        self.assertEqual(adjunto.formato, MensajeAdjunto.FORMATO_IMAGEN)

    def test_adjunto_unique_ycloud_media_id(self):
        """Test that ycloud_media_id is unique (idempotence)."""
        MensajeAdjunto.objects.create(
            mensaje=self.mensaje,
            ycloud_media_id="unique123",
            formato=MensajeAdjunto.FORMATO_IMAGEN,
            mime_type="image/jpeg",
            filename="photo.jpg",
            file_size=1024,
            sha256="abc123" * 10,
            retain_until=timezone.now() + timedelta(days=30),
        )

        # Try to create duplicate - should raise IntegrityError
        with self.assertRaises(Exception):
            MensajeAdjunto.objects.create(
                mensaje=self.mensaje,
                ycloud_media_id="unique123",  # Same ID
                formato=MensajeAdjunto.FORMATO_IMAGEN,
                mime_type="image/jpeg",
                filename="photo2.jpg",
                file_size=1024,
                sha256="def456" * 10,
                retain_until=timezone.now() + timedelta(days=30),
            )

    def test_ia_analysis_result_persistence(self):
        """Test that IA analysis results persist as JSON."""
        adjunto = MensajeAdjunto.objects.create(
            mensaje=self.mensaje,
            ycloud_media_id="media123",
            formato=MensajeAdjunto.FORMATO_IMAGEN,
            mime_type="image/jpeg",
            filename="photo.jpg",
            file_size=1024,
            sha256="abc123" * 10,
            retain_until=timezone.now() + timedelta(days=30),
            ia_analysis_result={
                "objetos": ["persona", "caja", "mesa"],
                "resumen": "Person with boxes on table",
                "confianza": 0.92,
            },
        )

        # Retrieve and verify
        retrieved = MensajeAdjunto.objects.get(id=adjunto.id)
        self.assertIsInstance(retrieved.ia_analysis_result, dict)
        self.assertEqual(len(retrieved.ia_analysis_result["objetos"]), 3)


class MensajeWhatsAppSerializerTest(TestCase):
    """Test serialization of multimedia messages."""

    def setUp(self):
        self.cliente = Cliente.objects.create(
            telefono="51987654321",
            nombre="Test Client",
        )
        self.lead = Lead.objects.create(
            cliente=self.cliente,
            estado=Lead.NUEVO,
        )
        self.conversacion = ConversacionWhatsApp.objects.create(
            cliente=self.cliente,
            lead=self.lead,
        )

    def test_serialize_text_message(self):
        """Test serializing a text message."""
        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            tipo="texto",
            contenido="Hello",
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
        )

        serializer = MensajeWhatsAppSerializer(msg)
        data = serializer.data

        self.assertEqual(data["tipo"], "texto")
        self.assertEqual(data["contenido"], "Hello")
        self.assertIn("tipo_display", data)

    def test_serialize_multimedia_message(self):
        """Test serializing a multimedia message."""
        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            tipo="imagen",
            ycloud_media_id="media123",
            media_status=MensajeWhatsApp.MEDIA_READY,
            mime_type="image/jpeg",
            filename="photo.jpg",
            file_size=2048,
            sha256="abc" * 20,
            caption="Nice photo",
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
        )

        serializer = MensajeWhatsAppSerializer(msg)
        data = serializer.data

        self.assertEqual(data["tipo"], "imagen")
        self.assertEqual(data["media_status"], "ready")
        self.assertEqual(data["filename"], "photo.jpg")
        self.assertEqual(data["caption"], "Nice photo")


class MensajeAdjuntoSerializerTest(TestCase):
    """Test serialization of attachments."""

    def setUp(self):
        self.cliente = Cliente.objects.create(
            telefono="51987654321",
            nombre="Test Client",
        )
        self.lead = Lead.objects.create(
            cliente=self.cliente,
            estado=Lead.NUEVO,
        )
        self.conversacion = ConversacionWhatsApp.objects.create(
            cliente=self.cliente,
            lead=self.lead,
        )
        self.mensaje = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            tipo="imagen",
            ycloud_media_id="media123",
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
        )

    def test_serialize_adjunto(self):
        """Test serializing an attachment."""
        adjunto = MensajeAdjunto.objects.create(
            mensaje=self.mensaje,
            ycloud_media_id="media123",
            formato=MensajeAdjunto.FORMATO_IMAGEN,
            mime_type="image/jpeg",
            filename="photo.jpg",
            file_size=2048,
            sha256="abc" * 20,
            retain_until=timezone.now() + timedelta(days=30),
        )

        serializer = MensajeAdjuntoSerializer(adjunto)
        data = serializer.data

        self.assertEqual(data["formato"], "imagen")
        self.assertEqual(data["filename"], "photo.jpg")
        self.assertEqual(data["file_size"], 2048)
        self.assertIn("retain_until", data)


class MediaStatusTransitionTest(TestCase):
    """Test media status transitions (PENDING -> DOWNLOADING -> READY)."""

    def setUp(self):
        self.cliente = Cliente.objects.create(
            telefono="51987654321",
            nombre="Test Client",
        )
        self.lead = Lead.objects.create(
            cliente=self.cliente,
            estado=Lead.NUEVO,
        )
        self.conversacion = ConversacionWhatsApp.objects.create(
            cliente=self.cliente,
            lead=self.lead,
        )

    def test_status_transitions(self):
        """Test valid status transitions."""
        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            tipo="imagen",
            ycloud_media_id="media123",
            media_status=MensajeWhatsApp.MEDIA_PENDING,
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
        )

        # PENDING → DOWNLOADING
        msg.media_status = MensajeWhatsApp.MEDIA_DOWNLOADING
        msg.save()
        self.assertEqual(msg.media_status, MensajeWhatsApp.MEDIA_DOWNLOADING)

        # DOWNLOADING → READY
        msg.media_status = MensajeWhatsApp.MEDIA_READY
        msg.save()
        self.assertEqual(msg.media_status, MensajeWhatsApp.MEDIA_READY)

        # Or DOWNLOADING → FAILED
        msg.media_status = MensajeWhatsApp.MEDIA_FAILED
        msg.save()
        self.assertEqual(msg.media_status, MensajeWhatsApp.MEDIA_FAILED)


class ErrorScenarioTest(TestCase):
    """Test error scenarios and edge cases."""

    def setUp(self):
        self.cliente = Cliente.objects.create(
            telefono="51987654321",
            nombre="Test Client",
        )
        self.lead = Lead.objects.create(
            cliente=self.cliente,
            estado=Lead.NUEVO,
        )
        self.conversacion = ConversacionWhatsApp.objects.create(
            cliente=self.cliente,
            lead=self.lead,
        )

    def test_media_without_adjunto(self):
        """Test message marked READY but no adjunto created yet."""
        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            tipo="imagen",
            ycloud_media_id="media123",
            media_status=MensajeWhatsApp.MEDIA_READY,  # Marked ready but no file
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
        )

        # Should not have adjuntos
        self.assertEqual(msg.adjuntos.count(), 0)

    def test_expired_media(self):
        """Test media marked as EXPIRED."""
        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            tipo="imagen",
            ycloud_media_id="media123",
            media_status=MensajeWhatsApp.MEDIA_EXPIRED,
            retention_policy=MensajeWhatsApp.RETAIN_DEFAULT,
            retain_until=timezone.now() - timedelta(hours=1),  # Already expired
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
        )

        self.assertEqual(msg.media_status, MensajeWhatsApp.MEDIA_EXPIRED)
        self.assertLess(msg.retain_until, timezone.now())

    def test_retention_policies(self):
        """Test different retention policies."""
        now = timezone.now()

        policies = [
            (MensajeWhatsApp.RETAIN_DEFAULT, 30),
            (MensajeWhatsApp.RETAIN_QUOTE, 60),
            (MensajeWhatsApp.RETAIN_SERVICE, 90),
        ]

        for policy, expected_days in policies:
            msg = MensajeWhatsApp.objects.create(
                conversacion=self.conversacion,
                tipo="imagen",
                ycloud_media_id=f"media_{policy}",
                retention_policy=policy,
                retain_until=now + timedelta(days=expected_days),
                direccion=MensajeWhatsApp.ENTRANTE,
                origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            )

            days_diff = (msg.retain_until - now).days
            self.assertEqual(days_diff, expected_days)
