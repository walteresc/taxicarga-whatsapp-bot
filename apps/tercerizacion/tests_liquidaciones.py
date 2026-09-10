"""P1 · Liquidaciones de tercerización: se genera al adjudicar, Finanzas concilia
y marca liquidado, el transportista lo ve en 'Mis cobros'."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.catalogo.models import TipoVehiculo
from apps.clientes.models import Cliente, ClienteUsuario
from apps.leads.models import Lead
from apps.servicios.models import ConfiguracionOperaciones, Servicio
from apps.tercerizacion import adjudicacion as adj
from apps.tercerizacion import liquidaciones as liq_svc
from apps.tercerizacion.models import (
    Liquidacion, PublicacionCarga, Transportista, TransportistaVehiculo,
)

User = get_user_model()


def _mundo(n, *, precio=1000, costo=800):
    cli = Cliente.objects.create(nombre=f"C{n}", telefono=f"+51933{n:06d}")
    lead = Lead.objects.create(cliente=cli, tipo_servicio="carga", categoria_carga="cajas",
                               distrito_origen="Lima", distrito_destino="Callao")
    svc = Servicio.objects.create(
        lead_origen=lead, cliente=cli, distrito_origen="Lima", distrito_destino="Callao",
        fecha_servicio=date.today() + timedelta(days=2), horario_servicio="09:00",
        precio=precio, modalidad_ejecucion=Servicio.MODALIDAD_TERCERIZADO,
    )
    pub = PublicacionCarga.objects.create(
        servicio=svc, codigo=f"L{n:02d}", texto_publicado="OFERTA-L",
        estado=PublicacionCarga.ESTADO_ABIERTA, modo_precio=PublicacionCarga.PRECIO_ABIERTO,
    )
    carrier = Transportista.objects.create(nombre=f"T{n}")
    TransportistaVehiculo.objects.create(
        transportista=carrier, placa=f"LL{n}-100", tipo_vehiculo=TipoVehiculo.objects.get(codigo="camion"),
    )
    user = User.objects.create_user(f"l_op{n}", password="x")
    o, _ = adj.registrar_oferta(pub, monto=costo, usuario=user, transportista=carrier)
    return dict(cli=cli, svc=svc, pub=pub, carrier=carrier, oferta=o, user=user)


class GeneracionTests(APITestCase):
    def setUp(self):
        ConfiguracionOperaciones.objects.filter(pk=1).delete()

    def test_se_genera_al_adjudicar(self):
        m = _mundo(1, precio=1000, costo=800)
        adj.adjudicar_publicacion(m["pub"], m["oferta"], m["user"])
        liq = Liquidacion.objects.get(servicio=m["svc"])
        self.assertEqual(liq.precio_servicio, Decimal("1000"))
        self.assertEqual(liq.costo_transportista, Decimal("800"))
        self.assertEqual(liq.comision_monto, Decimal("200"))
        self.assertEqual(liq.neto, Decimal("800"))  # medio por_definir → le pagamos precio - comisión
        self.assertEqual(liq.estado, Liquidacion.ESTADO_PENDIENTE)

    def test_sin_comision_flag(self):
        m = _mundo(2, precio=1000, costo=800)
        m["svc"].sin_comision = True
        m["svc"].sin_comision_motivo = "Cliente estratégico"
        m["svc"].save()
        adj.adjudicar_publicacion(m["pub"], m["oferta"], m["user"])
        liq = Liquidacion.objects.get(servicio=m["svc"])
        self.assertTrue(liq.sin_comision)
        self.assertEqual(liq.comision_monto, Decimal("0"))
        self.assertEqual(liq.neto, Decimal("1000"))  # el transportista recibe todo

    def test_monto_minimo_comisionable(self):
        cfg = ConfiguracionOperaciones.get_solo()
        cfg.monto_minimo_comisionable = 1500
        cfg.save()
        m = _mundo(3, precio=1000, costo=800)
        adj.adjudicar_publicacion(m["pub"], m["oferta"], m["user"])
        liq = Liquidacion.objects.get(servicio=m["svc"])
        self.assertTrue(liq.sin_comision)
        self.assertEqual(liq.comision_monto, Decimal("0"))

    def test_neto_efectivo_transportista(self):
        m = _mundo(4, precio=1000, costo=800)
        adj.adjudicar_publicacion(m["pub"], m["oferta"], m["user"])
        liq = Liquidacion.objects.get(servicio=m["svc"])
        liq_svc.set_medio_cobro(liq, Liquidacion.MEDIO_EFECTIVO_TRANSPORTISTA)
        liq.refresh_from_db()
        self.assertEqual(liq.neto, Decimal("-200"))  # nos debe la comisión
        self.assertEqual(liq.direccion, "a_favor_plataforma")
        self.assertEqual(liq.estado, Liquidacion.ESTADO_CONCILIADA)

    def test_marcar_liquidada_exige_medio(self):
        from django.core.exceptions import ValidationError
        m = _mundo(5)
        adj.adjudicar_publicacion(m["pub"], m["oferta"], m["user"])
        liq = Liquidacion.objects.get(servicio=m["svc"])
        with self.assertRaises(ValidationError):
            liq_svc.marcar_liquidada(liq, usuario=m["user"])
        liq_svc.set_medio_cobro(liq, Liquidacion.MEDIO_PASARELA)
        liq_svc.marcar_liquidada(liq, usuario=m["user"], referencia="OP-123")
        liq.refresh_from_db()
        self.assertEqual(liq.estado, Liquidacion.ESTADO_PAGADA)
        self.assertEqual(liq.referencia_pago, "OP-123")
        self.assertIsNotNone(liq.fecha_liquidacion)

    def test_recalcular_respeta_pagada(self):
        m = _mundo(6, precio=1000, costo=800)
        adj.adjudicar_publicacion(m["pub"], m["oferta"], m["user"])
        liq = Liquidacion.objects.get(servicio=m["svc"])
        liq_svc.set_medio_cobro(liq, Liquidacion.MEDIO_PASARELA)
        liq_svc.marcar_liquidada(liq, usuario=m["user"])
        m["svc"].precio = 5000
        m["svc"].save()
        liq_svc.recalcular(liq)
        liq.refresh_from_db()
        self.assertEqual(liq.precio_servicio, Decimal("1000"))  # congelada


class FinanzasAPITests(APITestCase):
    def setUp(self):
        ConfiguracionOperaciones.objects.filter(pk=1).delete()
        for g in ("Finanzas", "Asesor de Ventas"):
            Group.objects.get_or_create(name=g)
        self.fin = User.objects.create_user("l_fin", password="x")
        self.fin.groups.add(Group.objects.get(name="Finanzas"))
        self.asesor = User.objects.create_user("l_ase", password="x")
        self.asesor.groups.add(Group.objects.get(name="Asesor de Ventas"))
        self.m = _mundo(10, precio=1200, costo=900)
        adj.adjudicar_publicacion(self.m["pub"], self.m["oferta"], self.m["user"])
        self.liq = Liquidacion.objects.get(servicio=self.m["svc"])

    def test_asesor_no_ve_liquidaciones(self):
        self.client.force_authenticate(self.asesor)
        self.assertEqual(self.client.get("/api/v2/settlements/").status_code, 403)

    def test_lista_y_resumen(self):
        self.client.force_authenticate(self.fin)
        r = self.client.get("/api/v2/settlements/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["results"]), 1)
        s = self.client.get("/api/v2/settlements/summary")
        self.assertEqual(s.data["toPayCarriers"], 900.0)
        self.assertEqual(s.data["pendingCommission"], 300.0)

    def test_flujo_conciliar_y_liquidar(self):
        self.client.force_authenticate(self.fin)
        r = self.client.patch(f"/api/v2/settlements/{self.liq.id}/",
                              {"collectionMethod": "pasarela"}, format="json")
        self.assertEqual(r.data["state"], "conciliada")
        r = self.client.post(f"/api/v2/settlements/{self.liq.id}/settle",
                             {"reference": "YAPE-99", "date": "2026-09-20"}, format="json")
        self.assertEqual(r.data["state"], "pagada")
        self.assertEqual(r.data["paymentRef"], "YAPE-99")

    def test_marcar_sin_comision_desde_finanzas(self):
        self.client.force_authenticate(self.fin)
        r = self.client.patch(f"/api/v2/settlements/{self.liq.id}/",
                              {"noCommission": True, "exemptionReason": "Cortesía"}, format="json")
        self.assertTrue(r.data["noCommission"])
        self.assertEqual(r.data["commission"], 0.0)
        self.assertEqual(r.data["net"], 1200.0)

    def test_void(self):
        self.client.force_authenticate(self.fin)
        r = self.client.post(f"/api/v2/settlements/{self.liq.id}/void", {"reason": "Servicio cancelado"}, format="json")
        self.assertEqual(r.data["state"], "anulada")


class PortalEarningsTests(APITestCase):
    def setUp(self):
        ConfiguracionOperaciones.objects.filter(pk=1).delete()
        Group.objects.get_or_create(name="Transportista")
        self.m = _mundo(20, precio=1000, costo=750)
        adj.adjudicar_publicacion(self.m["pub"], self.m["oferta"], self.m["user"])
        self.carrier = self.m["carrier"]
        self.cuser = User.objects.create_user("l_carrier", password="x")
        self.cuser.groups.add(Group.objects.get(name="Transportista"))
        self.carrier.usuario = self.cuser
        self.carrier.save()

    def test_mis_cobros(self):
        self.client.force_authenticate(self.cuser)
        r = self.client.get("/api/v2/portal/carrier/earnings")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["results"]), 1)
        self.assertEqual(r.data["results"][0]["amount"], 750.0)  # su neto, sin ver precio ni comisión
        self.assertNotIn("commission", r.data["results"][0])
        self.assertEqual(r.data["summary"]["pendingPayout"], 750.0)
