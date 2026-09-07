"""API v2 del pipeline comercial — bandeja 'Potenciales': leads que siguen
conversando sin haber escalado todavía a Para revisión/Por cotizar/
Cotizaciones/Reservas."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from unittest.mock import patch

from apps.clientes.models import Cliente
from apps.cotizador.models import CotizacionComercial, SolicitudCotizacion
from apps.leads.models import Lead, LeadUbicacion
from apps.servicios.models import Servicio
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel

User = get_user_model()


def _cliente(nombre="Cliente"):
    _cliente.n += 1
    return Cliente.objects.create(nombre=nombre, telefono=f"+51900{_cliente.n:06d}")


_cliente.n = 0


class _Sup(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("potencial_test", password="x")
        g, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        self.user.groups.add(g)
        self.client.force_login(self.user)


class PotencialesListTests(_Sup):
    def test_lead_activo_sin_escalar_aparece_como_potencial(self):
        lead = Lead.objects.create(
            cliente=_cliente("Juan Perez"), tipo_servicio="mudanza",
            distrito_origen="San Isidro", distrito_destino="Surco",
        )
        r = self.client.get("/api/v2/pipeline/potentials/")
        self.assertEqual(r.status_code, 200)
        ids = [row["leadId"] for row in r.data["results"]]
        self.assertIn(lead.id, ids)

        d = self.client.get(f"/api/v2/pipeline/potentials/{lead.id}/")
        self.assertEqual(d.status_code, 200)
        self.assertEqual(d.data["origin"], "San Isidro")

    def test_lead_que_requiere_asesor_no_es_potencial(self):
        lead = Lead.objects.create(cliente=_cliente(), requiere_asesor=True)
        ids = [row["leadId"] for row in self.client.get("/api/v2/pipeline/potentials/").data["results"]]
        self.assertNotIn(lead.id, ids)

    def test_lead_cerrado_no_es_potencial(self):
        lead = Lead.objects.create(cliente=_cliente(), estado=Lead.CERRADO)
        ids = [row["leadId"] for row in self.client.get("/api/v2/pipeline/potentials/").data["results"]]
        self.assertNotIn(lead.id, ids)

    def test_lead_con_solicitud_activa_no_es_potencial(self):
        lead = Lead.objects.create(cliente=_cliente())
        SolicitudCotizacion.objects.create(
            lead=lead, tipo=SolicitudCotizacion.TIPO_COTIZACION,
            estado=SolicitudCotizacion.PENDIENTE, motivo="x",
        )
        ids = [row["leadId"] for row in self.client.get("/api/v2/pipeline/potentials/").data["results"]]
        self.assertNotIn(lead.id, ids)

    def test_lead_con_cotizacion_en_juego_no_es_potencial(self):
        lead = Lead.objects.create(cliente=_cliente())
        CotizacionComercial.objects.create(lead=lead, estado="enviada", codigo="COT-TEST-0001")
        ids = [row["leadId"] for row in self.client.get("/api/v2/pipeline/potentials/").data["results"]]
        self.assertNotIn(lead.id, ids)

    def test_lead_con_servicio_generado_no_es_potencial(self):
        lead = Lead.objects.create(cliente=_cliente())
        Servicio.objects.create(lead_origen=lead, estado="pendiente")
        ids = [row["leadId"] for row in self.client.get("/api/v2/pipeline/potentials/").data["results"]]
        self.assertNotIn(lead.id, ids)

    def test_counts_incluye_potentials(self):
        # Cuenta relativa, no absoluta: la base de test --keepdb puede traer
        # leads residuales de otras suites que también califican como
        # potenciales (mismo criterio ya aplicado en tests_conversacion_manual.py).
        base = self.client.get("/api/v2/pipeline/counts").data["potentials"]
        Lead.objects.create(cliente=_cliente())
        Lead.objects.create(cliente=_cliente())
        r = self.client.get("/api/v2/pipeline/counts")
        self.assertEqual(r.data["potentials"], base + 2)


class LeadStageMoveTests(_Sup):
    def test_etapa_actual_de_un_lead_nuevo_es_potencial(self):
        lead = Lead.objects.create(cliente=_cliente())
        r = self.client.get(f"/api/v2/pipeline/leads/{lead.id}/stage")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["stage"], "potentials")

    def test_mover_potencial_a_revision_y_a_por_cotizar_y_volver(self):
        lead = Lead.objects.create(cliente=_cliente())

        r = self.client.post(f"/api/v2/pipeline/leads/{lead.id}/stage", {"stage": "review"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["stage"], "review")
        self.assertEqual(
            SolicitudCotizacion.objects.filter(lead=lead, tipo="revision", estado="pendiente").count(), 1,
        )
        lead.refresh_from_db()
        self.assertTrue(lead.requiere_asesor)

        r = self.client.post(f"/api/v2/pipeline/leads/{lead.id}/stage", {"stage": "quoting"})
        self.assertEqual(r.data["stage"], "quoting")
        self.assertEqual(
            SolicitudCotizacion.objects.filter(lead=lead, tipo="cotizacion", estado__in=("pendiente", "en_proceso")).count(), 1,
        )

        r = self.client.post(f"/api/v2/pipeline/leads/{lead.id}/stage", {"stage": "potentials"})
        self.assertEqual(r.data["stage"], "potentials")
        self.assertFalse(
            SolicitudCotizacion.objects.filter(lead=lead, estado__in=("pendiente", "en_proceso")).exists(),
        )

    def test_no_permite_mover_a_cotizaciones_a_mano(self):
        lead = Lead.objects.create(cliente=_cliente())
        r = self.client.post(f"/api/v2/pipeline/leads/{lead.id}/stage", {"stage": "quotes"})
        self.assertEqual(r.status_code, 400)

    def test_lead_con_reserva_no_se_puede_mover(self):
        lead = Lead.objects.create(cliente=_cliente())
        Servicio.objects.create(lead_origen=lead, estado="pendiente")
        r = self.client.get(f"/api/v2/pipeline/leads/{lead.id}/stage")
        self.assertEqual(r.data["stage"], "bookings")
        r = self.client.post(f"/api/v2/pipeline/leads/{lead.id}/stage", {"stage": "quoting"})
        self.assertEqual(r.status_code, 400)


class QuickQuoteBookingTests(_Sup):
    def setUp(self):
        super().setUp()
        self.channel = WhatsAppChannel.objects.create(
            nombre="Canal", phone_number_id="qqb-test", activo=True,
        )

    def _lead_con_conv(self):
        lead = Lead.objects.create(cliente=_cliente("Ana Quispe"), whatsapp_channel=self.channel)
        self.conv = ConversacionWhatsApp.objects.create(
            cliente=lead.cliente, lead=lead, channel=self.channel,
        )
        return lead

    @patch("apps.whatsapp.services.send_crm_message", return_value={"success": True, "message": None, "error_code": None, "error_detail": None})
    def test_cotizar_rapido_deja_la_conversacion_en_cotizaciones(self, _send):
        lead = self._lead_con_conv()
        r = self.client.post(
            f"/api/v2/pipeline/leads/{lead.id}/quick-quote",
            {"price": "1800", "message": "Hola, tu mudanza sale S/ 1800. ¿Confirmamos?"},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["stage"], "quotes")
        self.assertTrue(CotizacionComercial.objects.filter(lead=lead, estado="enviada").exists())
        self.assertEqual(self.client.get(f"/api/v2/pipeline/leads/{lead.id}/stage").data["stage"], "quotes")
        # La conversación queda asignada al asesor para poder seguir chateando.
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.estado_atencion, "asesor")
        self.assertEqual(self.conv.responsable_id, self.user.id)

    @patch("apps.whatsapp.services.send_crm_message", return_value={"success": True, "message": None, "error_code": None, "error_detail": None})
    def test_recotizar_actualiza_el_precio(self, _send):
        lead = self._lead_con_conv()
        u = f"/api/v2/pipeline/leads/{lead.id}/quick-quote"
        self.client.post(u, {"price": "1800", "message": "S/ 1800"}, format="json")
        r = self.client.post(u, {"price": "1500", "message": "Ajusto a S/ 1500"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["requoted"])
        cot = CotizacionComercial.objects.get(lead=lead)
        last = cot.revisiones.order_by("-numero").first()
        self.assertEqual(str(last.precio_final), "1500.00")
        lead.refresh_from_db()
        self.assertEqual(str(lead.precio_cotizado), "1500.00")

    def test_cotizar_rapido_sin_mensaje_400(self):
        lead = self._lead_con_conv()
        r = self.client.post(
            f"/api/v2/pipeline/leads/{lead.id}/quick-quote", {"price": "1800", "message": ""}, format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_reservar_rapido_crea_la_reserva(self):
        lead = self._lead_con_conv()
        r = self.client.post(
            f"/api/v2/pipeline/leads/{lead.id}/quick-booking",
            {
                "customerName": "Ana Quispe",
                "serviceDate": "2026-10-01",
                "schedule": "09:00",
                "type": "mudanza",
                "addressOrigin": "Av. Larco 123",
                "addressDestination": "Calle Los Pinos 456",
                "districtOrigin": "Miraflores",
                "districtDestination": "Surco",
                "price": "1800",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["stage"], "bookings")
        servicio = Servicio.objects.get(lead_origen=lead)
        self.assertEqual(str(servicio.precio), "1800.00")
        self.assertEqual(self.client.get(f"/api/v2/pipeline/leads/{lead.id}/stage").data["stage"], "bookings")

    def test_reservar_rapido_falta_direccion_especifica_400(self):
        lead = self._lead_con_conv()
        r = self.client.post(
            f"/api/v2/pipeline/leads/{lead.id}/quick-booking",
            {
                "serviceDate": "2026-10-01", "schedule": "09:00",
                "addressOrigin": "por Miraflores", "addressDestination": "por Surco",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 400)
