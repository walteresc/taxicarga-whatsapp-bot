from django.test import TestCase

from apps.agente import registro
from apps.agente.errores import FueraDeAlcance, NoEncontrado
from apps.agente.models import AccionAgente
from apps.agente.principal import principal_sistema
from apps.agente.registro import ResultadoCapacidad, capacidad, ejecutar


class _TmpCaps:
    """Registra capacidades de prueba y las limpia al terminar."""

    NOMBRES = ("tst_ok", "tst_boom_alcance", "tst_boom_regla", "tst_solo_asesor")

    @classmethod
    def montar(cls):
        @capacidad("tst_ok", perfiles=["sistema", "asesor"], efecto="lectura")
        def _ok(principal, x=1):
            """Devuelve el doble de x."""
            return {"doble": x * 2}

        @capacidad("tst_boom_alcance", perfiles=["sistema"], efecto="lectura")
        def _alc(principal):
            """Siempre fuera de alcance."""
            raise FueraDeAlcance("no podés ver esto")

        @capacidad("tst_boom_regla", perfiles=["sistema"], efecto="escritura_reversible")
        def _reg(principal):
            """Rompe una regla de negocio."""
            from apps.tercerizacion.negociacion import NegociacionError
            raise NegociacionError("la mesa está pausada")

        @capacidad("tst_solo_asesor", perfiles=["asesor"], efecto="lectura")
        def _sa(principal):
            """Solo asesor."""
            return {"ok": True}

    @classmethod
    def desmontar(cls):
        for n in cls.NOMBRES:
            registro._REGISTRO.pop(n, None)


class RegistroTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _TmpCaps.montar()

    @classmethod
    def tearDownClass(cls):
        _TmpCaps.desmontar()
        super().tearDownClass()

    def test_happy_path_y_auditoria(self):
        r = ejecutar("tst_ok", principal_sistema(), x=5)
        self.assertIsInstance(r, ResultadoCapacidad)
        self.assertTrue(r.ok)
        self.assertEqual(r.datos, {"doble": 10})
        fila = AccionAgente.objects.get(capacidad="tst_ok")
        self.assertTrue(fila.ok)
        self.assertEqual(fila.principal_tipo, "sistema")
        self.assertEqual(fila.args, {"x": 5})
        self.assertEqual(fila.resultado, {"doble": 10})

    def test_capacidad_desconocida(self):
        r = ejecutar("no_existe", principal_sistema())
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo_error, "no_encontrado")

    def test_perfil_no_autorizado_no_ejecuta_cuerpo(self):
        r = ejecutar("tst_solo_asesor", principal_sistema())
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo_error, "perfil_no_autorizado")
        # igual queda auditado
        self.assertTrue(AccionAgente.objects.filter(
            capacidad="tst_solo_asesor", codigo_error="perfil_no_autorizado").exists())

    def test_fuera_de_alcance(self):
        r = ejecutar("tst_boom_alcance", principal_sistema())
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo_error, "fuera_de_alcance")
        self.assertIn("no podés ver esto", r.error)

    def test_regla_de_negocio(self):
        r = ejecutar("tst_boom_regla", principal_sistema())
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo_error, "regla_negocio")
        self.assertIn("pausada", r.error)

    def test_arg_invalido(self):
        r = ejecutar("tst_ok", principal_sistema(), y=99)  # 'y' no existe
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo_error, "arg_invalido")

    def test_catalogo_ordenado(self):
        nombres = [c.nombre for c in registro.catalogo()]
        self.assertEqual(nombres, sorted(nombres, key=lambda n: (registro._REGISTRO[n].efecto, n)))
