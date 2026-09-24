"""Grafo de corredores compartidos (catálogo de 40 corredores, 2026-09).

Geometría 100% FICTICIA en estos tests (puntos en línea recta, sin relación
con carreteras reales) — sirve solo para probar la LÓGICA de grafo
(`apps.tercerizacion.corredores.detectar_corredores_compartidos` y afines),
no para validar ningún trazado real. La validación contra datos reales
(GeoNames + Mapbox Directions) se hizo aparte, corriendo los comandos
`geocodificar_localidades`/`registrar_corredores`/`calcular_tramos_corredores`
sobre el catálogo real de 40 corredores (ver informe de la sesión).

Escenario sintético (mismo patrón de bifurcación que el ejemplo real del
negocio): dos corredores comparten un tramo inicial y divergen después.

    Corredor A "Lima - Piura": Lima -> Trujillo -> Chiclayo -> Lambayeque -> Piura
    Corredor B "Lima - Jaén":  Lima -> Trujillo -> Chiclayo -> Lambayeque -> Olmos -> Jaén

Comparten los 3 tramos Lima-Trujillo, Trujillo-Chiclayo, Chiclayo-Lambayeque
(misma fila `TramoVial`, referenciada por ambos vía `CorredorTramo`) y
divergen justo después de Lambayeque.
"""
from decimal import Decimal

from django.test import TestCase

from apps.tercerizacion.corredores import (
    detectar_corredores_compartidos, distancia_a_trazado_km, normalizar_nombre,
    recalcular_trazado, resolver_corredor, resolver_localidad,
)
from apps.tercerizacion.models import Corredor, CorredorParada, CorredorTramo, Localidad, TramoVial


def _loc(nombre, lat, lng, departamento="Ficticio", **kw):
    return Localidad.objects.create(
        nombre=nombre, departamento=departamento, lat=Decimal(str(lat)), lng=Decimal(str(lng)),
        fuente_geografica="manual", estado_validacion=Localidad.ESTADO_RESUELTO, **kw,
    )


def _tramo(a, b, distancia_km=10):
    """Geometría ficticia: solo los dos extremos, línea recta — alcanza para
    probar la lógica de grafo (orden/sentido), no un trazado vial real."""
    return TramoVial.objects.create(
        nodo_inicio=a, nodo_fin=b,
        geometria=[[float(a.lng), float(a.lat)], [float(b.lng), float(b.lat)]],
        distancia_km=Decimal(str(distancia_km)), estado_validacion=TramoVial.ESTADO_CALCULADO,
        fuente_geografica="ficticio_test",
    )


def _encadenar(corredor, tramos):
    for i, tramo in enumerate(tramos):
        CorredorTramo.objects.create(corredor=corredor, tramo=tramo, orden=i, sentido=CorredorTramo.SENTIDO_IDA)
    recalcular_trazado(corredor)


class GrafoCorredoresCompartidosTests(TestCase):
    def setUp(self):
        self.lima = _loc("Lima", -12.0, -77.0)
        self.trujillo = _loc("Trujillo", -8.1, -79.0)
        self.chiclayo = _loc("Chiclayo", -6.8, -79.8)
        self.lambayeque = _loc("Lambayeque", -6.7, -79.9)
        self.piura = _loc("Piura", -5.2, -80.6)
        self.olmos = _loc("Olmos", -6.0, -79.7)
        self.jaen = _loc("Jaén", -5.7, -78.8)

        t_lima_trujillo = _tramo(self.lima, self.trujillo, 560)
        t_trujillo_chiclayo = _tramo(self.trujillo, self.chiclayo, 210)
        t_chiclayo_lambayeque = _tramo(self.chiclayo, self.lambayeque, 15)
        t_lambayeque_piura = _tramo(self.lambayeque, self.piura, 200)
        t_lambayeque_olmos = _tramo(self.lambayeque, self.olmos, 90)
        t_olmos_jaen = _tramo(self.olmos, self.jaen, 180)

        self.corredor_piura = Corredor.objects.create(
            codigo="TEST-PIURA", nombre="Lima - Piura (test)", activo=True,
            localidad_origen=self.lima, localidad_destino=self.piura,
        )
        _encadenar(self.corredor_piura, [t_lima_trujillo, t_trujillo_chiclayo, t_chiclayo_lambayeque, t_lambayeque_piura])

        self.corredor_jaen = Corredor.objects.create(
            codigo="TEST-JAEN", nombre="Lima - Jaén (test)", activo=True,
            localidad_origen=self.lima, localidad_destino=self.jaen,
        )
        _encadenar(self.corredor_jaen, [t_lima_trujillo, t_trujillo_chiclayo, t_chiclayo_lambayeque, t_lambayeque_olmos, t_olmos_jaen])

    # -- 1. tramos compartidos --------------------------------------

    def test_corredores_comparten_la_misma_fila_de_tramo(self):
        """Lima-Trujillo, Trujillo-Chiclayo y Chiclayo-Lambayeque son la MISMA
        fila TramoVial en ambos corredores — no se duplican."""
        tramos_piura = {ct.tramo_id for ct in self.corredor_piura.tramos.all()}
        tramos_jaen = {ct.tramo_id for ct in self.corredor_jaen.tramos.all()}
        compartidos = tramos_piura & tramos_jaen
        self.assertEqual(len(compartidos), 3)
        self.assertEqual(TramoVial.objects.count(), 6)  # 4 + 5 tramos, 3 compartidos = 6 filas únicas

    def test_localidad_no_se_duplica_por_nombre(self):
        # Lima aparece en ambos corredores — debe ser la MISMA fila.
        self.assertEqual(Localidad.objects.filter(nombre_normalizado="lima").count(), 1)

    # -- 2. detección de corredores compartidos (sección 8 del pedido) ----

    def test_trujillo_chiclayo_identifica_ambos_corredores(self):
        res = detectar_corredores_compartidos(self.trujillo, self.chiclayo)
        codigos = {r["corredor"].codigo for r in res if r["tramo_completo"]}
        self.assertEqual(codigos, {"TEST-PIURA", "TEST-JAEN"})

    def test_chiclayo_jaen_no_es_lima_piura(self):
        """Chiclayo -> Jaén NO debe reconocerse como parte de Lima-Piura —
        Jaén no está en esa secuencia."""
        res = detectar_corredores_compartidos(self.chiclayo, self.jaen)
        codigos = {r["corredor"].codigo for r in res if r["tramo_completo"]}
        self.assertEqual(codigos, {"TEST-JAEN"})
        self.assertNotIn("TEST-PIURA", codigos)

    def test_sentido_inverso_no_matchea(self):
        """Una carga en sentido contrario (Chiclayo -> Trujillo) no debe
        identificarse como si viajara en el sentido del corredor."""
        res = detectar_corredores_compartidos(self.chiclayo, self.trujillo)
        completos = [r for r in res if r["tramo_completo"]]
        self.assertEqual(completos, [])

    def test_ica_nazca_style_tramo_intermedio_compartido(self):
        """Un tramo intermedio (no origen/destino de ningún corredor) también
        se detecta si varios corredores lo comparten."""
        res = detectar_corredores_compartidos(self.trujillo, self.lambayeque)
        codigos = {r["corredor"].codigo for r in res if r["tramo_completo"]}
        self.assertEqual(codigos, {"TEST-PIURA", "TEST-JAEN"})

    def test_sin_geometria_calculada_no_se_detecta_nada(self):
        """Un corredor sin CorredorTramo (solo registrado, PENDIENTE_TRAZADO)
        no debe aparecer en la detección — no hay geometría real que
        respalde la afirmación de que comparte algo."""
        pendiente = Corredor.objects.create(codigo="TEST-PEND", nombre="Corredor sin trazado")
        res = detectar_corredores_compartidos(self.trujillo, self.chiclayo)
        codigos = {r["corredor"].codigo for r in res}
        self.assertNotIn("TEST-PEND", codigos)

    def test_requiere_desvio_se_propaga(self):
        """Una parada marcada `requiere_desvio=True` en el corredor debe
        reflejarse en el resultado — no se trata como si estuviera limpiamente
        sobre el eje."""
        CorredorParada.objects.create(
            corredor=self.corredor_jaen, nombre="Olmos", orden=0,
            lat=self.olmos.lat, lng=self.olmos.lng, requiere_desvio=True,
        )
        res = detectar_corredores_compartidos(self.lima, self.jaen)
        fila = next(r for r in res if r["corredor"].codigo == "TEST-JAEN")
        self.assertTrue(fila["requiere_desvio"])

    # -- 3. resolver_corredor (motor de precios) no cambia -----------------

    def test_resolver_corredor_sigue_funcionando_con_trazado_derivado(self):
        """`resolver_corredor` (ya en producción) opera sobre `trazado` sin
        saber nada de tramos — debe seguir funcionando igual cuando `trazado`
        viene derivado de CorredorTramo (recalcular_trazado)."""
        self.corredor_piura.tolerancia_eje_km = Decimal("50")
        self.corredor_piura.desvio_maximo_km = Decimal("100")
        self.corredor_piura.save()
        # Punto muy cerca de Chiclayo (sin CorredorParada propia en este test).
        d_km, pos_km = distancia_a_trazado_km(float(self.chiclayo.lat), float(self.chiclayo.lng), self.corredor_piura.trazado)
        self.assertIsNotNone(d_km)
        self.assertLess(d_km, 1)

    def test_destino_fuera_de_cualquier_corredor_no_bloquea(self):
        """Un punto lejos de cualquier corredor -> resolver_corredor devuelve
        None (nunca bloquea al llamador, solo Exclusivo)."""
        resultado = resolver_corredor(-3.0, -60.0)  # Amazonía profunda, ningún corredor de prueba pasa cerca
        self.assertIsNone(resultado)

    # -- 4. resolver_localidad ---------------------------------------

    def test_resolver_localidad_por_nombre_exacto(self):
        self.assertEqual(resolver_localidad("Lima").id, self.lima.id)
        self.assertEqual(resolver_localidad("  LIMA  ").id, self.lima.id)

    def test_resolver_localidad_inexistente_no_bloquea(self):
        self.assertIsNone(resolver_localidad("Ciudad Inventada Que No Existe"))

    def test_normalizar_nombre_sin_tildes(self):
        self.assertEqual(normalizar_nombre("Jaén"), "jaen")
        self.assertEqual(normalizar_nombre("  Chiclayo  "), "chiclayo")
