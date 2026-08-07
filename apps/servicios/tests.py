from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from .models import (
    SERVICIO_CANCELADO,
    SERVICIO_FINALIZADO,
    SERVICIO_PENDIENTE,
    SERVICIO_PROGRAMADO,
    PagoReserva,
    Servicio,
)
from .services import crear_servicio_desde_lead


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_admin():
    user = User.objects.create_user(
        "admin", "admin@test.com", "pass123", is_staff=True, is_superuser=True
    )
    g, _ = Group.objects.get_or_create(name="Administrador")
    user.groups.add(g)
    return user


def create_supervisor():
    user = User.objects.create_user("supervisor", "sup@test.com", "pass123")
    g, _ = Group.objects.get_or_create(name="Supervisor")
    user.groups.add(g)
    return user


def create_lead(cliente=None):
    if cliente is None:
        cliente = Cliente.objects.create(nombre="Maria Lopez", telefono="999888777")
    return Lead.objects.create(
        cliente=cliente,
        tipo_servicio="Mudanza",
        distrito_origen="Surco",
        distrito_destino="Miraflores",
        direccion_origen="Av. Principal 123",
        direccion_destino="Calle Secundaria 456",
        piso_origen=3,
        piso_destino=5,
        ascensor_origen=True,
        ascensor_destino=False,
        acceso_origen="ascensor",
        acceso_destino="escaleras",
        lista_objetos="Caja de libros, mesa",
        objetos_pesados="Piano",
        incluye_personal_carga=True,
        requiere_desarmado=False,
        peso_carga_kg=200.50,
        volumen_carga_m3=3.5,
        fecha_servicio="2026-06-15",
        horario_servicio="10:00 AM",
        precio_cotizado=450.00,
        precio_final=420.00,
        nota_interna="Lead de prueba",
        etapa_conversacion="cotizacion",
        estado="cotizado",
    )


# ---------------------------------------------------------------------------
# Tests: crear_servicio_desde_lead (services.py)
# ---------------------------------------------------------------------------

class CrearServicioDesdeLeadTests(TestCase):
    def test_crear_servicio_desde_lead_cotizado(self):
        lead = create_lead()
        servicio, created = crear_servicio_desde_lead(lead)
        self.assertTrue(created)
        self.assertEqual(servicio.lead_origen, lead)
        self.assertEqual(servicio.cliente, lead.cliente)
        self.assertEqual(servicio.estado, SERVICIO_PENDIENTE)
        self.assertEqual(servicio.tipo_servicio, "Mudanza")
        self.assertEqual(servicio.direccion_origen, "Av. Principal 123")
        self.assertEqual(servicio.direccion_destino, "Calle Secundaria 456")
        self.assertEqual(servicio.lista_objetos, "Caja de libros, mesa")
        self.assertEqual(str(servicio.fecha_servicio), "2026-06-15")

    def test_evita_duplicado(self):
        lead = create_lead()
        s1, created1 = crear_servicio_desde_lead(lead)
        self.assertTrue(created1)
        s2, created2 = crear_servicio_desde_lead(lead)
        self.assertFalse(created2)
        self.assertEqual(s1.pk, s2.pk)

    def test_lead_tiene_cliente_telefono(self):
        cliente = Cliente.objects.create(nombre="Juan Perez", telefono="111222333")
        lead = create_lead(cliente=cliente)
        servicio, _ = crear_servicio_desde_lead(lead)
        self.assertEqual(servicio.cliente.telefono, "111222333")


# ---------------------------------------------------------------------------
# Tests: Views del módulo Reservas
# ---------------------------------------------------------------------------

class ReservasViewsTests(TestCase):
    def setUp(self):
        self.admin = create_admin()
        self.client.force_login(self.admin)

    # ---- Lista ----
    def test_lista_reservas_carga(self):
        resp = self.client.get(reverse("dashboard-servicios-list"))
        self.assertEqual(resp.status_code, 200)

    def test_lista_reservas_muestra_reservas(self):
        cliente = Cliente.objects.create(nombre="Test", telefono="999000111")
        s = Servicio.objects.create(cliente=cliente, precio=150.00)
        resp = self.client.get(reverse("dashboard-servicios-list"))
        self.assertContains(resp, s.codigo)

    def test_lista_reservas_filtro_q(self):
        c1 = Cliente.objects.create(nombre="Carlos", telefono="111111111")
        c2 = Cliente.objects.create(nombre="Pedro", telefono="222222222")
        Servicio.objects.create(cliente=c1)
        Servicio.objects.create(cliente=c2)
        resp = self.client.get(reverse("dashboard-servicios-list") + "?q=Carlos")
        self.assertContains(resp, "Carlos")
        self.assertNotContains(resp, "Pedro")

    def test_lista_reservas_filtro_estado(self):
        c = Cliente.objects.create(nombre="Test", telefono="333333333")
        Servicio.objects.create(cliente=c, estado=SERVICIO_FINALIZADO)
        Servicio.objects.create(cliente=c, estado=SERVICIO_PROGRAMADO)
        resp = self.client.get(
            reverse("dashboard-servicios-list") + "?estado=" + SERVICIO_FINALIZADO
        )
        self.assertContains(resp, SERVICIO_FINALIZADO)

    # ---- Detalle ----
    def test_detalle_reserva_carga(self):
        c = Cliente.objects.create(nombre="Test", telefono="444444444")
        s = Servicio.objects.create(cliente=c)
        resp = self.client.get(reverse("dashboard-servicios-detail", args=[s.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, s.codigo)

    def test_detalle_reserva_404(self):
        resp = self.client.get(reverse("dashboard-servicios-detail", args=[9999]))
        self.assertEqual(resp.status_code, 404)

    # ---- Crear ----
    def test_crear_reserva_get(self):
        resp = self.client.get(reverse("dashboard-servicios-create"))
        self.assertEqual(resp.status_code, 200)

    def test_crear_reserva_post_cliente_nuevo(self):
        data = {
            "cliente_nombre": "Nuevo Cliente",
            "cliente_telefono": "555555555",
            "direccion_origen": "Av. Origen 123",
            "piso_origen": "3",
            "acceso_origen_opciones": ["ascensor", "escaleras"],
            "direccion_destino": "Av. Destino 456",
            "piso_destino": "5",
            "acceso_destino_opciones": ["ascensor"],
            "detalle_carga": "Cajas varias",
            "tipo_embalaje": "sin_embalaje",
            "requisitos_especiales": ["ninguno"],
            "tipo_comprobante": "ninguno",
            "fecha_servicio": "2026-06-20",
            "horario_servicio": "09:00",
            "precio": "250.00",
        }
        resp = self.client.post(reverse("dashboard-servicios-create"), data)
        self.assertRedirects(resp, reverse("dashboard-servicios-list"))
        self.assertEqual(Servicio.objects.count(), 1)
        s = Servicio.objects.first()
        self.assertEqual(s.estado, SERVICIO_PROGRAMADO)
        self.assertEqual(s.cliente.nombre, "Nuevo Cliente")
        self.assertEqual(str(s.precio), "250.00")

    def test_crear_reserva_post_cliente_existente(self):
        cliente = Cliente.objects.create(
            nombre="Existente", telefono="666666666", documento="12345678"
        )
        data = {
            "cliente_id": cliente.pk,
            "cliente_nombre": "Existente",
            "cliente_telefono": "666666666",
            "direccion_origen": "Av. Origen 123",
            "piso_origen": "3",
            "acceso_origen_opciones": ["ascensor"],
            "direccion_destino": "Av. Destino 456",
            "piso_destino": "5",
            "acceso_destino_opciones": ["escaleras"],
            "detalle_carga": "Cajas",
            "tipo_embalaje": "sin_embalaje",
            "requisitos_especiales": ["ninguno"],
            "tipo_comprobante": "ninguno",
            "fecha_servicio": "2026-06-20",
            "horario_servicio": "09:00",
            "precio": "300.00",
        }
        resp = self.client.post(reverse("dashboard-servicios-create"), data)
        self.assertRedirects(resp, reverse("dashboard-servicios-list"))
        self.assertEqual(Cliente.objects.count(), 1)
        s = Servicio.objects.first()
        self.assertEqual(s.cliente.pk, cliente.pk)

    def test_crear_reserva_falta_nombre(self):
        data = {
            "cliente_nombre": "",
            "cliente_telefono": "777777777",
            "direccion_origen": "Av. Origen 123",
            "piso_origen": "3",
            "acceso_origen_opciones": ["ascensor"],
            "direccion_destino": "Av. Destino 456",
            "piso_destino": "5",
            "acceso_destino_opciones": ["escaleras"],
            "detalle_carga": "Cajas",
            "tipo_embalaje": "sin_embalaje",
            "requisitos_especiales": ["ninguno"],
            "tipo_comprobante": "ninguno",
            "fecha_servicio": "2026-06-20",
            "horario_servicio": "09:00",
            "precio": "300.00",
        }
        resp = self.client.post(reverse("dashboard-servicios-create"), data)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "requerido")

    def test_crear_reserva_desde_lead(self):
        lead = create_lead()
        resp = self.client.get(
            reverse("dashboard-servicios-create") + f"?lead={lead.pk}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Maria Lopez")

    # ---- Editar ----
    def test_editar_reserva_get(self):
        c = Cliente.objects.create(nombre="Edit", telefono="888888888")
        s = Servicio.objects.create(cliente=c)
        resp = self.client.get(reverse("dashboard-servicios-edit", args=[s.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_editar_reserva_post(self):
        c = Cliente.objects.create(nombre="Original", telefono="999999999")
        s = Servicio.objects.create(cliente=c, precio=100.00)
        data = {
            "cliente_id": c.pk,
            "cliente_nombre": "Original Editado",
            "cliente_telefono": "999999999",
            "direccion_origen": "Nuevo Origen 789",
            "piso_origen": "2",
            "acceso_origen_opciones": ["ascensor"],
            "direccion_destino": "Nuevo Destino 000",
            "piso_destino": "4",
            "acceso_destino_opciones": ["escaleras"],
            "detalle_carga": "Nueva carga",
            "tipo_embalaje": "basico",
            "requisitos_especiales": ["epp"],
            "tipo_comprobante": "boleta",
            "fecha_servicio": "2026-07-01",
            "horario_servicio": "14:00",
            "precio": "500.00",
        }
        resp = self.client.post(
            reverse("dashboard-servicios-edit", args=[s.pk]), data
        )
        self.assertRedirects(resp, reverse("dashboard-servicios-list"))
        s.refresh_from_db()
        self.assertEqual(str(s.precio), "500.00")

    # ---- Finalizar ----
    def test_finalizar_reserva(self):
        c = Cliente.objects.create(nombre="Fin", telefono="101010101")
        s = Servicio.objects.create(cliente=c, estado=SERVICIO_PROGRAMADO)
        resp = self.client.post(
            reverse("dashboard-servicios-finalizar", args=[s.pk])
        )
        self.assertRedirects(resp, reverse("dashboard-servicios-list"))
        s.refresh_from_db()
        self.assertEqual(s.estado, SERVICIO_FINALIZADO)
        self.assertIsNotNone(s.fecha_actualizacion_estado)

    # ---- Cancelar ----
    def test_cancelar_reserva_sin_motivo(self):
        c = Cliente.objects.create(nombre="Cancel", telefono="121212121")
        s = Servicio.objects.create(cliente=c, estado=SERVICIO_PROGRAMADO)
        resp = self.client.post(
            reverse("dashboard-servicios-cancelar", args=[s.pk]),
            {"motivo_cancelacion": ""},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Debe ingresar un motivo")
        s.refresh_from_db()
        self.assertNotEqual(s.estado, SERVICIO_CANCELADO)

    def test_cancelar_reserva_con_motivo(self):
        c = Cliente.objects.create(nombre="CancelOk", telefono="131313131")
        s = Servicio.objects.create(cliente=c, estado=SERVICIO_PROGRAMADO)
        resp = self.client.post(
            reverse("dashboard-servicios-cancelar", args=[s.pk]),
            {"motivo_cancelacion": "El cliente desistió"},
        )
        self.assertRedirects(resp, reverse("dashboard-servicios-list"))
        s.refresh_from_db()
        self.assertEqual(s.estado, SERVICIO_CANCELADO)
        self.assertEqual(s.motivo_cancelacion, "El cliente desistió")
        self.assertIsNotNone(s.fecha_actualizacion_estado)
        self.assertEqual(s.usuario_actualizacion, self.admin)

    # ---- Equipo sin asignar ----
    def test_crear_reserva_sin_equipo(self):
        c = Cliente.objects.create(nombre="SinEquipo", telefono="141414141")
        s = Servicio.objects.create(cliente=c, estado=SERVICIO_PROGRAMADO)
        self.assertEqual(s.estado, SERVICIO_PROGRAMADO)

    # ---- Validación de campos obligatorios ----
    def test_validar_nombre_telefono_obligatorios(self):
        data = {
            "cliente_nombre": "",
            "cliente_telefono": "",
            "direccion_origen": "Dir",
            "piso_origen": "1",
            "acceso_origen_opciones": ["ascensor"],
            "direccion_destino": "Dir",
            "piso_destino": "2",
            "acceso_destino_opciones": ["escaleras"],
            "detalle_carga": "Carga",
            "tipo_embalaje": "sin_embalaje",
            "requisitos_especiales": ["ninguno"],
            "tipo_comprobante": "ninguno",
            "fecha_servicio": "2026-06-20",
            "horario_servicio": "09:00",
            "precio": "100.00",
        }
        resp = self.client.post(reverse("dashboard-servicios-create"), data)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "requerido")


# ---------------------------------------------------------------------------
# Tests: permisos
# ---------------------------------------------------------------------------

class ReservasPermisosTests(TestCase):
    def test_supervisor_puede_crear(self):
        user = create_supervisor()
        self.client.force_login(user)
        resp = self.client.get(reverse("dashboard-servicios-create"))
        self.assertEqual(resp.status_code, 200)

    def test_usuario_anonimo_redirigido(self):
        self.client.logout()
        resp = self.client.get(reverse("dashboard-servicios-list"))
        self.assertNotEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# Tests: búsqueda de clientes AJAX
# ---------------------------------------------------------------------------

class BuscarClientesTests(TestCase):
    def setUp(self):
        self.admin = create_admin()
        self.client.force_login(self.admin)

    def test_buscar_clientes_por_nombre(self):
        Cliente.objects.create(nombre="Juan Perez", telefono="999999999")
        resp = self.client.get(
            reverse("dashboard-servicios-buscar-clientes") + "?q=Juan"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(len(data["results"]), 1)

    def test_buscar_clientes_por_telefono(self):
        Cliente.objects.create(nombre="Sin Nombre", telefono="555000555")
        resp = self.client.get(
            reverse("dashboard-servicios-buscar-clientes") + "?q=555000"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(len(data["results"]), 1)


# ---------------------------------------------------------------------------
# Tests: Pagos y amortizaciones
# ---------------------------------------------------------------------------

class PagosReservaTests(TestCase):
    def setUp(self):
        self.admin = create_admin()
        self.client.force_login(self.admin)
        self.cliente = Cliente.objects.create(nombre="Pago Test", telefono="999000111")
        self.servicio = Servicio.objects.create(
            cliente=self.cliente, precio=Decimal("500.00"),
            tipo_comprobante="ninguno",
        )

    # Helper para registrar un pago vía POST
    def _pagar(self, concepto, monto, metodo="yape", obs=""):
        return self.client.post(
            reverse("dashboard-servicios-pago", args=[self.servicio.pk]),
            {
                "concepto": concepto,
                "metodo_pago": metodo,
                "monto": str(monto),
                "fecha_pago": "2026-06-12T10:00",
                "observaciones": obs,
            },
            follow=True,
        )

    def test_adelanto(self):
        resp = self._pagar("adelanto", "200.00")
        self.assertEqual(PagoReserva.objects.count(), 1)
        p = PagoReserva.objects.first()
        self.assertEqual(p.concepto, "adelanto")
        self.assertEqual(p.monto, Decimal("200.00"))

    def test_pago_parcial(self):
        self._pagar("adelanto", "100.00")
        self._pagar("parcial", "150.00")
        self.assertEqual(PagoReserva.objects.count(), 2)

    def test_pago_final_en_detalle(self):
        self._pagar("adelanto", "300.00")
        self._pagar("final", "200.00")
        total = PagoReserva.objects.filter(
            servicio=self.servicio
        ).aggregate(total=Sum("monto"))["total"]
        self.assertEqual(total, Decimal("500.00"))

    def test_saldo_pendiente_correcto(self):
        self._pagar("adelanto", "150.00")
        from django.test import Client as TestClient
        c = TestClient()
        c.force_login(self.admin)
        resp = c.get(reverse("dashboard-servicios-detail", args=[self.servicio.pk]))
        self.assertContains(resp, "Total Pagado")
        self.assertContains(resp, "Saldo pendiente")

    def test_descuento_sin_observacion_rechazado(self):
        resp = self._pagar("descuento", "50.00", obs="")
        self.assertEqual(PagoReserva.objects.count(), 0)

    def test_finalizar_saldo_cero(self):
        self.servicio.precio = Decimal("0.00")
        self.servicio.save()
        resp = self.client.post(
            reverse("dashboard-servicios-finalizar", args=[self.servicio.pk]),
            follow=True,
        )
        self.servicio.refresh_from_db()
        self.assertEqual(self.servicio.estado, SERVICIO_FINALIZADO)

    def test_finalizar_con_pago_final(self):
        self._pagar("adelanto", "300.00")
        resp = self.client.post(
            reverse("dashboard-servicios-finalizar", args=[self.servicio.pk]),
            {
                "monto_final": "200.00",
                "metodo_final": "yape",
                "obs_final": "",
            },
            follow=True,
        )
        self.servicio.refresh_from_db()
        self.assertEqual(self.servicio.estado, SERVICIO_FINALIZADO)
        # Should have created the final payment
        final_pago = PagoReserva.objects.filter(
            servicio=self.servicio, concepto="final"
        ).first()
        self.assertIsNotNone(final_pago)
        self.assertEqual(final_pago.monto, Decimal("200.00"))

    def test_finalizar_monto_menor_exige_motivo(self):
        self._pagar("adelanto", "100.00")
        resp = self.client.post(
            reverse("dashboard-servicios-finalizar", args=[self.servicio.pk]),
            {
                "monto_final": "300.00",
                "metodo_final": "yape",
                "obs_final": "",
            },
            follow=True,
        )
        self.servicio.refresh_from_db()
        # Should NOT be finalized because monto < saldo without obs
        self.assertNotEqual(self.servicio.estado, SERVICIO_FINALIZADO)

    def test_finalizar_monto_menor_con_motivo(self):
        self._pagar("adelanto", "100.00")
        resp = self.client.post(
            reverse("dashboard-servicios-finalizar", args=[self.servicio.pk]),
            {
                "monto_final": "300.00",
                "metodo_final": "yape",
                "obs_final": "Cliente pagará el resto la próxima semana",
            },
            follow=True,
        )
        self.servicio.refresh_from_db()
        self.assertEqual(self.servicio.estado, SERVICIO_FINALIZADO)
        p = PagoReserva.objects.filter(
            servicio=self.servicio, concepto="final"
        ).first()
        self.assertIsNotNone(p)
        self.assertEqual(p.monto, Decimal("300.00"))

    def test_estado_pago_pagado(self):
        self._pagar("adelanto", "300.00")
        self._pagar("final", "200.00")
        self.servicio.refresh_from_db()
        self.assertEqual(self.servicio.estado_pago, "pagado")

    def test_estado_pago_amortizado(self):
        self._pagar("adelanto", "200.00")
        self.servicio.refresh_from_db()
        self.assertEqual(self.servicio.estado_pago, "amortizado")

    def test_estado_pago_pendiente(self):
        self.servicio.refresh_from_db()
        self.assertEqual(self.servicio.estado_pago, "pendiente")
