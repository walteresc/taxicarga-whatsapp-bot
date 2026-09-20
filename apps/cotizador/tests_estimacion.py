"""Estimación de peso/volumen por IA — servicio y endpoint público.
Provider siempre mockeado, nunca llama a una IA real."""
import json
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
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
        self.assertEqual(r, {"weightKg": 250, "volumeM3": 3.5, "confidence": "alta", "suggestedQuestion": None})

    def test_confianza_baja_sin_pregunta_devuelve_dict_con_nulls(self):
        # 0 es el centinela de "no se pudo estimar" (nunca `null`/Optional —
        # ver comentario en services_estimacion.py sobre por qué: DeepSeek
        # rechaza `anyOf` en modo estructurado).
        fake = FakeStructuredProvider(payload={"peso_kg": 0, "volumen_m3": 0, "confianza": "baja"})
        with patch("apps.cotizador.services_estimacion.build_provider", return_value=fake):
            r = estimar_carga_por_ia("cosas varias")
        self.assertEqual(r, {"weightKg": None, "volumeM3": None, "confidence": "baja", "suggestedQuestion": None})

    def test_confianza_baja_con_pregunta_sugerida(self):
        fake = FakeStructuredProvider(payload={
            "peso_kg": 0, "volumen_m3": 0, "confianza": "baja",
            "pregunta_sugerida": {"texto": "¿Cuántas cajas son aproximadamente?", "unidad": "cajas"},
        })
        with patch("apps.cotizador.services_estimacion.build_provider", return_value=fake):
            r = estimar_carga_por_ia("cosas varias")
        self.assertEqual(r["suggestedQuestion"], {"text": "¿Cuántas cajas son aproximadamente?", "unit": "cajas"})

    def test_pregunta_sugerida_vacia_no_cuenta_como_pregunta(self):
        """Si la IA estima algo, deja pregunta_sugerida con texto/unidad
        vacíos (el default del schema) — no debe aparecer como suggestedQuestion."""
        fake = FakeStructuredProvider(payload={"peso_kg": 100, "volumen_m3": 2, "confianza": "media"})
        with patch("apps.cotizador.services_estimacion.build_provider", return_value=fake):
            r = estimar_carga_por_ia("un ropero grande")
        self.assertIsNone(r["suggestedQuestion"])

    def test_texto_vacio_sin_fotos_no_llama_al_provider(self):
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

    def test_fotos_respetan_el_provider_pedido(self):
        """Con fotos, NO se fuerza ningún proveedor — DeepSeek también sabe
        leer imágenes (confirmado en vivo contra su API), así que se usa el
        que corresponda según ConfiguracionIA/provider_name, igual que sin fotos."""
        fake = FakeStructuredProvider(payload={"peso_kg": 80, "volumen_m3": 2, "confianza": "media"})
        foto = SimpleUploadedFile("carga.jpg", b"contenido-fake", content_type="image/jpeg")
        with patch("apps.cotizador.services_estimacion.build_provider", return_value=fake) as build:
            r = estimar_carga_por_ia("una caja", fotos=[foto], provider_name="deepseek")
        build.assert_called_once_with("extraction", provider_name="deepseek")
        self.assertEqual(r["confidence"], "media")

    def test_solo_fotos_sin_texto_igual_llama_al_provider(self):
        fake = FakeStructuredProvider(payload={"peso_kg": 40, "volumen_m3": 1, "confianza": "media"})
        foto = SimpleUploadedFile("carga.jpg", b"contenido-fake", content_type="image/jpeg")
        with patch("apps.cotizador.services_estimacion.build_provider", return_value=fake):
            r = estimar_carga_por_ia("", fotos=[foto])
        self.assertEqual(r["weightKg"], 40)


class EstimateCargoViewTests(APITestCase):
    """Sin login — lo usa el formulario de Detalles del cotizador de invitado."""

    def test_estima_y_devuelve_valores(self):
        fake = FakeStructuredProvider(payload={"peso_kg": 500, "volumen_m3": 2, "confianza": "media"})
        with patch("apps.cotizador.services_estimacion.build_provider", return_value=fake):
            r = self.client.post("/api/v2/guest/cargo/estimate", {"detail": "40 cajas de ropa"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data, {"weightKg": 500, "volumeM3": 2, "confidence": "media", "suggestedQuestion": None})

    def test_sin_detail_400(self):
        r = self.client.post("/api/v2/guest/cargo/estimate", {}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_estimacion_fallida_devuelve_nulls_no_error(self):
        fake = FakeStructuredProvider(error=RuntimeError("boom"))
        with patch("apps.cotizador.services_estimacion.build_provider", return_value=fake):
            r = self.client.post("/api/v2/guest/cargo/estimate", {"detail": "cosas"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, {"weightKg": None, "volumeM3": None, "confidence": None, "suggestedQuestion": None})

    def test_estima_con_fotos_multipart(self):
        fake = FakeStructuredProvider(payload={"peso_kg": 80, "volumen_m3": 2, "confianza": "media"})
        foto = SimpleUploadedFile("carga.jpg", b"contenido-fake", content_type="image/jpeg")
        with patch("apps.cotizador.services_estimacion.build_provider", return_value=fake):
            r = self.client.post(
                "/api/v2/guest/cargo/estimate",
                {"data": json.dumps({"detail": "un sofá"}), "photo0": foto},
                format="multipart",
            )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["confidence"], "media")

    def test_sin_detail_pero_con_fotos_no_es_400(self):
        fake = FakeStructuredProvider(payload={"peso_kg": 40, "volumen_m3": 1, "confianza": "media"})
        foto = SimpleUploadedFile("carga.jpg", b"contenido-fake", content_type="image/jpeg")
        with patch("apps.cotizador.services_estimacion.build_provider", return_value=fake):
            r = self.client.post(
                "/api/v2/guest/cargo/estimate",
                {"data": json.dumps({"detail": ""}), "photo0": foto},
                format="multipart",
            )
        self.assertEqual(r.status_code, 200, r.content)
