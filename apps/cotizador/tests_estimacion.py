"""Estimación de peso/volumen por IA — servicio y endpoint público.
Provider siempre mockeado, nunca llama a una IA real."""
from unittest.mock import patch

from rest_framework.test import APITestCase

from apps.ia.providers import AIProviderError, AIResult
from apps.cotizador.services_estimacion import estimar_carga_por_ia


class FakeStructuredProvider:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def generate_structured(self, messages, *, schema_model, purpose="unknown"):
        if self.error:
            raise self.error
        parsed = schema_model.model_validate(self.payload)
        return AIResult(text=parsed.model_dump_json(), provider="openai", model="gpt-4.1-mini", latency_ms=10)


class EstimarCargaPorIaTests(APITestCase):
    def test_estimacion_confiable_devuelve_valores(self):
        fake = FakeStructuredProvider(payload={"peso_kg": 250, "volumen_m3": 3.5, "confianza": "alta"})
        with patch("apps.cotizador.services_estimacion.build_provider", return_value=fake):
            r = estimar_carga_por_ia("un juego de sala")
        self.assertEqual(r, {"weightKg": 250, "volumeM3": 3.5, "confidence": "alta"})

    def test_confianza_baja_sin_valores_devuelve_none(self):
        fake = FakeStructuredProvider(payload={"peso_kg": None, "volumen_m3": None, "confianza": "baja"})
        with patch("apps.cotizador.services_estimacion.build_provider", return_value=fake):
            r = estimar_carga_por_ia("cosas varias")
        self.assertIsNone(r)

    def test_texto_vacio_no_llama_al_provider(self):
        with patch("apps.cotizador.services_estimacion.build_provider") as provider:
            r = estimar_carga_por_ia("   ")
        provider.assert_not_called()
        self.assertIsNone(r)

    def test_error_del_provider_no_lanza(self):
        fake = FakeStructuredProvider(error=AIProviderError("sin credencial"))
        with patch("apps.cotizador.services_estimacion.build_provider", return_value=fake):
            r = estimar_carga_por_ia("40 cajas")
        self.assertIsNone(r)

    def test_json_invalido_no_lanza(self):
        class BadProvider:
            def generate_structured(self, messages, *, schema_model, purpose="unknown"):
                return AIResult(text="no es json", provider="openai", model="x", latency_ms=1)
        with patch("apps.cotizador.services_estimacion.build_provider", return_value=BadProvider()):
            r = estimar_carga_por_ia("una moto usada")
        self.assertIsNone(r)


class EstimateCargoViewTests(APITestCase):
    """Sin login — lo usa el formulario de Detalles del cotizador de invitado."""

    def test_estima_y_devuelve_valores(self):
        fake = FakeStructuredProvider(payload={"peso_kg": 500, "volumen_m3": 2, "confianza": "media"})
        with patch("apps.cotizador.services_estimacion.build_provider", return_value=fake):
            r = self.client.post("/api/v2/guest/cargo/estimate", {"detail": "40 cajas de ropa"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data, {"weightKg": 500, "volumeM3": 2, "confidence": "media"})

    def test_sin_detail_400(self):
        r = self.client.post("/api/v2/guest/cargo/estimate", {}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_estimacion_fallida_devuelve_nulls_no_error(self):
        fake = FakeStructuredProvider(error=RuntimeError("boom"))
        with patch("apps.cotizador.services_estimacion.build_provider", return_value=fake):
            r = self.client.post("/api/v2/guest/cargo/estimate", {"detail": "cosas"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, {"weightKg": None, "volumeM3": None, "confidence": None})
