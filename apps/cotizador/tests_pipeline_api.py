"""API v2 del pipeline comercial — contadores + bandeja 'Para revisión'."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.clientes.models import Cliente
from apps.cotizador.models import SolicitudCotizacion
from apps.cotizador import pipeline
from apps.leads.models import Lead

User = get_user_model()


def _lead(**kw):
    cli = Cliente.objects.create(nombre=kw.pop("nombre", "Cliente"), telefono=kw.pop("tel", "+51900%06d" % _lead.n))
    _lead.n += 1
    base = dict(cliente=cli, tipo_servicio="carga", distrito_origen="Piura", distrito_destino="Tumbes",
                estado=Lead.NUEVO, es_interprovincial=True, requiere_asesor=True)
    base.update(kw)
    lead = Lead.objects.create(**base)
    # El signal usa transaction.on_commit, que no dispara en TestCase; lo llamamos
    # explícito para preparar los datos (hay un test aparte para el signal real).
    pipeline.sync_review_request(lead)
    return lead


_lead.n = 0


class _Sup(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("pipe", password="x")
        g, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        self.user.groups.add(g)
        self.client.force_login(self.user)


class ReviewSyncTests(_Sup):
    def test_signal_crea_solicitud_revision_al_marcar_requiere_asesor(self):
        with self.captureOnCommitCallbacks(execute=True):
            cli = Cliente.objects.create(nombre="X", telefono="+51988000111")
            lead = Lead.objects.create(
                cliente=cli, tipo_servicio="carga", distrito_origen="Piura",
                distrito_destino="Tumbes", es_interprovincial=True, requiere_asesor=True,
            )
        s = SolicitudCotizacion.objects.filter(lead=lead, tipo="revision").first()
        self.assertIsNotNone(s)
        self.assertEqual(s.estado, "pendiente")
        self.assertIn("fuera de Lima", s.motivo)

    def test_no_duplica_si_ya_hay_solicitud_activa(self):
        lead = _lead()  # ya llama sync_review_request una vez
        pipeline.sync_review_request(lead)
        self.assertEqual(SolicitudCotizacion.objects.filter(lead=lead).count(), 1)


class CountsTests(_Sup):
    def test_counts(self):
        _lead()
        _lead()
        r = self.client.get("/api/v2/pipeline/counts")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["review"], 2)
        self.assertEqual(r.data["quoting"], 0)


class ReviewListTests(_Sup):
    def test_lista_y_detalle(self):
        lead = _lead(nombre="Interprovincial SA")
        r = self.client.get("/api/v2/pipeline/review/")
        self.assertEqual(r.status_code, 200)
        row = r.data["results"][0]
        self.assertEqual(row["leadId"], lead.id)
        self.assertTrue(row["isInterprovincial"])
        self.assertIn("Piura", row["route"])

        d = self.client.get(f"/api/v2/pipeline/review/{row['id']}/")
        self.assertEqual(d.status_code, 200)
        self.assertEqual(d.data["origin"], "Piura")
        self.assertIn("reason", d.data)

    def test_to_quoting_cambia_de_bandeja(self):
        _lead()
        rid = self.client.get("/api/v2/pipeline/review/").data["results"][0]["id"]
        r = self.client.post(f"/api/v2/pipeline/review/{rid}/to-quoting")
        self.assertEqual(r.status_code, 200)
        s = SolicitudCotizacion.objects.get(pk=rid)
        self.assertEqual(s.tipo, "cotizacion")
        counts = self.client.get("/api/v2/pipeline/counts").data
        self.assertEqual(counts["review"], 0)
        self.assertEqual(counts["quoting"], 1)

    def test_discard_marca_lead_perdido(self):
        lead = _lead()
        rid = self.client.get("/api/v2/pipeline/review/").data["results"][0]["id"]
        r = self.client.post(f"/api/v2/pipeline/review/{rid}/discard", {"reason": "Cliente no responde"}, format="json")
        self.assertEqual(r.status_code, 200)
        lead.refresh_from_db()
        self.assertEqual(lead.estado, Lead.PERDIDO)
        self.assertEqual(SolicitudCotizacion.objects.get(pk=rid).estado, "cancelada")

    def test_discard_sin_motivo_400(self):
        _lead()
        rid = self.client.get("/api/v2/pipeline/review/").data["results"][0]["id"]
        r = self.client.post(f"/api/v2/pipeline/review/{rid}/discard", {}, format="json")
        self.assertEqual(r.status_code, 400)


class QuoteRequestTests(_Sup):
    def _to_quoting(self):
        lead = _lead()
        rid = self.client.get("/api/v2/pipeline/review/").data["results"][0]["id"]
        self.client.post(f"/api/v2/pipeline/review/{rid}/to-quoting")
        return lead, rid

    def test_detalle_trae_sugerido_y_flag_interprovincial(self):
        self._to_quoting()
        rid = self.client.get("/api/v2/pipeline/quote-requests/").data["results"][0]["id"]
        d = self.client.get(f"/api/v2/pipeline/quote-requests/{rid}/")
        self.assertEqual(d.status_code, 200)
        self.assertTrue(d.data["isInterprovincial"])
        self.assertIn("recommended", d.data["suggested"])
        self.assertIn("service", d.data)

    def test_guardar_borrador_y_contador(self):
        self._to_quoting()
        rid = self.client.get("/api/v2/pipeline/quote-requests/").data["results"][0]["id"]
        r = self.client.post(f"/api/v2/pipeline/quote-requests/{rid}/quote",
                             {"price": "2500", "conditions": "x", "validityDays": 7}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["price"], 2500.0)
        d = self.client.get(f"/api/v2/pipeline/quote-requests/{rid}/").data
        self.assertEqual(d["draft"]["price"], 2500.0)

    def test_precio_cero_da_400(self):
        self._to_quoting()
        rid = self.client.get("/api/v2/pipeline/quote-requests/").data["results"][0]["id"]
        r = self.client.post(f"/api/v2/pipeline/quote-requests/{rid}/quote", {"price": "0"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_send_avanza_estado(self):
        from unittest.mock import patch
        self._to_quoting()
        rid = self.client.get("/api/v2/pipeline/quote-requests/").data["results"][0]["id"]
        self.client.post(f"/api/v2/pipeline/quote-requests/{rid}/quote",
                         {"price": "2500", "validityDays": 7}, format="json")
        with patch("apps.cotizador.delivery.queue_revision_whatsapp") as q:
            r = self.client.post(f"/api/v2/pipeline/quote-requests/{rid}/send")
        self.assertEqual(r.status_code, 200, r.data)
        q.assert_called_once()
        from apps.cotizador.models import CotizacionComercial, SolicitudCotizacion
        self.assertEqual(CotizacionComercial.objects.get(codigo=r.data["code"]).estado, "enviada")
        self.assertEqual(SolicitudCotizacion.objects.get(pk=rid).estado, "terminada")
        counts = self.client.get("/api/v2/pipeline/counts").data
        self.assertEqual(counts["quoting"], 0)
        self.assertEqual(counts["quotes"], 1)


class QuoteAndBookingFlowTests(_Sup):
    """Flujo completo: revisión → cotizar → enviar → aceptar → reserva → pago → finalizar."""

    def _sent_quote(self):
        from unittest.mock import patch
        _lead(nombre="Flujo SA",
              direccion_origen="Av. Grau 123, Piura", direccion_destino="Jr. Lima 456, Tumbes",
              fecha_servicio="2026-10-01", horario_servicio="09:00")
        rid = self.client.get("/api/v2/pipeline/review/").data["results"][0]["id"]
        self.client.post(f"/api/v2/pipeline/review/{rid}/to-quoting")
        self.client.post(f"/api/v2/pipeline/quote-requests/{rid}/quote",
                         {"price": "2500", "validityDays": 7}, format="json")
        with patch("apps.cotizador.delivery.queue_revision_whatsapp"):
            self.client.post(f"/api/v2/pipeline/quote-requests/{rid}/send")
        return self.client.get("/api/v2/pipeline/quotes/").data["results"][0]

    def test_lista_y_detalle_cotizaciones(self):
        q = self._sent_quote()
        self.assertEqual(q["state"], "sent")
        d = self.client.get(f"/api/v2/pipeline/quotes/{q['id']}/")
        self.assertEqual(d.status_code, 200)
        self.assertEqual(len(d.data["revisions"]), 1)
        self.assertIn("service", d.data)

    def test_cambiar_estado(self):
        q = self._sent_quote()
        r = self.client.post(f"/api/v2/pipeline/quotes/{q['id']}/state", {"state": "negotiating"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["state"], "negotiating")

    def test_aceptar_crea_reserva_y_audita(self):
        q = self._sent_quote()
        r = self.client.post(f"/api/v2/pipeline/quotes/{q['id']}/accept")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["bookingCode"].startswith("CRG-"))
        from apps.servicios.models import Servicio
        s = Servicio.objects.get(codigo=r.data["bookingCode"])
        self.assertEqual(s.asesor, self.user)
        self.assertIn("cotizacion_aceptada", s.lead_origen.nota_interna)
        counts = self.client.get("/api/v2/pipeline/counts").data
        self.assertEqual(counts["quotes"], 0)
        self.assertEqual(counts["bookings"], 1)

    def test_booking_pago_y_finalizar(self):
        q = self._sent_quote()
        bid = self.client.post(f"/api/v2/pipeline/quotes/{q['id']}/accept").data["bookingId"]
        r = self.client.post(f"/api/v2/pipeline/bookings/{bid}/payment",
                             {"concept": "adelanto", "method": "yape", "amount": "1000"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["paid"], 1000.0)
        self.assertEqual(r.data["balance"], 1500.0)
        fr = self.client.post(f"/api/v2/pipeline/bookings/{bid}/finalize",
                              {"finalAmount": "1500", "method": "yape"}, format="json")
        self.assertEqual(fr.status_code, 200, fr.data)
        self.assertEqual(fr.data["state"], "completed")
        from apps.servicios.models import Servicio
        self.assertIsNotNone(Servicio.objects.get(pk=bid).fecha_finalizacion)

    def test_booking_finalize_pago_mayor_al_saldo_400(self):
        q = self._sent_quote()
        bid = self.client.post(f"/api/v2/pipeline/quotes/{q['id']}/accept").data["bookingId"]
        r = self.client.post(f"/api/v2/pipeline/bookings/{bid}/finalize",
                             {"finalAmount": "9999"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_booking_cancel(self):
        q = self._sent_quote()
        bid = self.client.post(f"/api/v2/pipeline/quotes/{q['id']}/accept").data["bookingId"]
        r = self.client.post(f"/api/v2/pipeline/bookings/{bid}/cancel", {"reason": "Cliente desistió"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["state"], "cancelled")


class RbacTests(APITestCase):
    def test_sin_rol_403(self):
        u = User.objects.create_user("nr", password="x")
        self.client.force_login(u)
        for url in ("/api/v2/pipeline/counts", "/api/v2/pipeline/review/",
                    "/api/v2/pipeline/quote-requests/", "/api/v2/pipeline/quotes/",
                    "/api/v2/pipeline/bookings/"):
            self.assertEqual(self.client.get(url).status_code, 403, url)


class FrequentRouteTests(APITestCase):
    def test_tarifa_ruta_frecuente(self):
        from apps.cotizador.models import ServicioHistorico
        import datetime as dt
        from decimal import Decimal
        for _ in range(4):
            ServicioHistorico.objects.create(
                fecha=dt.date(2025, 1, 1), tipo_servicio="carga",
                distrito_origen="Lima", distrito_destino="Piura centro",
                precio_final=Decimal("2500"), precio_cotizado=Decimal("2500"), cerrado=True,
            )
        out = pipeline.tarifa_ruta_frecuente("Lima", "Piura otro sitio")
        self.assertIsNotNone(out)
        self.assertEqual(out["cases"], 4)
        self.assertEqual(out["typicalPrice"], 2500.0)
        self.assertIsNone(pipeline.tarifa_ruta_frecuente("Miraflores", "Surco"))
