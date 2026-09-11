"""Clasificación local/nacional por distancia (Fase 'Direcciones', 2026-09)."""
from django.test import TestCase

from apps.clientes.models import Cliente
from apps.servicios.models import ConfiguracionOperaciones

from .geo import clasificar_y_marcar_ambito, haversine_km
from .models import Lead


class HaversineTests(TestCase):
    def test_mismo_punto_distancia_cero(self):
        self.assertEqual(haversine_km(-12.05, -77.04, -12.05, -77.04), 0)

    def test_lima_piura_aprox_900km(self):
        d = haversine_km(-12.0464, -77.0428, -5.1945, -80.6328)
        self.assertTrue(800 < d < 1000, d)


class ClasificarAmbitoTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(telefono="+51900000111", nombre="Test")

    def _lead(self, **kwargs):
        return Lead.objects.create(cliente=self.cliente, **kwargs)

    def test_sin_coordenadas_no_hace_nada(self):
        lead = self._lead(distrito_origen="Miraflores", distrito_destino="Surco")
        cambiado = clasificar_y_marcar_ambito(lead)
        self.assertFalse(cambiado)
        self.assertFalse(lead.es_interprovincial)

    def test_destino_lejano_marca_interprovincial(self):
        lead = self._lead(
            lat_origen=-12.0464, lng_origen=-77.0428,   # Lima Cercado
            lat_destino=-5.1945, lng_destino=-80.6328,  # Piura
        )
        cambiado = clasificar_y_marcar_ambito(lead)
        self.assertTrue(cambiado)
        lead.refresh_from_db()
        self.assertTrue(lead.es_interprovincial)

    def test_ambos_puntos_cercanos_no_marca(self):
        lead = self._lead(
            lat_origen=-12.1211, lng_origen=-77.0297,   # Miraflores
            lat_destino=-12.1350, lng_destino=-76.9900,  # Surco
        )
        cambiado = clasificar_y_marcar_ambito(lead)
        self.assertFalse(cambiado)
        self.assertFalse(lead.es_interprovincial)

    def test_radio_configurable(self):
        config = ConfiguracionOperaciones.get_solo()
        config.radio_local_km = 5
        config.save(update_fields=["radio_local_km"])
        # Miraflores-Surco (~9 km) queda fuera de un radio de 5 km.
        lead = self._lead(
            lat_origen=-12.1211, lng_origen=-77.0297,
            lat_destino=-12.1350, lng_destino=-76.9900,
        )
        clasificar_y_marcar_ambito(lead)
        lead.refresh_from_db()
        self.assertTrue(lead.es_interprovincial)

    def test_ya_marcado_correctamente_no_reguarda(self):
        lead = self._lead(
            lat_origen=-12.0464, lng_origen=-77.0428,
            lat_destino=-5.1945, lng_destino=-80.6328,
            es_interprovincial=True,
        )
        cambiado = clasificar_y_marcar_ambito(lead)
        self.assertFalse(cambiado)


class FallbackSinCoordenadasTests(TestCase):
    """Respaldo por texto cuando no hay lat/lng (dirección tipeada a mano)."""

    def setUp(self):
        self.cliente = Cliente.objects.create(telefono="+51900000222", nombre="Test")

    def _lead(self, **kwargs):
        return Lead.objects.create(cliente=self.cliente, **kwargs)

    def test_distrito_destino_fuera_de_lima_marca_interprovincial(self):
        lead = self._lead(distrito_origen="Miraflores", distrito_destino="Arequipa")
        cambiado = clasificar_y_marcar_ambito(lead)
        self.assertTrue(cambiado)
        lead.refresh_from_db()
        self.assertTrue(lead.es_interprovincial)

    def test_ambos_distritos_de_lima_no_marca(self):
        lead = self._lead(distrito_origen="Miraflores", distrito_destino="San Isidro")
        cambiado = clasificar_y_marcar_ambito(lead)
        self.assertFalse(cambiado)
        self.assertFalse(lead.es_interprovincial)

    def test_no_revierte_una_marca_existente(self):
        # Si ya estaba marcado (p. ej. por el bot) y el texto no matchea nada,
        # el respaldo nunca lo pone en False.
        lead = self._lead(distrito_origen="Miraflores", distrito_destino="San Isidro",
                           es_interprovincial=True)
        cambiado = clasificar_y_marcar_ambito(lead)
        self.assertFalse(cambiado)
        self.assertTrue(lead.es_interprovincial)
