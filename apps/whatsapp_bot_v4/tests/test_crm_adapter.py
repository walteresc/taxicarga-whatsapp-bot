from django.test import TestCase

from apps.clientes.models import Cliente
from apps.cotizador.models import Cotizacion, SolicitudCotizacion
from apps.leads.models import Lead, LeadUbicacion

from ..adapters.crm import CRMV4Adapter
from ..domain.state import Access, BotState


class CRMAdapterTests(TestCase):
    def setUp(self):
        self.client_record = Cliente.objects.create(telefono="51999000001")
        self.lead = Lead.objects.create(cliente=self.client_record)
        self.adapter = CRMV4Adapter()
        self.complete = BotState("Surco", "Miraflores", 1, 2, Access.NOT_APPLICABLE, Access.STAIRS, ["1 cama", "10 cajas"])

    def test_state_maps_to_crm(self):
        result = self.adapter.sync(self.complete, self.lead)
        self.assertTrue(result.ready_for_quote)

    def test_origin_mapping(self):
        self.adapter.sync(self.complete, self.lead)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.distrito_origen, "Surco")
        self.assertEqual(LeadUbicacion.objects.get(lead=self.lead, tipo="origen").distrito, "Surco")

    def test_destination_mapping(self):
        self.adapter.sync(self.complete, self.lead)
        self.assertEqual(LeadUbicacion.objects.get(lead=self.lead, tipo="destino").distrito, "Miraflores")

    def test_floors_mapping(self):
        self.adapter.sync(self.complete, self.lead)
        self.lead.refresh_from_db()
        self.assertEqual((self.lead.piso_origen, self.lead.piso_destino), (1, 2))

    def test_accesses_mapping(self):
        self.adapter.sync(self.complete, self.lead)
        self.lead.refresh_from_db()
        self.assertEqual((self.lead.acceso_origen, self.lead.acceso_destino), ("NOT_APPLICABLE", "escaleras"))

    def test_items_mapping(self):
        self.adapter.sync(self.complete, self.lead)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.lista_objetos, "1 cama\n10 cajas")

    def test_incomplete_does_not_create_fake_quote(self):
        result = self.adapter.sync(BotState(origin_district="Surco"), self.lead)
        self.assertFalse(result.ready_for_quote)
        self.assertEqual(Cotizacion.objects.count(), 0)
        self.assertTrue(result.missing)

    def test_complete_becomes_ready_for_quote(self):
        result = self.adapter.sync(self.complete, self.lead)
        request = SolicitudCotizacion.objects.get(pk=result.request_id)
        self.assertEqual(request.datos_faltantes, [])
        self.assertIn("lista para cotizar", request.motivo)
        self.assertEqual(Cotizacion.objects.count(), 0)

    def test_repeated_sync_is_idempotent(self):
        first = self.adapter.sync(self.complete, self.lead)
        second = self.adapter.sync(self.complete, self.lead)
        self.assertEqual(first.request_id, second.request_id)
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(SolicitudCotizacion.objects.count(), 1)
        self.assertEqual(LeadUbicacion.objects.count(), 2)

    def test_correction_updates_crm(self):
        self.adapter.sync(self.complete, self.lead)
        corrected = self.complete.copy()
        corrected.origin_district = "San Borja"
        self.adapter.sync(corrected, self.lead)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.distrito_origen, "San Borja")
        self.assertEqual(LeadUbicacion.objects.get(lead=self.lead, tipo="origen").distrito, "San Borja")
