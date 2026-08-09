from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.clientes.models import Cliente

from .models import Lead, LeadUbicacion
from .route import remove_stop, replace_lead_route


class OrderedRouteTests(TestCase):
    def setUp(self):
        self.lead = Lead.objects.create(cliente=Cliente.objects.create(telefono="route-test"))

    def test_four_locations_keep_order_and_access(self):
        replace_lead_route(self.lead, [
            {"tipo": "origen", "distrito": "Surco", "piso": 4, "ascensor": False},
            {"tipo": "parada", "distrito": "San Borja", "piso": 1},
            {"tipo": "parada", "distrito": "La Victoria", "piso": 2, "ascensor": True},
            {"tipo": "destino", "distrito": "Miraflores", "piso": 8, "ascensor": True},
        ])
        self.assertEqual(
            list(self.lead.ubicaciones.values_list("orden", "tipo", "distrito", "piso")),
            [(0, "origen", "Surco", 4), (1, "parada", "San Borja", 1),
             (2, "parada", "La Victoria", 2), (3, "destino", "Miraflores", 8)],
        )

    def test_clear_stop_removal_renumbers_without_touching_endpoints(self):
        replace_lead_route(self.lead, [
            {"tipo": "origen", "distrito": "Surco"},
            {"tipo": "parada", "distrito": "San Borja"},
            {"tipo": "destino", "distrito": "Miraflores"},
        ])
        self.assertTrue(remove_stop(self.lead, "San Borja"))
        self.assertEqual(
            list(self.lead.ubicaciones.values_list("orden", "tipo", "distrito")),
            [(0, "origen", "Surco"), (1, "destino", "Miraflores")],
        )

    def test_service_validation_rejects_invalid_route(self):
        with self.assertRaises(ValidationError):
            replace_lead_route(self.lead, [{"tipo": "origen", "distrito": "Surco"}])

    def test_database_rejects_duplicate_origin(self):
        LeadUbicacion.objects.create(lead=self.lead, orden=0, tipo="origen", distrito="Surco")
        with self.assertRaises(IntegrityError), transaction.atomic():
            LeadUbicacion.objects.create(lead=self.lead, orden=1, tipo="origen", distrito="Ate")
