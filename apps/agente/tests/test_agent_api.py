from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.agente.models import ConversacionAgente, PropuestaAccion

from ._fake_llm import ProviderFake
from ._fixtures import Mundo

User = get_user_model()

_NO_THROTTLE = override_settings(
    REST_FRAMEWORK={
        "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
        "DEFAULT_THROTTLE_RATES": {"agent_ask": "1000/hour"},
    },
    AGENTE_PERFILES_HABILITADOS={"asesor", "cliente", "transportista"},
)


@_NO_THROTTLE
class AgentApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.m = Mundo()

    def setUp(self):
        from django.core.cache import caches
        caches["throttle"].clear()

    def _patch_provider(self, guion):
        import apps.agente.orquestador as orq
        self._orig = orq.build_provider
        orq.build_provider = lambda *_a, **_k: ProviderFake(guion)
        self.addCleanup(lambda: setattr(orq, "build_provider", self._orig))

    def test_ask_happy_path(self):
        self._patch_provider([
            {"calls": [("ver_carga", {"codigo": self.m.lead.codigo})]},
            {"texto": "Miraflores → Surco."},
        ])
        self.client.force_login(self.m.u_asesor)
        r = self.client.post("/api/v2/agent/ask", {"message": "contame de " + self.m.lead.codigo},
                             format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("Surco", r.data["reply"])
        self.assertTrue(r.data["conversationId"])

    def test_ask_403_sin_perfil(self):
        u = User.objects.create_user("nadie_api", password="x")
        self.client.force_login(u)
        r = self.client.post("/api/v2/agent/ask", {"message": "hola"}, format="json")
        self.assertEqual(r.status_code, 403)

    @override_settings(AGENTE_PERFILES_HABILITADOS=set())
    def test_ask_403_si_deshabilitado_para_el_perfil(self):
        self.client.force_login(self.m.u_asesor)
        r = self.client.post("/api/v2/agent/ask", {"message": "hola"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_status(self):
        self.client.force_login(self.m.u_asesor)
        r = self.client.get("/api/v2/agent/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["enabled"])
        self.assertEqual(r.data["profile"], "asesor")

    @override_settings(AGENTE_PERFILES_HABILITADOS={"cliente"})
    def test_status_deshabilitado(self):
        self.client.force_login(self.m.u_asesor)
        r = self.client.get("/api/v2/agent/status")
        self.assertFalse(r.data["enabled"])

    def test_ask_401_sin_sesion(self):
        r = self.client.post("/api/v2/agent/ask", {"message": "hola"}, format="json")
        self.assertIn(r.status_code, (401, 403))

    def test_propuesta_flujo_apply(self):
        self._patch_provider([
            {"calls": [("crear_reserva", {"codigo": self.m.lead.codigo})]},
            {"texto": "Propuse crear la reserva."},
        ])
        self.client.force_login(self.m.u_asesor)
        r = self.client.post("/api/v2/agent/ask", {"message": "creá la reserva de " + self.m.lead.codigo},
                             format="json")
        pid = r.data["proposals"][0]["id"]

        r = self.client.get("/api/v2/agent/proposals/", {"estado": "pendiente"})
        self.assertEqual([p["id"] for p in r.data["results"]], [pid])

        r = self.client.post(f"/api/v2/agent/proposals/{pid}/apply", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["ok"])
        PropuestaAccion.objects.get(pk=pid, estado="aplicada")

    def test_conversation_scoped_al_usuario(self):
        self._patch_provider([{"texto": "hola"}])
        self.client.force_login(self.m.u_asesor)
        cid = self.client.post("/api/v2/agent/ask", {"message": "hola"}, format="json").data["conversationId"]
        # otro usuario no la ve
        self.client.force_login(self.m.u_gerente)
        r = self.client.get(f"/api/v2/agent/conversations/{cid}/")
        self.assertEqual(r.status_code, 404)
