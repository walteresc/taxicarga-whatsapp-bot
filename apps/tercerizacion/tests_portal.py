"""F5 · Portal del Transportista: scoping + privacidad (nada del cliente)."""
import json
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.catalogo.models import TipoVehiculo
from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.servicios.models import Servicio
from apps.tercerizacion import adjudicacion as adj
from apps.tercerizacion import negociacion as neg
from apps.tercerizacion.models import (
    HiloNegociacion, MensajeNegociacion, PublicacionCarga, Transportista,
    TransportistaVehiculo,
)

User = get_user_model()

CLIENTE_NOMBRE = "Distribuidora Secreta SAC"
CLIENTE_TEL = "+51987654321"


def _carrier(name, vehiculos=1):
    u = User.objects.create_user(f"carr_{name}", password="x")
    u.groups.add(Group.objects.get_or_create(name="Transportista")[0])
    c = Transportista.objects.create(nombre=f"Transportes {name}", usuario=u)
    tv = TipoVehiculo.objects.get(codigo="camion")
    for i in range(vehiculos):
        TransportistaVehiculo.objects.create(transportista=c, placa=f"{name[:2].upper()}{i}-100", tipo_vehiculo=tv)
    return c, u


def _publicacion(n, estado=PublicacionCarga.ESTADO_ABIERTA):
    cli = Cliente.objects.create(nombre=CLIENTE_NOMBRE, telefono=CLIENTE_TEL)
    lead = Lead.objects.create(cliente=cli, tipo_servicio="mudanza",
                               distrito_origen="Miraflores", distrito_destino="Surco")
    svc = Servicio.objects.create(lead_origen=lead, cliente=cli, tipo_servicio="mudanza",
                                  distrito_origen="Miraflores", distrito_destino="Surco",
                                  direccion_origen="Calle Real 123 dpto 401",
                                  fecha_servicio=date.today() + timedelta(days=3),
                                  horario_servicio="08:00", precio=1500)
    return PublicacionCarga.objects.create(
        servicio=svc, codigo=f"P{n:02d}", texto_publicado="OFERTA-P", estado=estado,
        modo_precio=PublicacionCarga.PRECIO_REFERENCIAL, precio_publicado=1000,
    )


class PortalScopingTests(APITestCase):
    def setUp(self):
        self.c1, self.u1 = _carrier("uno")
        self.c2, self.u2 = _carrier("dos")
        self.pub = _publicacion(1)

    def test_no_transportista_no_entra(self):
        staff = User.objects.create_user("staff", password="x")
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/api/v2/portal/carrier/loads").status_code, 403)

    def test_cargas_no_filtran_datos_del_cliente(self):
        self.client.force_login(self.u1)
        r = self.client.get("/api/v2/portal/carrier/loads")
        self.assertEqual(r.status_code, 200)
        blob = json.dumps(r.data)
        self.assertNotIn(CLIENTE_NOMBRE, blob)
        self.assertNotIn(CLIENTE_TEL, blob)
        self.assertNotIn("Calle Real 123", blob)   # dirección exacta
        self.assertNotIn("1500", blob)             # precio de venta
        load = r.data["results"][0]
        self.assertEqual(load["targetPrice"], 1000.0)  # costo objetivo sí
        self.assertEqual(load["origin"], "Miraflores")

    def test_oferta_queda_acotada_al_transportista(self):
        self.client.force_login(self.u1)
        r = self.client.post(f"/api/v2/portal/carrier/loads/{self.pub.codigo}/offer",
                             {"amount": "950"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

        # c2 no ve la oferta de c1
        self.client.force_login(self.u2)
        r = self.client.get("/api/v2/portal/carrier/offers")
        self.assertEqual(r.data["results"], [])

        self.client.force_login(self.u1)
        r = self.client.get("/api/v2/portal/carrier/offers")
        self.assertEqual(len(r.data["results"]), 1)
        self.assertEqual(r.data["results"][0]["currentAmount"], 950.0)

    def test_precio_fijo_ignora_el_monto_enviado(self):
        self.pub.modo_precio = PublicacionCarga.PRECIO_FIJO
        self.pub.precio_publicado = 1000
        self.pub.save()
        self.client.force_login(self.u1)
        r = self.client.post(f"/api/v2/portal/carrier/loads/{self.pub.codigo}/offer",
                             {"amount": "500"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["myOfferAmount"], 1000.0)

    def test_negociacion_de_compra_scoped_y_sin_margen(self):
        adj.registrar_oferta(self.pub, monto=950, usuario=self.u1, transportista=self.c1)
        hilo = HiloNegociacion.objects.get(tipo="compra", transportista=self.c1)
        # TaxiCarga contrapropone
        neg.publicar_mensaje(hilo, emisor=MensajeNegociacion.EMISOR_TAXICARGA, propuesta_monto=880)

        self.client.force_login(self.u2)
        self.assertEqual(self.client.get(f"/api/v2/portal/carrier/negotiations/{hilo.id}/").status_code, 404)

        self.client.force_login(self.u1)
        r = self.client.get(f"/api/v2/portal/carrier/negotiations/{hilo.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("margin", r.data)
        self.assertNotIn("sale", json.dumps(r.data))
        prop = [m for m in r.data["messages"] if m["proposalFromTaxicarga"]][-1]

        r = self.client.post(f"/api/v2/portal/carrier/negotiations/messages/{prop['id']}/respond",
                             {"action": "accept"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["state"], "agreement")
        self.assertEqual(r.data["agreedAmount"], 880.0)

    def test_asignaciones_solo_las_propias(self):
        c, u = self.c1, self.u1
        oferta, _ = adj.registrar_oferta(self.pub, monto=950, usuario=u, transportista=c)
        adj.adjudicar_publicacion(self.pub, oferta, self.u1)

        self.client.force_login(self.u2)
        self.assertEqual(self.client.get("/api/v2/portal/carrier/assignments").data["results"], [])

        self.client.force_login(u)
        r = self.client.get("/api/v2/portal/carrier/assignments")
        self.assertEqual(len(r.data["results"]), 1)
        self.assertNotIn(CLIENTE_NOMBRE, json.dumps(r.data))
