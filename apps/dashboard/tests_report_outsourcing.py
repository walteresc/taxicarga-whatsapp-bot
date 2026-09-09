"""F8 · Reporte Propio vs Tercerizado + margen."""
import datetime as dt

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.campo.models import ProgramacionServicio
from apps.catalogo.models import TipoVehiculo
from apps.clientes.models import Cliente
from apps.dashboard import services_reportes as R
from apps.servicios.models import Servicio
from apps.tercerizacion.models import Transportista, TransportistaVehiculo

User = get_user_model()

HOY = dt.date.today()


def _servicio(precio, modalidad, n):
    cli = Cliente.objects.create(telefono=f"+51922{n:06d}", nombre=f"C{n}")
    return Servicio.objects.create(
        cliente=cli, precio=precio, modalidad_ejecucion=modalidad,
        fecha_confirmacion=HOY, fecha_servicio=HOY,
        distrito_origen="Lima", distrito_destino="Callao", horario_servicio="08:00",
    )


class OutsourcingReportTests(APITestCase):
    def setUp(self):
        # propio: 2 servicios, 1000 c/u
        _servicio(1000, "propio", 1)
        _servicio(1000, "propio", 2)
        # tercerizado: venta 1200, costo 800 (prog con transportista)
        svc = _servicio(1200, "tercerizado", 3)
        carrier = Transportista.objects.create(nombre="T")
        tv = TransportistaVehiculo.objects.create(
            transportista=carrier, placa="AAA-100",
            tipo_vehiculo=TipoVehiculo.objects.get(codigo="camion"),
        )
        ProgramacionServicio.objects.create(
            servicio=svc, vehiculo=None, transportista=carrier, transportista_vehiculo=tv,
            fecha=HOY, hora_inicio="08:00", monto=800,
        )

    def test_calculo(self):
        d = R.propio_vs_tercerizado(HOY - dt.timedelta(days=5), HOY + dt.timedelta(days=1), agrupacion="dia")
        by = {r["modality"]: r for r in d["resumen"]}
        self.assertEqual(by["propio"]["count"], 2)
        self.assertEqual(by["propio"]["revenue"], 2000.0)
        self.assertIsNone(by["propio"]["cost"])
        self.assertEqual(by["tercerizado"]["revenue"], 1200.0)
        self.assertEqual(by["tercerizado"]["cost"], 800.0)
        self.assertEqual(by["tercerizado"]["margin"], 400.0)
        self.assertEqual(d["serie"][0]["outsourcedMargin"], 400.0)
        self.assertEqual(d["serie"][0]["ownRevenue"], 2000.0)

    def test_endpoint_gatea_por_rol_de_margen(self):
        asesor = User.objects.create_user("ases_r", password="x")
        asesor.groups.add(Group.objects.get_or_create(name="Asesor de Ventas")[0])
        self.client.force_login(asesor)
        self.assertEqual(self.client.get("/api/v2/reports/outsourcing").status_code, 403)

        jefe = User.objects.create_user("ger_r", password="x")
        jefe.groups.add(Group.objects.get_or_create(name="Gerencia")[0])
        self.client.force_login(jefe)
        r = self.client.get("/api/v2/reports/outsourcing", {"period": "month"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("summary", r.data)
        self.assertIn("series", r.data)
