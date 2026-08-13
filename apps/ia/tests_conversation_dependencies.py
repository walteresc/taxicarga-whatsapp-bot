"""Test conversation dependency logic for eligible question targets."""
from django.test import TestCase

from apps.clientes.models import Cliente
from apps.leads.models import Lead, LeadUbicacion
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp

from .conversation_policy import eligible_question_targets


class EligibleQuestionTargetsTest(TestCase):
    """Test filtering of eligible question targets based on dependencies."""

    def setUp(self):
        self.client = Cliente.objects.create(telefono="51999999999")
        self.channel = WhatsAppChannel.objects.create(
            nombre="TEST", phone_number_id="123"
        )
        self.lead = Lead.objects.create(
            cliente=self.client, whatsapp_channel=self.channel
        )

    def test_piso_unknown_excludes_ascensor(self):
        """If floor is unknown, ascensor/escaleras should not be eligible."""
        # Create route but no floor set
        LeadUbicacion.objects.create(
            lead=self.lead, orden=0, tipo="origen", distrito="Surco", piso=None
        )
        missing = ("piso_origen", "ascensor_origen")

        eligible = eligible_question_targets(missing, self.lead)

        # Should only include piso, not ascensor (depends on piso)
        self.assertIn("piso_origen", eligible)
        self.assertNotIn("ascensor_origen", eligible)

    def test_piso_1_excludes_ascensor(self):
        """If floor is 1, ascensor should not be eligible."""
        # Floor is 1
        LeadUbicacion.objects.create(
            lead=self.lead, orden=0, tipo="origen", distrito="Surco", piso=1
        )

        missing = ("ascensor_origen",)
        eligible = eligible_question_targets(missing, self.lead)

        # Floor 1 doesn't need ascensor question
        self.assertEqual(len(eligible), 0)

    def test_piso_greater_than_1_includes_ascensor(self):
        """If floor > 1, ascensor is eligible."""
        # Floor is 3
        LeadUbicacion.objects.create(
            lead=self.lead, orden=0, tipo="origen", distrito="Surco", piso=3
        )

        missing = ("ascensor_origen",)
        eligible = eligible_question_targets(missing, self.lead)

        # Floor > 1, so ascensor is eligible
        self.assertIn("ascensor_origen", eligible)

    def test_route_unknown_excludes_pisos(self):
        """If route is unknown, floor/ascensor should not be eligible."""
        # No locations set
        missing = ("distrito_origen", "piso_origen", "ascensor_origen")

        eligible = eligible_question_targets(missing, self.lead)

        # Can ask for district, but not floor/ascensor (require route)
        self.assertIn("distrito_origen", eligible)
        # Floor/ascensor are location-specific, so excluded
        self.assertNotIn("piso_origen", eligible)
        self.assertNotIn("ascensor_origen", eligible)

    def test_both_floors_greater_than_1(self):
        """Both locations > 1 should allow ascensor for both."""
        LeadUbicacion.objects.create(
            lead=self.lead, orden=0, tipo="origen", distrito="Surco", piso=3
        )
        LeadUbicacion.objects.create(
            lead=self.lead, orden=1, tipo="destino", distrito="Miraflores", piso=2
        )

        missing = ("ascensor_origen", "ascensor_destino")
        eligible = eligible_question_targets(missing, self.lead)

        self.assertIn("ascensor_origen", eligible)
        self.assertIn("ascensor_destino", eligible)

    def test_one_floor_1_excludes_its_ascensor(self):
        """Floor 1 destination excludes ascensor for that location."""
        LeadUbicacion.objects.create(
            lead=self.lead, orden=0, tipo="origen", distrito="Surco", piso=3
        )
        LeadUbicacion.objects.create(
            lead=self.lead, orden=1, tipo="destino", distrito="Miraflores", piso=1
        )

        missing = ("ascensor_origen", "ascensor_destino")
        eligible = eligible_question_targets(missing, self.lead)

        self.assertIn("ascensor_origen", eligible)
        self.assertNotIn("ascensor_destino", eligible)
