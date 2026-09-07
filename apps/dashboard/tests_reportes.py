"""Tests de las pantallas de Reportes (Fase: reportes de ventas).

Cubre: capa de cálculo (`services_reportes`) con base vacía y con datos, y las
vistas (acceso, permisos, que no revientan sin datos).
"""
import datetime as dt
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.cotizador.models import CotizacionComercial, ServicioHistorico
from apps.leads.models import Lead
from apps.servicios.models import PagoReserva, Servicio, SERVICIO_CANCELADO, SERVICIO_FINALIZADO
from apps.dashboard import services_reportes as R

User = get_user_model()


class ReportesServiceVacioTests(TestCase):
    """Con la base vacía todo devuelve ceros, nunca una excepción."""

    def test_todo_en_cero(self):
        desde, hasta = R.rango_por_defecto()
        v = R.ventas_por_periodo(desde, hasta)
        self.assertEqual(v["bruto"]["n"], 0)
        self.assertEqual(v["neto"]["facturado"], 0.0)
        self.assertEqual(v["serie"], [])

        e = R.embudo_conversion(desde, hasta)
        self.assertEqual((e["creados"], e["cotizados"], e["ganados"]), (0, 0, 0))
        self.assertEqual(e["tasa_cierre"], 0.0)

        t = R.ticket_local_interprovincial(desde, hasta)
        self.assertEqual(t["local"]["n"], 0)
        self.assertEqual(t["interprovincial"]["ticket_promedio"], 0.0)

        c = R.cobranzas(desde, hasta)
        self.assertEqual(c["facturado"], 0.0)
        self.assertEqual(c["pct_cobrado"], 0.0)

        b = R.benchmark_historico()
        self.assertEqual(b["total"], 0)
        self.assertEqual(b["rutas_interprovinciales"], [])
        self.assertEqual(b["precio"]["todos"]["mediana"], 0.0)

    def test_parse_rango_quincena_y_semana(self):
        d, h = R.parse_rango(None, None, "quincena", "2026-03-20")
        self.assertEqual((d, h), (dt.date(2026, 3, 16), dt.date(2026, 3, 31)))
        d, h = R.parse_rango(None, None, "quincena", "2026-03-10")
        self.assertEqual((d, h), (dt.date(2026, 3, 1), dt.date(2026, 3, 15)))
        d, h = R.parse_rango(None, None, "semana", "2026-03-18")  # miércoles
        self.assertEqual((d, h), (dt.date(2026, 3, 16), dt.date(2026, 3, 22)))
        d, h = R.parse_rango("2026-05-10", "2026-01-01", "rango")  # invertido -> ordena
        self.assertEqual((d, h), (dt.date(2026, 1, 1), dt.date(2026, 5, 10)))


class ReportesServiceConDatosTests(TestCase):
    def setUp(self):
        self.asesor = User.objects.create_user("ase1", password="x")
        self.cli = Cliente.objects.create(nombre="Cliente Uno", telefono="+51900000001")
        hoy = timezone.localdate()

        # Venta local finalizada, pagada a medias.
        self.s_local = Servicio.objects.create(
            cliente=self.cli, asesor=self.asesor, estado=SERVICIO_FINALIZADO,
            fecha_confirmacion=hoy, tipo_servicio="mudanza", es_interprovincial=False,
            distrito_origen="Miraflores", distrito_destino="Surco",
            precio=Decimal("600.00"), precio_final=Decimal("600.00"),
            fecha_servicio=hoy - dt.timedelta(days=2),
        )
        PagoReserva.objects.create(
            servicio=self.s_local, concepto="adelanto", metodo_pago="yape",
            monto=Decimal("200.00"), fecha_pago=timezone.now(),
        )
        # Venta interprovincial confirmada, sin pagos.
        self.s_inter = Servicio.objects.create(
            cliente=self.cli, asesor=self.asesor, estado="programado",
            fecha_confirmacion=hoy, tipo_servicio="carga", es_interprovincial=True,
            distrito_origen="Lima", distrito_destino="Piura",
            precio=Decimal("3000.00"), precio_final=Decimal("3000.00"),
            fecha_servicio=hoy + dt.timedelta(days=5),
        )
        # Venta cancelada -> cuenta en bruto, no en neto.
        Servicio.objects.create(
            cliente=self.cli, asesor=self.asesor, estado=SERVICIO_CANCELADO,
            fecha_confirmacion=hoy, tipo_servicio="mudanza",
            precio=Decimal("400.00"), precio_final=Decimal("400.00"),
        )

    def test_ventas_bruto_vs_neto(self):
        d, h = R.rango_por_defecto()
        v = R.ventas_por_periodo(d, h)
        self.assertEqual(v["bruto"]["n"], 3)
        self.assertEqual(v["bruto"]["facturado"], 4000.0)
        self.assertEqual(v["neto"]["n"], 2)
        self.assertEqual(v["neto"]["facturado"], 3600.0)
        self.assertEqual(v["cancelados"], 1)
        self.assertEqual(v["neto"]["ticket_promedio"], 1800.0)

    def test_ventas_filtro_por_tipo(self):
        d, h = R.rango_por_defecto()
        v = R.ventas_por_periodo(d, h, filtros={"tipo": "carga"})
        self.assertEqual(v["neto"]["n"], 1)
        self.assertEqual(v["neto"]["facturado"], 3000.0)

    def test_ticket_local_vs_interprovincial(self):
        d, h = R.rango_por_defecto()
        t = R.ticket_local_interprovincial(d, h)
        self.assertEqual(t["local"]["n"], 1)
        self.assertEqual(t["local"]["ticket_promedio"], 600.0)
        self.assertEqual(t["interprovincial"]["n"], 1)
        self.assertEqual(t["interprovincial"]["ticket_promedio"], 3000.0)
        self.assertEqual(t["interprovincial"]["pct_facturacion"], 83.3)

    def test_cobranzas(self):
        d, h = R.rango_por_defecto()
        c = R.cobranzas(d, h)
        self.assertEqual(c["facturado"], 3600.0)   # excluye cancelada
        self.assertEqual(c["cobrado"], 200.0)
        self.assertEqual(c["pendiente"], 3400.0)   # 400 local + 3000 inter
        self.assertEqual(c["por_estado_pago"]["amortizado"], 1)
        self.assertEqual(c["por_estado_pago"]["pendiente"], 1)
        self.assertEqual(len(c["top_pendientes"]), 2)
        self.assertEqual(c["metodos_pago"][0]["metodo_pago"], "yape")

    def test_embudo(self):
        hoy = timezone.localdate()
        l_ganado = Lead.objects.create(
            cliente=self.cli, estado=Lead.CERRADO, tipo_servicio="mudanza",
            fecha_cierre=timezone.now(),
        )
        Lead.objects.filter(pk=l_ganado.pk).update(
            fecha_creacion=timezone.now() - dt.timedelta(days=3)
        )
        l_perdido = Lead.objects.create(
            cliente=self.cli, estado=Lead.PERDIDO, tipo_servicio="carga",
            motivo_perdida=Lead.MOTIVO_PERDIDA_PRECIO, fecha_cierre=timezone.now(),
        )
        CotizacionComercial.objects.create(
            codigo="COT-T1", lead=l_ganado, origen="asesor", estado="aceptada",
        )
        d, h = hoy - dt.timedelta(days=30), hoy
        e = R.embudo_conversion(d, h)
        self.assertEqual(e["creados"], 2)
        self.assertEqual(e["cotizados"], 1)
        self.assertEqual(e["ganados"], 1)
        self.assertEqual(e["perdidos"], 1)
        self.assertEqual(e["win_rate"], 50.0)
        self.assertEqual(e["motivos_perdida"][0]["motivo_perdida"], Lead.MOTIVO_PERDIDA_PRECIO)

    def test_fecha_finalizacion_se_sella_sola(self):
        s = Servicio.objects.create(cliente=self.cli, estado="programado")
        self.assertIsNone(s.fecha_finalizacion)
        s.estado = SERVICIO_FINALIZADO
        s.save(update_fields=["estado"])
        s.refresh_from_db()
        self.assertEqual(s.fecha_finalizacion, timezone.localdate())


class ReportesBenchmarkDatosTests(TestCase):
    def test_split_y_rutas(self):
        for i in range(4):
            ServicioHistorico.objects.create(
                fecha=dt.date(2025, 6, 1), tipo_servicio="carga",
                distrito_origen="Lima", distrito_destino="Piura ciudad",
                precio_cotizado=Decimal("2000"), precio_final=Decimal("2000"),
                cerrado=True,
            )
        for i in range(5):
            ServicioHistorico.objects.create(
                fecha=dt.date(2025, 6, 1), tipo_servicio="mudanza",
                distrito_origen="Miraflores", distrito_destino="Surco",
                precio_cotizado=Decimal("300"), precio_final=Decimal("300"),
                cerrado=True,
            )
        b = R.benchmark_historico()
        self.assertEqual(b["total"], 9)
        self.assertEqual(b["ambito"]["interprovincial"]["n"], 4)
        self.assertEqual(b["ambito"]["local"]["n"], 5)
        rutas = {r["ruta"]: r for r in b["rutas_interprovinciales"]}
        self.assertIn("Lima ↔ Piura", rutas)
        self.assertEqual(rutas["Lima ↔ Piura"]["casos"], 4)
        self.assertEqual(rutas["Lima ↔ Piura"]["precio_tipico"], 2000.0)


