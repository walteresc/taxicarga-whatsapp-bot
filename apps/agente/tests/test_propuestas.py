from django.test import TestCase

from apps.agente.errores import PerfilNoAutorizado
from apps.agente.models import PropuestaAccion
from apps.agente.orquestador import aplicar_propuesta, rechazar_propuesta
from apps.servicios.models import Servicio

from ._fixtures import Mundo


class PropuestaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.m = Mundo()

    def _prop(self, capacidad, args):
        return PropuestaAccion.objects.create(
            usuario=self.m.u_asesor, capacidad=capacidad, efecto="escritura_critica",
            args=args, resumen="test",
        )

    def test_aplicar_ejecuta_como_el_confirmador(self):
        prop = self._prop("crear_reserva", {"codigo": self.m.lead.codigo})
        res = aplicar_propuesta(prop, self.m.u_despacho)
        self.assertTrue(res.ok, res.error)
        prop.refresh_from_db()
        self.assertEqual(prop.estado, "aplicada")
        self.assertEqual(prop.resuelta_por, self.m.u_despacho)
        self.assertTrue(Servicio.objects.filter(lead_origen=self.m.lead).exists())

    def test_no_se_aplica_dos_veces(self):
        prop = self._prop("crear_reserva", {"codigo": self.m.lead.codigo})
        aplicar_propuesta(prop, self.m.u_asesor)
        with self.assertRaises(PerfilNoAutorizado):
            aplicar_propuesta(prop, self.m.u_asesor)

    def test_regla_de_negocio_marca_rechazada(self):
        # cerrar_precio de una carga sin cotización → regla_negocio
        from apps.clientes.models import Cliente
        from apps.leads.models import Lead
        cli = Cliente.objects.create(nombre="Z", telefono="+51900000188")
        lead = Lead.objects.create(cliente=cli, tipo_servicio="mudanza",
                                   distrito_origen="A", distrito_destino="B")
        prop = self._prop("cerrar_precio", {"codigo": lead.codigo, "monto": 500})
        res = aplicar_propuesta(prop, self.m.u_asesor)
        self.assertFalse(res.ok)
        prop.refresh_from_db()
        self.assertEqual(prop.estado, "rechazada")
        self.assertTrue(prop.motivo_rechazo)

    def test_rechazar(self):
        prop = self._prop("crear_reserva", {"codigo": self.m.lead.codigo})
        rechazar_propuesta(prop, self.m.u_asesor, motivo="el cliente canceló")
        prop.refresh_from_db()
        self.assertEqual(prop.estado, "rechazada")
        self.assertEqual(prop.motivo_rechazo, "el cliente canceló")
        with self.assertRaises(PerfilNoAutorizado):
            aplicar_propuesta(prop, self.m.u_asesor)
