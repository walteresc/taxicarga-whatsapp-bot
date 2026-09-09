"""F2 · Mesas de negociación: servicios + API."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.tercerizacion import negociacion as neg
from apps.tercerizacion.models import HiloNegociacion, MensajeNegociacion

User = get_user_model()


def _lead(n=0):
    cli = Cliente.objects.create(nombre=f"Cliente {n}", telefono=f"+5199000{n:04d}")
    return Lead.objects.create(
        cliente=cli, tipo_servicio="carga", distrito_origen="Lima", distrito_destino="Callao",
    )


class ServiciosNegociacionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("neg", password="x")
        self.lead = _lead(1)

    def test_abrir_hilo_es_idempotente_y_rellena_objetivo(self):
        h1, creado1 = neg.abrir_hilo(self.lead, HiloNegociacion.TIPO_VENTA,
                                     usuario=self.user, contraparte=self.lead.cliente)
        h2, creado2 = neg.abrir_hilo(self.lead, HiloNegociacion.TIPO_VENTA,
                                     usuario=self.user, contraparte=self.lead.cliente,
                                     monto_objetivo=500)
        self.assertTrue(creado1)
        self.assertFalse(creado2)
        self.assertEqual(h1.id, h2.id)
        h2.refresh_from_db()
        self.assertEqual(h2.monto_objetivo, 500)

    def test_propuesta_aceptada_fija_monto_acordado_y_estado(self):
        hilo, _ = neg.abrir_hilo(self.lead, HiloNegociacion.TIPO_VENTA,
                                 usuario=self.user, contraparte=self.lead.cliente)
        prop = neg.publicar_mensaje(hilo, emisor=MensajeNegociacion.EMISOR_CLIENTE,
                                    autor=self.user, propuesta_monto=450)
        neg.responder_propuesta(prop, "aceptar", usuario=self.user)
        hilo.refresh_from_db()
        self.assertEqual(hilo.estado, HiloNegociacion.ESTADO_ACUERDO)
        self.assertEqual(hilo.monto_acordado, 450)
        self.assertTrue(hilo.mensajes.filter(tipo=MensajeNegociacion.TIPO_SISTEMA).exists())

    def test_contraoferta_genera_propuesta_del_otro_lado(self):
        hilo, _ = neg.abrir_hilo(self.lead, HiloNegociacion.TIPO_VENTA,
                                 usuario=self.user, contraparte=self.lead.cliente)
        prop = neg.publicar_mensaje(hilo, emisor=MensajeNegociacion.EMISOR_CLIENTE,
                                    autor=self.user, propuesta_monto=400)
        nueva = neg.responder_propuesta(prop, "contraofertar", usuario=self.user, monto=460)
        self.assertEqual(nueva.emisor, MensajeNegociacion.EMISOR_TAXICARGA)
        self.assertEqual(nueva.propuesta_monto, 460)
        prop.refresh_from_db()
        self.assertEqual(prop.propuesta_estado, MensajeNegociacion.PROP_CONTRAOFERTADA)
        hilo.refresh_from_db()
        self.assertEqual(hilo.monto_actual, 460)

    def test_hilo_pausado_bloquea_a_la_contraparte_pero_no_al_asesor(self):
        hilo, _ = neg.abrir_hilo(self.lead, HiloNegociacion.TIPO_VENTA,
                                 usuario=self.user, contraparte=self.lead.cliente)
        neg.pausar_hilo(hilo, self.user, "revisar ruta")
        with self.assertRaises(neg.NegociacionError):
            neg.publicar_mensaje(hilo, emisor=MensajeNegociacion.EMISOR_CLIENTE, texto="hola")
        # el asesor sí puede
        neg.publicar_mensaje(hilo, emisor=MensajeNegociacion.EMISOR_TAXICARGA,
                             autor=self.user, texto="un momento por favor")

    def test_margen_en_vivo_venta_menos_compra(self):
        v, _ = neg.abrir_hilo(self.lead, HiloNegociacion.TIPO_VENTA,
                              usuario=self.user, contraparte=self.lead.cliente)
        pv = neg.publicar_mensaje(v, emisor=MensajeNegociacion.EMISOR_TAXICARGA,
                                  autor=self.user, propuesta_monto=1000)
        neg.responder_propuesta(pv, "aceptar", usuario=self.user)
        c, _ = neg.abrir_hilo(self.lead, HiloNegociacion.TIPO_COMPRA, usuario=self.user)
        pc = neg.publicar_mensaje(c, emisor=MensajeNegociacion.EMISOR_TRANSPORTISTA,
                                  autor=self.user, propuesta_monto=700)
        neg.responder_propuesta(pc, "aceptar", usuario=self.user)
        m = neg.margen_en_vivo(self.lead)
        self.assertEqual(m["sale"], 1000.0)
        self.assertEqual(m["cost"], 700.0)
        self.assertEqual(m["amount"], 300.0)
        self.assertEqual(m["pct"], 30.0)


class ApiNegociacionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("negapi", password="x")
        self.user.groups.add(Group.objects.get_or_create(name="Asesor de Ventas")[0])
        self.client.force_login(self.user)
        self.lead = _lead(2)
        self.hilo, _ = neg.abrir_hilo(self.lead, HiloNegociacion.TIPO_VENTA,
                                      usuario=self.user, contraparte=self.lead.cliente,
                                      monto_objetivo=800)

    def test_lista_y_detalle(self):
        r = self.client.get("/api/v2/negotiations/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["results"][0]["type"], "sale")

        r = self.client.get(f"/api/v2/negotiations/{self.hilo.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["state"], "open")
        self.assertIn("margin", r.data)
        self.assertIn("messages", r.data)

    def test_postear_propuesta_y_responder(self):
        r = self.client.post(f"/api/v2/negotiations/{self.hilo.id}/messages",
                             {"sender": "client", "proposalAmount": "720"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["currentAmount"], 720.0)
        msg_id = [m for m in r.data["messages"] if m["kind"] == "propuesta"][0]["id"]

        r = self.client.post(f"/api/v2/negotiations/messages/{msg_id}/respond",
                             {"action": "accept"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["state"], "agreement")
        self.assertEqual(r.data["agreedAmount"], 720.0)

    def test_pausar_bloquea_mensaje_de_cliente_via_api(self):
        self.client.post(f"/api/v2/negotiations/{self.hilo.id}/pause",
                         {"reason": "dato raro"}, format="json")
        r = self.client.post(f"/api/v2/negotiations/{self.hilo.id}/messages",
                             {"sender": "client", "text": "insisto"}, format="json")
        self.assertEqual(r.status_code, 400)

        r = self.client.post(f"/api/v2/negotiations/{self.hilo.id}/resume", {}, format="json")
        self.assertEqual(r.data["state"], "open")


class MargenGateTests(APITestCase):
    def setUp(self):
        self.asesor = User.objects.create_user("ases_margen", password="x")
        self.asesor.groups.add(Group.objects.get_or_create(name="Asesor de Ventas")[0])
        self.jefe = User.objects.create_user("jefe_margen", password="x")
        self.jefe.groups.add(Group.objects.get_or_create(name="Gerencia")[0])
        self.lead = _lead(9)
        self.venta, _ = neg.abrir_hilo(self.lead, HiloNegociacion.TIPO_VENTA,
                                       usuario=self.jefe, contraparte=self.lead.cliente)
        self.compra, _ = neg.abrir_hilo(self.lead, HiloNegociacion.TIPO_COMPRA, usuario=self.jefe)

    def test_asesor_no_ve_hilos_de_compra_ni_margen(self):
        self.client.force_login(self.asesor)
        codes = {h["type"] for h in self.client.get("/api/v2/negotiations/").data["results"]}
        self.assertEqual(codes, {"sale"})

        r = self.client.get(f"/api/v2/negotiations/{self.venta.id}/")
        self.assertIsNone(r.data["margin"])
        self.assertFalse(r.data["canSeeMargin"])

        self.assertEqual(self.client.get(f"/api/v2/negotiations/{self.compra.id}/").status_code, 403)

    def test_gerencia_ve_compra_y_margen(self):
        self.client.force_login(self.jefe)
        r = self.client.get(f"/api/v2/negotiations/{self.venta.id}/")
        self.assertTrue(r.data["canSeeMargin"])
        self.assertIsNotNone(r.data["margin"])
        self.assertEqual(self.client.get(f"/api/v2/negotiations/{self.compra.id}/").status_code, 200)
