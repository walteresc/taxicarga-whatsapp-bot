"""F3 · Publicar a transportistas, ofertar, adjudicar → ProgramacionServicio."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.campo.models import ProgramacionServicio
from apps.catalogo.models import TipoVehiculo
from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.servicios.models import Servicio
from apps.tercerizacion import adjudicacion as adj
from apps.tercerizacion.models import (
    HiloNegociacion, PublicacionCarga, Transportista, TransportistaVehiculo,
)

User = get_user_model()


def _publicacion(n=0, estado=PublicacionCarga.ESTADO_BORRADOR):
    cli = Cliente.objects.create(nombre=f"C{n}", telefono=f"+51955{n:06d}")
    lead = Lead.objects.create(cliente=cli, tipo_servicio="carga",
                               distrito_origen="Lima", distrito_destino="Callao")
    svc = Servicio.objects.create(lead_origen=lead, cliente=cli, distrito_origen="Lima",
                                  distrito_destino="Callao", fecha_servicio=date.today() + timedelta(days=2),
                                  horario_servicio="09:00", precio=1200,
                                  modalidad_ejecucion=Servicio.MODALIDAD_TERCERIZADO)
    return PublicacionCarga.objects.create(
        servicio=svc, codigo=f"Z{n:02d}", texto_publicado="OFERTA-Z", estado=estado,
        modo_precio=PublicacionCarga.PRECIO_REFERENCIAL, precio_publicado=900,
    )


def _carrier(n=0, vehiculos=1):
    c = Transportista.objects.create(nombre=f"Transportes {n}")
    tv = TipoVehiculo.objects.get(codigo="camion")
    for i in range(vehiculos):
        TransportistaVehiculo.objects.create(transportista=c, placa=f"AB{n}-{i}00", tipo_vehiculo=tv)
    return c


class AdjudicacionServiceTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("adj", password="x")

    def test_publicar_pasa_a_abierta(self):
        pub = _publicacion(1)
        adj.publicar_publicacion(pub, self.user, grupos=["Grupo A"])
        pub.refresh_from_db()
        self.assertEqual(pub.estado, PublicacionCarga.ESTADO_ABIERTA)
        self.assertIsNotNone(pub.publicada_en)
        self.assertIn("Grupo A", pub.grupos_publicados)

    def test_oferta_abre_hilo_compra_y_marca_con_ofertas(self):
        pub = _publicacion(2)
        adj.publicar_publicacion(pub, self.user)
        carrier = _carrier(2)
        oferta, hilo = adj.registrar_oferta(pub, monto=850, usuario=self.user, transportista=carrier)
        pub.refresh_from_db()
        self.assertEqual(pub.estado, PublicacionCarga.ESTADO_CON_OFERTAS)
        self.assertEqual(hilo.tipo, HiloNegociacion.TIPO_COMPRA)
        self.assertEqual(hilo.transportista_id, carrier.id)
        self.assertEqual(hilo.monto_actual, 850)

    def test_adjudicar_crea_programacion_tercerizada_y_rechaza_las_demas(self):
        pub = _publicacion(3)
        adj.publicar_publicacion(pub, self.user)
        c1, c2 = _carrier(31), _carrier(32)
        o1, _ = adj.registrar_oferta(pub, monto=800, usuario=self.user, transportista=c1)
        adj.registrar_oferta(pub, monto=780, usuario=self.user, transportista=c2)

        prog = adj.adjudicar_publicacion(pub, o1, self.user)
        self.assertIsInstance(prog, ProgramacionServicio)
        self.assertIsNone(prog.vehiculo_id)
        self.assertEqual(prog.transportista_id, c1.id)
        self.assertEqual(prog.monto, 800)

        pub.refresh_from_db()
        self.assertEqual(pub.estado, PublicacionCarga.ESTADO_ADJUDICADA)
        self.assertEqual(pub.oferta_ganadora_id, o1.id)
        self.assertEqual(pub.servicio.modalidad_ejecucion, Servicio.MODALIDAD_TERCERIZADO)

        estados = sorted(pub.ofertas.values_list("estado", flat=True))
        self.assertEqual(estados, ["aceptada", "rechazada"])

        ganador = pub.hilos_negociacion.get(transportista=c1)
        self.assertEqual(ganador.estado, HiloNegociacion.ESTADO_CERRADA)
        self.assertEqual(ganador.monto_acordado, 800)

    def test_adjudicar_pide_vehiculo_si_el_afiliado_tiene_varios(self):
        pub = _publicacion(4)
        adj.publicar_publicacion(pub, self.user)
        carrier = _carrier(4, vehiculos=2)
        oferta, _ = adj.registrar_oferta(pub, monto=800, usuario=self.user, transportista=carrier)
        with self.assertRaises(adj.AdjudicacionError):
            adj.adjudicar_publicacion(pub, oferta, self.user)
        tv = carrier.vehiculos.first()
        prog = adj.adjudicar_publicacion(pub, oferta, self.user, transportista_vehiculo=tv)
        self.assertEqual(prog.transportista_vehiculo_id, tv.id)

    def test_oferta_de_contacto_whatsapp_sin_afiliar_no_se_puede_adjudicar(self):
        pub = _publicacion(5)
        adj.publicar_publicacion(pub, self.user)
        contacto = Cliente.objects.create(nombre="WA", telefono="+51999888777", es_transportista=True)
        oferta, _ = adj.registrar_oferta(pub, monto=800, usuario=self.user, cliente=contacto)
        with self.assertRaises(adj.AdjudicacionError):
            adj.adjudicar_publicacion(pub, oferta, self.user)


class PublicationApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("pubapi", password="x")
        self.user.groups.add(Group.objects.get_or_create(name="Despacho")[0])
        self.client.force_login(self.user)
        self.pub = _publicacion(6)

    def test_publish_offer_award_flow(self):
        r = self.client.post(f"/api/v2/publications/{self.pub.id}/publish", {"groups": "Grupo Norte"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["state"], "open")

        carrier = _carrier(6)
        r = self.client.post(f"/api/v2/publications/{self.pub.id}/offers",
                             {"carrierId": carrier.id, "amount": "820"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["state"], "with_offers")
        offer_id = r.data["offers"][0]["id"]

        r = self.client.post(f"/api/v2/publications/{self.pub.id}/award",
                             {"offerId": offer_id}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["ok"])
        self.assertEqual(r.data["publication"]["state"], "awarded")
        self.assertTrue(ProgramacionServicio.objects.filter(pk=r.data["assignmentId"]).exists())

    def test_lista_filtra_por_estado(self):
        r = self.client.get("/api/v2/publications/", {"state": "draft"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(p["id"] == self.pub.id for p in r.data["results"]))
