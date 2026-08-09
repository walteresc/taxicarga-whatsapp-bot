from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.cotizador.commercial import aceptar_cotizacion_para_lead
from apps.cotizador.models import CotizacionComercial, RevisionCotizacion
from apps.leads.models import Lead
from apps.leads.route import replace_lead_route

from .models import Servicio
from .services import crear_servicio_desde_lead


class ConfirmedBookingTests(TestCase):
    def setUp(self):
        self.client_record = Cliente.objects.create(nombre="Ana", telefono="51911110000")
        self.lead = Lead.objects.create(
            cliente=self.client_record,
            tipo_servicio="mudanza",
            lista_objetos="cama, refrigeradora y 10 cajas",
            incluye_personal_carga=True,
            cantidad_operarios=2,
            modalidad_servicio="embalaje basico",
            requiere_desarmado=True,
            requiere_armado=True,
            fecha_servicio=timezone.localdate() + timedelta(days=2),
            horario_servicio="9:00 am",
            distrito_origen="Surco",
            distrito_destino="Miraflores",
            direccion_origen="Av. Uno 123",
            direccion_destino="Calle Dos 456",
        )
        replace_lead_route(self.lead, [
            {"tipo": "origen", "distrito": "Surco", "direccion": "Av. Uno 123", "piso": 3, "ascensor": True},
            {"tipo": "parada", "distrito": "San Borja", "direccion": "Av. Tres 789", "piso": 1},
            {"tipo": "destino", "distrito": "Miraflores", "direccion": "Calle Dos 456", "piso": 2, "ascensor": False},
        ])
        self.quote = CotizacionComercial.objects.create(
            codigo="COT-TEST-1", lead=self.lead, origen="bot", estado="enviada"
        )
        self.revision = RevisionCotizacion.objects.create(
            cotizacion=self.quote, numero=1, precio_final=Decimal("480"), enviada=True
        )

    def test_acceptance_and_service_snapshot_are_idempotent(self):
        revision, changed = aceptar_cotizacion_para_lead(self.lead)
        self.assertTrue(changed)
        self.assertEqual(revision, self.revision)

        service, created = crear_servicio_desde_lead(self.lead)
        duplicate, created_again = crear_servicio_desde_lead(self.lead)

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(service, duplicate)
        self.assertEqual(Servicio.objects.filter(lead_origen=self.lead).count(), 1)
        self.assertEqual(service.precio, Decimal("480"))
        self.assertEqual(service.cantidad_operarios, 2)
        self.assertTrue(service.requiere_armado)
        self.assertEqual(service.tipo_embalaje, "basico")
        self.assertEqual(
            list(service.ubicaciones.values_list("tipo", "distrito")),
            [("origen", "Surco"), ("parada", "San Borja"), ("destino", "Miraflores")],
        )

    def test_acceptance_repeated_returns_same_revision(self):
        first, first_changed = aceptar_cotizacion_para_lead(self.lead)
        second, second_changed = aceptar_cotizacion_para_lead(self.lead)
        self.assertEqual(first, second)
        self.assertTrue(first_changed)
        self.assertFalse(second_changed)
