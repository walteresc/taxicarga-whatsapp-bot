"""F6 · Portal del Cliente: wizard, precio, aceptar/negociar, scoping."""
import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.clientes.models import Cliente, ClienteUsuario
from apps.leads.models import Lead

User = get_user_model()


def _customer(name):
    u = User.objects.create_user(f"cust_{name}", password="x")
    u.groups.add(Group.objects.get_or_create(name="Cliente Portal")[0])
    c = Cliente.objects.create(nombre=f"Cliente {name}", telefono=f"+51944{abs(hash(name)) % 1000000:06d}",
                               correo=f"{name}@x.com")
    cu = ClienteUsuario.objects.create(usuario=u, cliente=c)
    return cu, u


_WIZARD = {
    "origin": {"district": "Miraflores", "address": "Av Larco 100", "floor": 3},
    "destination": {"district": "Surco", "address": "Av Primavera 500"},
    "cargo": {"category": "mudanza", "detail": "Depto 2 amb", "operators": 2},
    "date": "2026-10-01", "schedule": "09:00", "quoteMode": "por_carga",
}


class PortalClienteTests(APITestCase):
    def setUp(self):
        self.cu, self.u = _customer("uno")
        self.cu2, self.u2 = _customer("dos")

    def test_no_cliente_portal_no_entra(self):
        staff = User.objects.create_user("staff2", password="x")
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/api/v2/portal/customer/loads").status_code, 403)

    def test_wizard_crea_lead_y_devuelve_precio(self):
        self.client.force_login(self.u)
        r = self.client.post("/api/v2/portal/customer/loads", _WIZARD, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.data["code"].startswith("CRG-"))
        self.assertIn(r.data["price"]["mode"], ("auto", "advisor"))
        lead = Lead.objects.get(codigo=r.data["code"])
        self.assertEqual(lead.origen_carga, "portal_cliente")
        self.assertEqual(lead.cliente_id, self.cu.cliente_id)
        self.assertEqual(lead.ubicaciones.count(), 2)

    def test_cargas_scoped_al_cliente(self):
        self.client.force_login(self.u)
        self.client.post("/api/v2/portal/customer/loads", _WIZARD, format="json")
        self.client.force_login(self.u2)
        self.assertEqual(self.client.get("/api/v2/portal/customer/loads").data["results"], [])

    def test_aceptar_precio_deja_cotizacion_entregada(self):
        self.client.force_login(self.u)
        code = self.client.post("/api/v2/portal/customer/loads", _WIZARD, format="json").data["code"]
        lead = Lead.objects.get(codigo=code)
        # forzar precio automático para poder aceptar
        lead.cotizaciones.update(modo="automatico", confianza=60)
        r = self.client.post(f"/api/v2/portal/customer/loads/{code}/accept", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(lead.cotizaciones_comerciales.first().estado, "entregada")

    def test_negociar_abre_hilo_de_venta_y_el_cliente_lo_ve(self):
        self.client.force_login(self.u)
        code = self.client.post("/api/v2/portal/customer/loads", _WIZARD, format="json").data["code"]
        r = self.client.post(f"/api/v2/portal/customer/loads/{code}/negotiate",
                             {"counterOffer": "800", "note": "puedo pagar esto"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["negotiating"])

        r = self.client.get(f"/api/v2/portal/customer/loads/{code}/negotiation")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("margin", json.dumps(r.data))
        self.assertNotIn("cost", json.dumps(r.data))
        self.assertEqual(r.data["currentAmount"], 800.0)

        # el otro cliente no puede ver esta negociación
        self.client.force_login(self.u2)
        self.assertEqual(
            self.client.get(f"/api/v2/portal/customer/loads/{code}/negotiation").status_code, 404,
        )
