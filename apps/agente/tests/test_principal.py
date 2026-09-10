from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.clientes.models import Cliente, ClienteUsuario
from apps.agente.principal import (
    PrincipalNoResoluble, principal_desde_usuario, principal_sistema,
)
from apps.tercerizacion.models import Transportista

User = get_user_model()


class PrincipalTests(TestCase):
    def test_sistema(self):
        p = principal_sistema()
        self.assertEqual(p.tipo, "sistema")
        self.assertTrue(p.es_interno)
        self.assertTrue(p.ve_margen())

    def test_asesor_por_rol(self):
        u = User.objects.create_user("ase", password="x")
        u.groups.add(Group.objects.get_or_create(name="Asesor de Ventas")[0])
        p = principal_desde_usuario(u)
        self.assertEqual(p.tipo, "asesor")
        self.assertIn("Asesor de Ventas", p.roles)
        self.assertFalse(p.ve_margen())

    def test_gerencia_ve_margen(self):
        u = User.objects.create_user("ger", password="x")
        u.groups.add(Group.objects.get_or_create(name="Gerencia")[0])
        self.assertTrue(principal_desde_usuario(u).ve_margen())

    def test_transportista(self):
        u = User.objects.create_user("tr", password="x")
        Transportista.objects.create(nombre="T", usuario=u)
        p = principal_desde_usuario(u)
        self.assertEqual(p.tipo, "transportista")
        self.assertIsNotNone(p.carrier)

    def test_transportista_inactivo_no_resuelve(self):
        u = User.objects.create_user("tri", password="x")
        Transportista.objects.create(nombre="T", usuario=u, activo=False)
        with self.assertRaises(PrincipalNoResoluble):
            principal_desde_usuario(u)

    def test_cliente_portal(self):
        u = User.objects.create_user("cl", password="x")
        c = Cliente.objects.create(nombre="C", telefono="+51900000001")
        ClienteUsuario.objects.create(usuario=u, cliente=c)
        p = principal_desde_usuario(u)
        self.assertEqual(p.tipo, "cliente")
        self.assertEqual(p.cliente_id if hasattr(p, "cliente_id") else p.cliente.id, c.id)

    def test_precedencia_transportista_sobre_asesor(self):
        u = User.objects.create_user("mix", password="x")
        u.groups.add(Group.objects.get_or_create(name="Supervisor")[0])
        Transportista.objects.create(nombre="T", usuario=u)
        self.assertEqual(principal_desde_usuario(u).tipo, "transportista")

    def test_usuario_sin_perfil(self):
        u = User.objects.create_user("nadie", password="x")
        with self.assertRaises(PrincipalNoResoluble):
            principal_desde_usuario(u)

    def test_anonimo(self):
        from django.contrib.auth.models import AnonymousUser
        with self.assertRaises(PrincipalNoResoluble):
            principal_desde_usuario(AnonymousUser())
