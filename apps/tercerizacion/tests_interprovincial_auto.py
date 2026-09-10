"""Derivación automática de cargas interprovinciales a transportistas (G3).

Con el flag `ConfiguracionOperaciones.derivar_interprovincial_auto` activo, un
lead interprovincial con datos completos se publica solo a los transportistas
(precio abierto) y NO entra a la cola de revisión del asesor.
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.clientes.models import Cliente
from apps.cotizador.pipeline import sync_review_request
from apps.leads.models import Lead
from apps.leads.route import replace_lead_route
from apps.servicios.models import ConfiguracionOperaciones, Servicio
from apps.tercerizacion.models import HiloNegociacion, PublicacionCarga
from apps.tercerizacion.services import derivar_interprovincial_si_corresponde

User = get_user_model()


def _lead_interprovincial_completo(**kw):
    n = _lead_interprovincial_completo
    n.i = getattr(n, "i", 0) + 1
    cli = Cliente.objects.create(nombre="Cliente IP", telefono="+5190010%04d" % n.i)
    base = dict(
        cliente=cli, tipo_servicio="carga",
        distrito_origen="Piura", distrito_destino="Tumbes",
        direccion_origen="Av. Grau 100", direccion_destino="Jr. Lima 250",
        fecha_servicio=date.today() + timedelta(days=5), horario_servicio="09:00",
        estado=Lead.NUEVO, es_interprovincial=True, requiere_asesor=True,
    )
    base.update(kw)
    lead = Lead.objects.create(**base)
    replace_lead_route(lead, [
        {"tipo": "origen", "distrito": "Piura", "direccion": "Av. Grau 100"},
        {"tipo": "destino", "distrito": "Tumbes", "direccion": "Jr. Lima 250"},
    ])
    return lead


class DerivacionInterprovincialAutoTests(APITestCase):
    def setUp(self):
        ConfiguracionOperaciones.objects.filter(pk=1).delete()

    def _activar(self, valor=True):
        cfg = ConfiguracionOperaciones.get_solo()
        cfg.derivar_interprovincial_auto = valor
        cfg.save(update_fields=["derivar_interprovincial_auto", "actualizado_en"])

    def test_flag_apagado_no_hace_nada(self):
        lead = _lead_interprovincial_completo()
        self.assertIsNone(derivar_interprovincial_si_corresponde(lead))
        self.assertFalse(PublicacionCarga.objects.filter(servicio__lead_origen=lead).exists())

    def test_flag_encendido_publica_a_transportistas(self):
        self._activar()
        lead = _lead_interprovincial_completo()
        pub = derivar_interprovincial_si_corresponde(lead)
        self.assertIsNotNone(pub)
        self.assertEqual(pub.estado, PublicacionCarga.ESTADO_ABIERTA)
        self.assertEqual(pub.modo_precio, PublicacionCarga.PRECIO_ABIERTO)
        self.assertEqual(pub.servicio.modalidad_ejecucion, Servicio.MODALIDAD_TERCERIZADO)
        self.assertEqual(pub.servicio.lead_origen_id, lead.id)
        self.assertTrue(HiloNegociacion.objects.filter(
            lead=lead, tipo=HiloNegociacion.TIPO_COMPRA,
        ).exists())

    def test_no_es_interprovincial_se_ignora(self):
        self._activar()
        lead = _lead_interprovincial_completo(es_interprovincial=False)
        self.assertIsNone(derivar_interprovincial_si_corresponde(lead))

    def test_datos_incompletos_espera(self):
        self._activar()
        lead = _lead_interprovincial_completo(horario_servicio="")
        self.assertIsNone(derivar_interprovincial_si_corresponde(lead))
        self.assertFalse(PublicacionCarga.objects.filter(servicio__lead_origen=lead).exists())

    def test_idempotente(self):
        self._activar()
        lead = _lead_interprovincial_completo()
        pub1 = derivar_interprovincial_si_corresponde(lead)
        pub2 = derivar_interprovincial_si_corresponde(lead)
        self.assertEqual(pub1.id, pub2.id)
        self.assertEqual(PublicacionCarga.objects.filter(servicio__lead_origen=lead).count(), 1)

    def test_sync_review_request_no_encola_si_deriva(self):
        self._activar()
        lead = _lead_interprovincial_completo()
        sol = sync_review_request(lead)
        self.assertIsNone(sol)
        self.assertTrue(PublicacionCarga.objects.filter(servicio__lead_origen=lead).exists())

    def test_sync_review_request_encola_si_flag_apagado(self):
        lead = _lead_interprovincial_completo()
        sol = sync_review_request(lead)
        self.assertIsNotNone(sol)


class OutsourcingSettingsAPITests(APITestCase):
    def setUp(self):
        ConfiguracionOperaciones.objects.filter(pk=1).delete()
        Group.objects.get_or_create(name="Despacho")
        Group.objects.get_or_create(name="Asesor de Ventas")
        self.despacho = User.objects.create_user("g_despacho", password="x")
        self.despacho.groups.add(Group.objects.get(name="Despacho"))
        self.asesor = User.objects.create_user("g_asesor", password="x")
        self.asesor.groups.add(Group.objects.get(name="Asesor de Ventas"))

    def test_get_default_false(self):
        self.client.force_authenticate(self.despacho)
        r = self.client.get("/api/v2/outsourcing/settings")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["autoDeriveInterprovincial"])

    def test_patch_activa(self):
        self.client.force_authenticate(self.despacho)
        r = self.client.patch("/api/v2/outsourcing/settings",
                              {"autoDeriveInterprovincial": True}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["autoDeriveInterprovincial"])
        self.assertTrue(ConfiguracionOperaciones.get_solo().derivar_interprovincial_auto)

    def test_asesor_no_puede(self):
        self.client.force_authenticate(self.asesor)
        r = self.client.patch("/api/v2/outsourcing/settings",
                              {"autoDeriveInterprovincial": True}, format="json")
        self.assertEqual(r.status_code, 403)
