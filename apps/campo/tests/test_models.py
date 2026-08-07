from datetime import date, time

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.servicios.models import Servicio

from ..models import Ayudante, Conductor, EquipoDia, ProgramacionServicio, Vehiculo


class VehiculoModelTests(TestCase):
    def test_crear_vehiculo(self):
        v = Vehiculo.objects.create(
            placa="BHV-931",
            marca="Volvo",
            modelo="FH 460",
            capacidad_toneladas=5.0,
        )
        self.assertEqual(v.placa, "BHV-931")
        self.assertTrue(v.activo)
        self.assertEqual(str(v), "BHV-931 - Volvo FH 460")


class ConductorModelTests(TestCase):
    def test_crear_conductor(self):
        c = Conductor.objects.create(
            nombre="Juan Pérez",
            dni="12345678",
            telefono="51970000001",
        )
        self.assertEqual(c.nombre, "Juan Pérez")
        self.assertTrue(c.activo)
        self.assertEqual(str(c), "Juan Pérez (12345678)")


class AyudanteModelTests(TestCase):
    def test_crear_ayudante(self):
        a = Ayudante.objects.create(
            nombre="Pedro Gómez",
            dni="87654321",
            telefono="51970000002",
        )
        self.assertEqual(a.nombre, "Pedro Gómez")
        self.assertTrue(a.activo)
        self.assertEqual(str(a), "Pedro Gómez (87654321)")


class EquipoDiaModelTests(TestCase):
    def test_crear_equipo_dia(self):
        vehiculo = Vehiculo.objects.create(placa="BHV-931", marca="Volvo", modelo="FH 460", capacidad_toneladas=5)
        conductor = Conductor.objects.create(nombre="Juan Pérez", dni="12345678", telefono="51970000001")
        ayudante = Ayudante.objects.create(nombre="Pedro Gómez", dni="87654321", telefono="51970000002")

        equipo = EquipoDia.objects.create(
            fecha=date(2026, 6, 15),
            vehiculo=vehiculo,
            conductor=conductor,
        )
        equipo.ayudantes.add(ayudante)

        self.assertEqual(equipo.fecha, date(2026, 6, 15))
        self.assertEqual(equipo.vehiculo, vehiculo)
        self.assertEqual(equipo.conductor, conductor)
        self.assertIn(ayudante, equipo.ayudantes.all())
        self.assertTrue(equipo.activo)


class ProgramacionServicioModelTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nombre="Carlos Vega", telefono="51970000003")
        self.lead = Lead.objects.create(
            cliente=self.cliente,
            tipo_servicio="Mudanza",
            distrito_origen="Miraflores",
            distrito_destino="San Isidro",
            direccion_origen="Av. Larco 123",
            direccion_destino="Av. Javier Prado 456",
            lista_objetos="Sillón, mesa",
            horario_servicio="09:00",
            estado="cotizado",
        )
        self.user = User.objects.create_user("vendedor", password="pass123")
        self.servicio = Servicio.objects.create(
            lead_origen=self.lead,
            cliente=self.cliente,
            asesor=self.user,
            tipo_servicio="Mudanza",
            distrito_origen="Miraflores",
            distrito_destino="San Isidro",
            direccion_origen="Av. Larco 123",
            direccion_destino="Av. Javier Prado 456",
            lista_objetos="Sillón, mesa",
            horario_servicio="09:00",
            precio_final=500,
        )

    def test_crear_programacion_desde_servicio(self):
        vehiculo = Vehiculo.objects.create(placa="BHV-931", marca="Volvo", modelo="FH 460", capacidad_toneladas=5)
        conductor = Conductor.objects.create(nombre="Juan Pérez", dni="12345678", telefono="51970000001")
        ayudante = Ayudante.objects.create(nombre="Pedro Gómez", dni="87654321", telefono="51970000002")

        programacion = ProgramacionServicio.objects.create(
            servicio=self.servicio,
            vehiculo=vehiculo,
            conductor=conductor,
            fecha=date(2026, 6, 15),
            hora_inicio=time(8, 0),
            monto=500,
        )
        programacion.ayudantes.add(ayudante)

        self.assertEqual(programacion.servicio, self.servicio)
        self.assertEqual(programacion.vehiculo, vehiculo)
        self.assertEqual(programacion.conductor, conductor)
        self.assertIn(ayudante, programacion.ayudantes.all())
        self.assertEqual(programacion.estado_operativo, "programado")
        self.assertIn("SVC-0001", str(programacion))
        self.assertIn("2026-06-15", str(programacion))

    def test_programacion_mantiene_historial_al_cambiar_equipo(self):
        vehiculo_viejo = Vehiculo.objects.create(placa="BHV-931", marca="Volvo", modelo="FH 460", capacidad_toneladas=5)
        conductor_viejo = Conductor.objects.create(nombre="Juan Pérez", dni="12345678", telefono="51970000001")
        vehiculo_nuevo = Vehiculo.objects.create(placa="D7D-911", marca="Mercedes", modelo="Actros", capacidad_toneladas=8)
        conductor_nuevo = Conductor.objects.create(nombre="Luis Torres", dni="98765432", telefono="51970000004")

        programacion = ProgramacionServicio.objects.create(
            servicio=self.servicio,
            vehiculo=vehiculo_viejo,
            conductor=conductor_viejo,
            fecha=date(2026, 6, 15),
            hora_inicio=time(8, 0),
            monto=500,
        )

        programacion.vehiculo = vehiculo_nuevo
        programacion.conductor = conductor_nuevo
        programacion.save()
        programacion.refresh_from_db()

        self.assertEqual(programacion.vehiculo, vehiculo_nuevo)
        self.assertEqual(programacion.conductor, conductor_nuevo)


# ---------------------------------------------------------------------------
# CRUD view tests
# ---------------------------------------------------------------------------

class CrudBase(TestCase):
    """Base class for CRUD tests with an authenticated user."""

    def setUp(self):
        super().setUp()
        group, _ = Group.objects.get_or_create(name="Administrador")
        self.user = User.objects.create_user("testuser", password="pass123")
        self.user.groups.add(group)


class VehiculoCrudTests(CrudBase):
    def test_list_requiere_login(self):
        response = self.client.get(reverse("dashboard-campo-vehiculos"))
        self.assertEqual(response.status_code, 302)

    def test_list_muestra_vehiculos(self):
        self.client.force_login(self.user)
        Vehiculo.objects.create(placa="BHV-931", marca="Volvo", modelo="FH 460", capacidad_toneladas=5)
        response = self.client.get(reverse("dashboard-campo-vehiculos"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "BHV-931")
        self.assertContains(response, "Volvo")

    def test_crear_vehiculo_via_post(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("vehiculo_create"), {
            "placa": "D7D-911",
            "marca": "Mercedes",
            "modelo": "Actros",
            "capacidad_toneladas": 8.0,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Vehiculo.objects.filter(placa="D7D-911").exists())

    def test_editar_vehiculo(self):
        self.client.force_login(self.user)
        v = Vehiculo.objects.create(placa="BHV-931", marca="Volvo", modelo="FH 460", capacidad_toneladas=5)
        response = self.client.post(reverse("vehiculo_edit", args=[v.pk]), {
            "placa": "BHV-931",
            "marca": "Volvo",
            "modelo": "FH 500",
            "capacidad_toneladas": 5.0,
        })
        self.assertEqual(response.status_code, 302)
        v.refresh_from_db()
        self.assertEqual(v.modelo, "FH 500")

    def test_toggle_vehiculo(self):
        self.client.force_login(self.user)
        v = Vehiculo.objects.create(placa="BHV-931", marca="Volvo", modelo="FH 460", capacidad_toneladas=5)
        self.assertTrue(v.activo)
        self.client.get(reverse("vehiculo_toggle", args=[v.pk]))
        v.refresh_from_db()
        self.assertFalse(v.activo)


class ConductorCrudTests(CrudBase):
    def test_list_requiere_login(self):
        response = self.client.get(reverse("dashboard-campo-conductores"))
        self.assertEqual(response.status_code, 302)

    def test_crear_conductor_via_post(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("conductor_create"), {
            "nombre": "Juan Pérez",
            "dni": "12345678",
            "telefono": "51970000001",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Conductor.objects.filter(dni="12345678").exists())

    def test_editar_conductor(self):
        self.client.force_login(self.user)
        c = Conductor.objects.create(nombre="Juan", dni="12345678", telefono="51970000001")
        response = self.client.post(reverse("conductor_edit", args=[c.pk]), {
            "nombre": "Juan Pérez Modificado",
            "dni": "12345678",
            "telefono": "51970000001",
        })
        self.assertEqual(response.status_code, 302)
        c.refresh_from_db()
        self.assertEqual(c.nombre, "Juan Pérez Modificado")

    def test_toggle_conductor(self):
        self.client.force_login(self.user)
        c = Conductor.objects.create(nombre="Juan", dni="12345678", telefono="51970000001")
        self.client.get(reverse("conductor_toggle", args=[c.pk]))
        c.refresh_from_db()
        self.assertFalse(c.activo)


class AyudanteCrudTests(CrudBase):
    def test_list_requiere_login(self):
        response = self.client.get(reverse("dashboard-campo-ayudantes"))
        self.assertEqual(response.status_code, 302)

    def test_crear_ayudante_via_post(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("ayudante_create"), {
            "nombre": "Pedro Gómez",
            "dni": "87654321",
            "telefono": "51970000002",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Ayudante.objects.filter(dni="87654321").exists())

    def test_editar_ayudante(self):
        self.client.force_login(self.user)
        a = Ayudante.objects.create(nombre="Pedro", dni="87654321", telefono="51970000002")
        response = self.client.post(reverse("ayudante_edit", args=[a.pk]), {
            "nombre": "Pedro Modificado",
            "dni": "87654321",
            "telefono": "51970000002",
        })
        self.assertEqual(response.status_code, 302)
        a.refresh_from_db()
        self.assertEqual(a.nombre, "Pedro Modificado")

    def test_toggle_ayudante(self):
        self.client.force_login(self.user)
        a = Ayudante.objects.create(nombre="Pedro", dni="87654321", telefono="51970000002")
        self.client.get(reverse("ayudante_toggle", args=[a.pk]))
        a.refresh_from_db()
        self.assertFalse(a.activo)


class EquipoCrudTests(CrudBase):
    def setUp(self):
        super().setUp()
        self.vehiculo = Vehiculo.objects.create(placa="BHV-931", marca="Volvo", modelo="FH 460", capacidad_toneladas=5)
        self.conductor = Conductor.objects.create(nombre="Juan Pérez", dni="12345678", telefono="51970000001")
        self.ayudante = Ayudante.objects.create(nombre="Pedro Gómez", dni="87654321", telefono="51970000002")

    def test_list_equipos_requiere_login(self):
        response = self.client.get(reverse("dashboard-campo-equipos"))
        self.assertEqual(response.status_code, 302)

    def test_crear_equipo_via_post(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("equipo_create"), {
            "fecha": "2026-06-15",
            "vehiculo": self.vehiculo.pk,
            "conductor": self.conductor.pk,
            "ayudantes": [self.ayudante.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(EquipoDia.objects.filter(fecha=date(2026, 6, 15)).exists())

    def test_editar_equipo(self):
        self.client.force_login(self.user)
        equipo = EquipoDia.objects.create(fecha=date(2026, 6, 15), vehiculo=self.vehiculo, conductor=self.conductor)
        otro_vehiculo = Vehiculo.objects.create(placa="D7D-911", marca="Mercedes", modelo="Actros", capacidad_toneladas=8)
        response = self.client.post(reverse("equipo_edit", args=[equipo.pk]), {
            "fecha": "2026-06-15",
            "vehiculo": otro_vehiculo.pk,
            "conductor": self.conductor.pk,
        })
        self.assertEqual(response.status_code, 302)
        equipo.refresh_from_db()
        self.assertEqual(equipo.vehiculo.pk, otro_vehiculo.pk)

    def test_toggle_equipo(self):
        self.client.force_login(self.user)
        equipo = EquipoDia.objects.create(fecha=date(2026, 6, 15), vehiculo=self.vehiculo, conductor=self.conductor)
        self.client.get(reverse("equipo_toggle", args=[equipo.pk]))
        equipo.refresh_from_db()
        self.assertFalse(equipo.activo)
