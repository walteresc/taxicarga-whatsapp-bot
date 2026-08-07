from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.clientes.models import Cliente
from apps.leads.models import Lead

from .commercial import crear_borrador, crear_revision, marcar_revision_enviada
from .models import RevisionCotizacion, SolicitudCotizacion


class CommercialQuoteTests(TestCase):
    def setUp(self):
        cliente = Cliente.objects.create(telefono="51900000002", nombre="Cotizacion etapa 1")
        self.lead = Lead.objects.create(cliente=cliente)
        self.asesor = get_user_model().objects.create_user(username="quote_stage1", password="x")
        self.solicitud = SolicitudCotizacion.objects.create(lead=self.lead, creada_por=self.asesor)

    def test_crea_borrador_con_snapshot_y_revision(self):
        cotizacion, revision = crear_borrador(
            self.solicitud,
            self.asesor,
            580,
            snapshot_servicio={"origen": "Surco", "destino": "Miraflores"},
        )
        self.assertTrue(cotizacion.codigo.startswith("COT-"))
        self.assertEqual(revision.numero, 1)
        self.assertEqual(revision.snapshot_servicio["origen"], "Surco")

    def test_rechaza_precio_bajo_margen(self):
        with self.assertRaises(ValidationError):
            crear_borrador(
                self.solicitud,
                self.asesor,
                500,
                costo_estimado=500,
                margen_minimo_porcentaje=20,
            )

    def test_revision_enviada_es_inmutable(self):
        cotizacion, revision = crear_borrador(self.solicitud, self.asesor, 580)
        marcar_revision_enviada(revision)
        revision.refresh_from_db()
        revision.precio_final = 600
        with self.assertRaises(ValidationError):
            revision.save()
        nueva = crear_revision(cotizacion, self.asesor, 600)
        self.assertEqual(nueva.numero, 2)
        self.assertEqual(RevisionCotizacion.objects.filter(cotizacion=cotizacion).count(), 2)
