"""F8 · Portal Cliente: ver ofertas de transportistas de MI carga y marcar
cuál prefiero (nunca adjudica sola — es una señal para que el asesor
confirme, ver apps/tercerizacion/models.py::PublicacionCarga)."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.clientes.models import Cliente, ClienteUsuario
from apps.leads.models import Lead
from apps.servicios.models import Servicio
from apps.tercerizacion.models import OfertaTransportista, PublicacionCarga, Transportista

User = get_user_model()


def _customer(name):
    u = User.objects.create_user(f"cust_{name}", password="x")
    u.groups.add(Group.objects.get_or_create(name="Cliente Portal")[0])
    c = Cliente.objects.create(nombre=f"Cliente {name}", telefono=f"+51944{abs(hash(name)) % 1000000:06d}")
    cu = ClienteUsuario.objects.create(usuario=u, cliente=c)
    return cu, u


def _carrier(name):
    return Transportista.objects.create(nombre=f"Transportes {name}")


class _WithPublication(APITestCase):
    def setUp(self):
        self.cu, self.u = _customer("uno")
        self.cu2, self.u2 = _customer("dos")
        self.lead = Lead.objects.create(
            cliente=self.cu.cliente, tipo_servicio="carga", codigo="CRG-TEST1",
            distrito_origen="Lima", distrito_destino="Piura", es_interprovincial=True,
        )
        self.svc = Servicio.objects.create(
            lead_origen=self.lead, cliente=self.cu.cliente, tipo_servicio="carga",
            distrito_origen="Lima", distrito_destino="Piura",
            fecha_servicio=date.today() + timedelta(days=3), horario_servicio="08:00",
        )
        self.pub = PublicacionCarga.objects.create(
            servicio=self.svc, codigo="P01", texto_publicado="x",
            estado=PublicacionCarga.ESTADO_CON_OFERTAS, modo_precio=PublicacionCarga.PRECIO_ABIERTO,
        )
        self.carrier = _carrier("rapido")
        self.oferta = OfertaTransportista.objects.create(
            publicacion=self.pub, transportista=self.carrier,
            precio_ofertado=300, modalidad="completa",
        )


class CustomerLoadOffersViewTests(_WithPublication):
    def test_lista_ofertas_traducidas_nunca_expone_el_costo_crudo(self):
        self.client.force_login(self.u)
        r = self.client.get(f"/api/v2/portal/customer/loads/{self.lead.codigo}/offers")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(r.data["offers"]), 1)
        offer = r.data["offers"][0]
        self.assertEqual(offer["carrierName"], "Transportes rapido")
        self.assertEqual(offer["modality"], "completa")
        # El precio mostrado NUNCA es el costo crudo (300) — es costo con markup.
        self.assertGreater(offer["price"], 300)
        self.assertNotIn("firstAmount", offer)
        self.assertNotIn("currentAmount", offer)

    def test_sin_publicacion_devuelve_listas_vacias_no_error(self):
        lead2 = Lead.objects.create(cliente=self.cu.cliente, tipo_servicio="carga", codigo="CRG-SINPUB")
        self.client.force_login(self.u)
        r = self.client.get(f"/api/v2/portal/customer/loads/{lead2.codigo}/offers")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["offers"], [])
        self.assertFalse(r.data["awarded"])

    def test_otro_cliente_no_ve_estas_ofertas(self):
        self.client.force_login(self.u2)
        r = self.client.get(f"/api/v2/portal/customer/loads/{self.lead.codigo}/offers")
        self.assertEqual(r.status_code, 404)

    def test_ofertas_rechazadas_no_se_muestran(self):
        OfertaTransportista.objects.create(
            publicacion=self.pub, transportista=_carrier("otro"),
            precio_ofertado=250, estado=OfertaTransportista.ESTADO_RECHAZADA,
        )
        self.client.force_login(self.u)
        r = self.client.get(f"/api/v2/portal/customer/loads/{self.lead.codigo}/offers")
        self.assertEqual(len(r.data["offers"]), 1)


class CustomerLoadPreferOfferViewTests(_WithPublication):
    def test_preferir_una_oferta_real(self):
        self.client.force_login(self.u)
        r = self.client.post(
            f"/api/v2/portal/customer/loads/{self.lead.codigo}/offers/prefer",
            {"offerId": self.oferta.id}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.pub.refresh_from_db()
        self.assertEqual(self.pub.oferta_preferida_cliente_id, self.oferta.id)
        self.assertFalse(self.pub.prefiere_directo_taxicarga)
        self.assertIsNotNone(self.pub.preferencia_cliente_en)

    def test_preferir_directo_taxicarga_sin_offer_id(self):
        self.client.force_login(self.u)
        r = self.client.post(
            f"/api/v2/portal/customer/loads/{self.lead.codigo}/offers/prefer", {}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.pub.refresh_from_db()
        self.assertIsNone(self.pub.oferta_preferida_cliente_id)
        self.assertTrue(self.pub.prefiere_directo_taxicarga)

    def test_no_adjudica_solo_marca_preferencia(self):
        self.client.force_login(self.u)
        self.client.post(
            f"/api/v2/portal/customer/loads/{self.lead.codigo}/offers/prefer",
            {"offerId": self.oferta.id}, format="json",
        )
        self.pub.refresh_from_db()
        self.assertEqual(self.pub.estado, PublicacionCarga.ESTADO_CON_OFERTAS)  # sin cambio
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.estado, OfertaTransportista.ESTADO_PENDIENTE)  # sin cambio

    def test_no_se_puede_preferir_de_otra_carga(self):
        self.client.force_login(self.u)
        otra = OfertaTransportista.objects.create(
            publicacion=PublicacionCarga.objects.create(
                servicio=Servicio.objects.create(
                    lead_origen=Lead.objects.create(cliente=self.cu2.cliente, tipo_servicio="carga", codigo="CRG-OTRA"),
                    cliente=self.cu2.cliente, tipo_servicio="carga",
                    fecha_servicio=date.today(), horario_servicio="08:00",
                ),
                codigo="P02", texto_publicado="x",
            ),
            transportista=self.carrier, precio_ofertado=100,
        )
        r = self.client.post(
            f"/api/v2/portal/customer/loads/{self.lead.codigo}/offers/prefer",
            {"offerId": otra.id}, format="json",
        )
        self.assertEqual(r.status_code, 404)

    def test_ya_adjudicada_no_permite_cambiar_preferencia(self):
        self.pub.estado = PublicacionCarga.ESTADO_ADJUDICADA
        self.pub.save(update_fields=["estado"])
        self.client.force_login(self.u)
        r = self.client.post(
            f"/api/v2/portal/customer/loads/{self.lead.codigo}/offers/prefer",
            {"offerId": self.oferta.id}, format="json",
        )
        self.assertEqual(r.status_code, 400)


class StaffSeesClientPreferenceTests(_WithPublication):
    def test_publication_item_expone_la_preferencia_del_cliente(self):
        from apps.tercerizacion.api.publicaciones_views import publication_item

        self.pub.oferta_preferida_cliente = self.oferta
        self.pub.save(update_fields=["oferta_preferida_cliente"])
        item = publication_item(self.pub)
        self.assertEqual(item["clientPreferredOfferId"], self.oferta.id)
        self.assertFalse(item["clientPrefersDirect"])
