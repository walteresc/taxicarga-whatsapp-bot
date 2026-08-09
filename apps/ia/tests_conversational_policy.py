from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.clientes.models import Cliente
from apps.ia.conversation_engine import handle_incoming_message
from apps.ia.conversation_policy import booking_missing_fields, quote_missing_fields
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp


@override_settings(OPENAI_API_KEY="")
class ConversationalPolicyTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(telefono="51900000001")

    def test_quote_contract_excludes_administrative_fields_and_uses_defaults(self):
        lead = Lead.objects.create(
            cliente=self.cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Miraflores",
            lista_objetos="cama y refrigeradora",
            piso_origen=1,
            piso_destino=1,
            camion_llega_origen=True,
            camion_llega_destino=True,
        )

        self.assertEqual(quote_missing_fields(lead, requires_truck_access=True), [])
        self.assertNotIn("fecha_servicio", quote_missing_fields(lead))
        self.assertNotIn("cliente_nombre", quote_missing_fields(lead))

    def test_booking_contract_requires_name_schedule_and_addresses_not_dni(self):
        lead = Lead.objects.create(cliente=self.cliente, etapa_conversacion=Lead.ETAPA_RESERVA)

        missing = booking_missing_fields(lead)

        self.assertEqual(
            missing,
            ["cliente_nombre", "direccion_origen", "direccion_destino", "fecha_servicio", "horario_servicio"],
        )
        self.assertNotIn("dni_reserva", missing)

    def test_case_1_applies_defaults_and_only_asks_grouped_access(self):
        reply = handle_incoming_message(
            self.cliente,
            "Quiero una mudanza de Surco a Miraflores. Llevo cama, refrigeradora y unas 15 cajas.",
        )
        lead = self.cliente.leads.get()

        self.assertTrue(lead.incluye_personal_carga)
        self.assertEqual(lead.modalidad_servicio, "sin embalaje")
        self.assertFalse(lead.requiere_desarmado)
        self.assertIn("piso", reply.lower())
        self.assertIn("ascensor", reply.lower())
        self.assertNotIn("nombre", reply.lower())
        self.assertNotIn("fecha", reply.lower())

    def test_case_2_captures_both_access_conditions_in_one_turn(self):
        Lead.objects.create(
            cliente=self.cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Miraflores",
            lista_objetos="cama",
        )

        handle_incoming_message(
            self.cliente,
            "Origen tercer piso con ascensor y destino segundo piso sin ascensor.",
        )
        lead = self.cliente.leads.get()

        self.assertEqual((lead.piso_origen, lead.piso_destino), (3, 2))
        self.assertEqual((lead.ascensor_origen, lead.ascensor_destino), (True, False))

    def test_case_3_complete_first_message_prices_directly(self):
        reply = handle_incoming_message(
            self.cliente,
            "Mudanza de Surco a Miraflores, cama y refrigeradora, origen primer piso, "
            "destino primer piso; en ambos el camion llega a la puerta.",
        )
        lead = self.cliente.leads.get()

        self.assertEqual(lead.estado, Lead.COTIZADO)
        self.assertIsNotNone(lead.precio_cotizado)
        self.assertIn("s/", reply.lower())

    def test_case_4_explicit_transport_only_overrides_default(self):
        handle_incoming_message(self.cliente, "Quiero una mudanza")
        handle_incoming_message(self.cliente, "Nosotros cargamos, solo quiero el camión.")

        self.assertFalse(self.cliente.leads.get().incluye_personal_carga)

    def test_case_5_answers_customer_question_then_resumes_collection(self):
        lead = Lead.objects.create(
            cliente=self.cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Miraflores",
            lista_objetos="cama",
            incluye_personal_carga=True,
        )

        reply = handle_incoming_message(self.cliente, "¿El precio incluye ayudantes?")

        self.assertIn("personal", reply.lower())
        self.assertIn("pisos", reply.lower())
        lead.refresh_from_db()
        self.assertIsNone(lead.precio_cotizado)

    def test_case_6_explicit_route_correction_replaces_destination(self):
        Lead.objects.create(
            cliente=self.cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Miraflores",
        )

        handle_incoming_message(self.cliente, "Perdón, no era Miraflores, es San Isidro")

        self.assertEqual(self.cliente.leads.get().distrito_destino, "San Isidro")

    def test_cases_7_and_8_price_without_date_or_name(self):
        lead = Lead.objects.create(
            cliente=self.cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Miraflores",
            lista_objetos="mesa",
            piso_origen=1,
            piso_destino=1,
        )

        reply = handle_incoming_message(self.cliente, "Eso sería todo")
        lead.refresh_from_db()

        self.assertEqual(lead.estado, Lead.COTIZADO)
        self.assertFalse(self.cliente.nombre)
        self.assertIsNone(lead.fecha_servicio)
        self.assertIn("s/", reply.lower())

    def test_case_9_persists_many_reliable_fields(self):
        handle_incoming_message(
            self.cliente,
            "Mudanza de Surco a Miraflores mañana a las 9 am; cama y 10 cajas; nosotros cargamos.",
        )
        lead = self.cliente.leads.get()

        self.assertEqual(lead.tipo_servicio, "mudanza")
        self.assertEqual(lead.distrito_origen, "Surco")
        self.assertEqual(lead.distrito_destino, "Miraflores")
        self.assertTrue(lead.fecha_servicio)
        self.assertEqual(lead.horario_servicio, "9:00 am")
        self.assertTrue(lead.lista_objetos)
        self.assertFalse(lead.incluye_personal_carga)

    @patch("apps.ia.conversation_engine.extract_lead_with_ai", return_value=None)
    def test_case_10_ai_error_does_not_crash_or_invent_price(self, _mock_ai):
        reply = handle_incoming_message(self.cliente, "Quiero una mudanza")

        self.assertIn("distrito", reply.lower())
        self.assertIsNone(self.cliente.leads.get().precio_cotizado)

    def test_case_11_route_with_stop_goes_to_manual_quote(self):
        lead = Lead.objects.create(cliente=self.cliente)
        conversation = ConversacionWhatsApp.objects.create(cliente=self.cliente, lead=lead)

        reply = handle_incoming_message(
            self.cliente,
            "Recojo en Surco, paso por San Borja y termino en Miraflores.",
        )
        lead.refresh_from_db()
        conversation.refresh_from_db()

        self.assertTrue(lead.atencion_humana)
        self.assertIsNone(lead.precio_cotizado)
        self.assertEqual(
            list(lead.ubicaciones.values_list("tipo", "distrito")),
            [("origen", "Surco"), ("parada", "San Borja"), ("destino", "Miraflores")],
        )
        self.assertEqual(conversation.estado_cotizacion, ConversacionWhatsApp.COTIZACION_PENDIENTE)
        self.assertIn("asesor", reply.lower())
