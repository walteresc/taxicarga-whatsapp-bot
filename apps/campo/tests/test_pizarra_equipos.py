import json
from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from apps.campo.models import Ayudante, Conductor, EquipoDia, Vehiculo


class PizarraEquiposTests(TestCase):
    def setUp(self):
        admin_group, _ = Group.objects.get_or_create(name="Administrador")
        self.user = User.objects.create_user("pizarra_admin", password="Admin123*")
        self.user.groups.add(admin_group)
        self.client.login(username="pizarra_admin", password="Admin123*")

        self.vehiculo = Vehiculo.objects.create(
            placa="PIZ-101",
            marca="JAC",
            modelo="X200",
            capacidad_toneladas=2,
            activo=True,
        )
        self.conductor = Conductor.objects.create(
            nombre="Conductor Pizarra",
            dni="70000001",
            telefono="900000001",
            activo=True,
        )
        self.conductor_ayudante = Conductor.objects.create(
            nombre="Conductor Ayudante",
            dni="70000002",
            telefono="900000002",
            activo=True,
        )
        self.ayudante = Ayudante.objects.create(
            nombre="Ayudante Pizarra",
            dni="80000001",
            telefono="900000003",
            activo=True,
        )
        self.source_date = date.today() - timedelta(days=1)
        self.target_date = date.today() + timedelta(days=1)
        self.source = EquipoDia.objects.create(
            fecha=self.source_date,
            vehiculo=self.vehiculo,
            conductor=self.conductor,
        )
        self.source.ayudantes.add(self.ayudante)
        self.source.conductores_ayudantes.add(self.conductor_ayudante)

        self.vehiculo_2 = Vehiculo.objects.create(
            placa="PIZ-202",
            marca="Foton",
            modelo="Aumark",
            capacidad_toneladas=3,
            activo=True,
        )
        self.conductor_2 = Conductor.objects.create(
            nombre="Conductor Dos",
            dni="70000003",
            telefono="900000004",
            activo=True,
        )

    def post_equipo(self, payload):
        return self.client.post(
            reverse("pizarra-equipo-crear"),
            json.dumps(payload),
            content_type="application/json",
        )

    def test_pizarra_expone_selector_de_equipos_formados(self):
        response = self.client.get(reverse("dashboard-pizarra"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Equipos formados")
        self.assertContains(response, "Crear Equipo")
        self.assertContains(response, "pizarra-equipos-formados")
        self.assertEqual(response.context["equipos_formados_json"][0]["placa"], "PIZ-101")

    def test_clonar_equipo_formado_conserva_personal(self):
        response = self.post_equipo({
            "fecha": self.target_date.isoformat(),
            "equipo_origen_id": self.source.id,
        })

        self.assertEqual(response.status_code, 200)
        equipo = EquipoDia.objects.get(fecha=self.target_date)
        self.assertEqual(equipo.vehiculo, self.vehiculo)
        self.assertEqual(equipo.conductor, self.conductor)
        self.assertEqual(list(equipo.ayudantes.all()), [self.ayudante])
        self.assertEqual(
            list(equipo.conductores_ayudantes.all()),
            [self.conductor_ayudante],
        )

    def test_creacion_manual_admite_conductor_como_ayudante(self):
        response = self.post_equipo({
            "fecha": self.target_date.isoformat(),
            "vehiculo_id": self.vehiculo.id,
            "conductor_id": self.conductor.id,
            "ayudante_ids": [self.ayudante.id],
            "conductor_ayudante_ids": [self.conductor_ayudante.id],
        })

        self.assertEqual(response.status_code, 200)
        equipo = EquipoDia.objects.get(fecha=self.target_date)
        self.assertTrue(equipo.ayudantes.filter(pk=self.ayudante.id).exists())
        self.assertTrue(
            equipo.conductores_ayudantes.filter(pk=self.conductor_ayudante.id).exists()
        )

    def test_clonar_combinacion_duplicada_devuelve_409(self):
        EquipoDia.objects.create(
            fecha=self.target_date,
            vehiculo=self.vehiculo,
            conductor=self.conductor,
        )

        response = self.post_equipo({
            "fecha": self.target_date.isoformat(),
            "equipo_origen_id": self.source.id,
        })

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            EquipoDia.objects.filter(
                fecha=self.target_date,
                vehiculo=self.vehiculo,
                conductor=self.conductor,
            ).count(),
            1,
        )

    def test_editar_equipo_actualiza_composicion(self):
        response = self.client.post(
            reverse("equipo-editar-ajax", args=[self.source.id]),
            json.dumps({
                "vehiculo_id": self.vehiculo_2.id,
                "conductor_id": self.conductor_2.id,
                "ayudante_ids": [],
                "conductor_ayudante_ids": [self.conductor.id],
                "observaciones": "Actualizado desde modal",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.source.refresh_from_db()
        self.assertEqual(self.source.vehiculo, self.vehiculo_2)
        self.assertEqual(self.source.conductor, self.conductor_2)
        self.assertEqual(self.source.observaciones, "Actualizado desde modal")
        self.assertFalse(self.source.ayudantes.exists())
        self.assertEqual(
            list(self.source.conductores_ayudantes.all()),
            [self.conductor],
        )

    def test_editar_equipo_bloquea_combinacion_duplicada(self):
        existing = EquipoDia.objects.create(
            fecha=self.source_date,
            vehiculo=self.vehiculo_2,
            conductor=self.conductor_2,
        )

        response = self.client.post(
            reverse("equipo-editar-ajax", args=[self.source.id]),
            json.dumps({
                "vehiculo_id": self.vehiculo_2.id,
                "conductor_id": self.conductor_2.id,
                "ayudante_ids": [],
                "conductor_ayudante_ids": [],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.source.refresh_from_db()
        self.assertEqual(self.source.vehiculo, self.vehiculo)
        self.assertEqual(existing.vehiculo, self.vehiculo_2)

    def test_vistas_muestran_edicion_de_equipo(self):
        pizarra = self.client.get(reverse("dashboard-pizarra"))
        equipos = self.client.get(
            reverse("dashboard-campo-equipos"),
            {"fecha": self.source_date.strftime("%Y%m%d")},
        )

        self.assertContains(pizarra, "btn-edit-equipo")
        self.assertContains(pizarra, "pizarra-equipos-edicion")
        self.assertContains(equipos, "btn-edit")
        self.assertContains(equipos, "ec-equipos-data")
