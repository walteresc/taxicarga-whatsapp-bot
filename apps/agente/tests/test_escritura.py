from unittest import mock

from django.test import TestCase

from apps.agente.models import AccionAgente
from apps.agente.registro import ejecutar
from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.tercerizacion.models import HiloNegociacion

from ._fixtures import Mundo


class NegociacionCapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.m = Mundo()

    def test_abrir_negociacion_venta(self):
        r = ejecutar("abrir_negociacion", self.m.p_asesor, codigo=self.m.lead2.codigo, con="cliente")
        self.assertTrue(r.ok, r.error)
        self.assertEqual(r.datos["tipo"], "venta")

    def test_abrir_negociacion_perfil_cliente_denegado(self):
        r = ejecutar("abrir_negociacion", self.m.p_cliente, codigo=self.m.lead.codigo)
        self.assertEqual(r.codigo_error, "perfil_no_autorizado")

    def test_cliente_manda_mensaje_en_su_hilo(self):
        r = ejecutar("enviar_mensaje_negociacion", self.m.p_cliente,
                     hilo_id=self.m.hilo_venta.id, texto="puedo pagar 820")
        self.assertTrue(r.ok, r.error)

    def test_cliente_no_manda_en_hilo_ajeno(self):
        r = ejecutar("enviar_mensaje_negociacion", self.m.p_cliente,
                     hilo_id=self.m.hilo_compra.id, texto="hola")
        self.assertEqual(r.codigo_error, "no_encontrado")

    def test_asesor_propone_y_cliente_acepta(self):
        p = ejecutar("enviar_mensaje_negociacion", self.m.p_asesor,
                     hilo_id=self.m.hilo_venta.id, texto="cerramos", monto=850)
        self.assertTrue(p.ok, p.error)
        hilo = HiloNegociacion.objects.get(pk=self.m.hilo_venta.id)
        prop = hilo.mensajes.filter(tipo="propuesta", emisor="taxicarga").latest("creado_en")
        r = ejecutar("responder_propuesta", self.m.p_cliente, mensaje_id=prop.id, accion="aceptar")
        self.assertTrue(r.ok, r.error)
        self.assertEqual(r.datos["estado"], "acuerdo")

    def test_cliente_no_responde_su_propia_propuesta(self):
        hilo = HiloNegociacion.objects.get(pk=self.m.hilo_venta.id)
        prop = hilo.mensajes.filter(emisor="cliente", tipo="propuesta").first()
        r = ejecutar("responder_propuesta", self.m.p_cliente, mensaje_id=prop.id, accion="aceptar")
        self.assertEqual(r.codigo_error, "fuera_de_alcance")


class CargaCapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.m = Mundo()

    def test_dejar_nota(self):
        r = ejecutar("dejar_nota", self.m.p_asesor, codigo=self.m.lead.codigo, texto="cliente pidió factura")
        self.assertTrue(r.ok, r.error)
        self.m.lead.refresh_from_db()
        self.assertIn("cliente pidió factura", self.m.lead.nota_interna)

    def test_dejar_nota_cliente_denegado(self):
        r = ejecutar("dejar_nota", self.m.p_cliente, codigo=self.m.lead.codigo, texto="x")
        self.assertEqual(r.codigo_error, "perfil_no_autorizado")

    def test_marcar_datos_faltantes_completa(self):
        r = ejecutar("marcar_datos_faltantes", self.m.p_asesor, codigo=self.m.lead.codigo)
        self.assertTrue(r.ok, r.error)
        self.assertTrue(r.datos["completa"])

    def test_marcar_datos_faltantes_incompleta(self):
        cli = Cliente.objects.create(nombre="", telefono="+51900000199")
        lead = Lead.objects.create(cliente=cli, tipo_servicio="mudanza",
                                   distrito_origen="A", distrito_destino="B")
        r = ejecutar("marcar_datos_faltantes", self.m.p_asesor, codigo=lead.codigo)
        self.assertFalse(r.datos["completa"])
        self.assertIn("fecha_servicio", r.datos["faltan"])

    def test_crear_reserva_falla_por_datos(self):
        cli = Cliente.objects.create(nombre="X", telefono="+51900000198")
        lead = Lead.objects.create(cliente=cli, tipo_servicio="mudanza",
                                   distrito_origen="A", distrito_destino="B")
        r = ejecutar("crear_reserva", self.m.p_asesor, codigo=lead.codigo)
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo_error, "regla_negocio")

    def test_cerrar_precio_crea_reserva(self):
        # monto = última revisión (900): no manda revisión/WhatsApp, solo acepta + reserva.
        # (cerrar_precio con precio distinto necesita conversación WhatsApp del lead —
        #  restricción heredada de QuoteClosePriceView.)
        r = ejecutar("cerrar_precio", self.m.p_asesor, codigo=self.m.lead.codigo, monto=900)
        self.assertTrue(r.ok, r.error)
        self.assertTrue(r.datos["reserva"])
        self.m.lead.refresh_from_db()
        self.assertTrue(hasattr(self.m.lead, "servicio_generado"))

    def test_derivar_a_tercerizacion(self):
        r = ejecutar("derivar_a_tercerizacion", self.m.p_asesor,
                     codigo=self.m.lead.codigo, modo_precio="referencial", precio_ref=700)
        self.assertTrue(r.ok, r.error)
        self.assertTrue(r.datos["publicacion"])


class TercerizacionOperacionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.m = Mundo()

    def test_transportista_oferta_por_si_mismo(self):
        # publicacion abierta (F01), el carrier2 aún no ofertó
        r = ejecutar("registrar_oferta", self.m.p_carrier2,
                     publicacion_codigo=self.m.publicacion.codigo, monto=830)
        self.assertTrue(r.ok, r.error)

    def test_publicar_requiere_rol_margen(self):
        # la publicacion de _fixtures ya está abierta → creamos una en borrador
        from apps.tercerizacion.models import PublicacionCarga
        from apps.servicios.models import Servicio
        svc = Servicio.objects.create(lead_origen=self.m.lead, cliente=self.m.cliente,
                                      fecha_servicio=self.m.lead.fecha_servicio, precio=500,
                                      modalidad_ejecucion=Servicio.MODALIDAD_TERCERIZADO)
        pub = PublicacionCarga.objects.create(servicio=svc, codigo="F02", texto_publicado="x",
                                              estado=PublicacionCarga.ESTADO_BORRADOR)
        r = ejecutar("publicar_a_transportistas", self.m.p_asesor, publicacion_codigo="F02")
        self.assertEqual(r.codigo_error, "fuera_de_alcance")
        r2 = ejecutar("publicar_a_transportistas", self.m.p_gerente, publicacion_codigo="F02")
        self.assertTrue(r2.ok, r2.error)

    def test_adjudicar(self):
        self.m.oferta.transportista_vehiculo = self.m.tv
        self.m.oferta.save(update_fields=["transportista_vehiculo"])
        r = ejecutar("adjudicar", self.m.p_gerente,
                     publicacion_codigo=self.m.publicacion.codigo, oferta_id=self.m.oferta.id)
        self.assertTrue(r.ok, r.error)
        self.assertTrue(r.datos["programacion_id"])

    def test_asignar_propio(self):
        from apps.campo.models import Vehiculo
        veh = Vehiculo.objects.create(placa="XYZ-999", marca="V", modelo="M", anio=2020,
                                      capacidad_toneladas=2)
        # lead2 tiene servicio2 con fecha/hora
        r = ejecutar("asignar", self.m.p_asesor, reserva_codigo=self.m.servicio2.codigo,
                     recurso=f"v{veh.id}")
        self.assertTrue(r.ok, r.error)

    def test_registrar_pago(self):
        r = ejecutar("registrar_pago", self.m.p_asesor, reserva_codigo=self.m.servicio2.codigo,
                     concepto="adelanto", metodo_pago="yape", monto=300)
        self.assertTrue(r.ok, r.error)
        self.assertEqual(r.datos["monto"], 300.0)


class MensajeriaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.m = Mundo()

    def test_enviar_whatsapp_mockeado(self):
        with mock.patch(
            "apps.whatsapp_bot_v4.services.ycloud_webhook_service.send_via_ycloud"
        ) as sender:
            r = ejecutar("enviar_whatsapp", self.m.p_asesor,
                         carga_codigo=self.m.lead.codigo, texto="tu servicio quedó agendado")
        self.assertTrue(r.ok, r.error)
        sender.assert_called_once()
        self.assertEqual(sender.call_args[0][0], self.m.cliente.telefono)

    def test_enviar_whatsapp_perfil_cliente_denegado(self):
        r = ejecutar("enviar_whatsapp", self.m.p_cliente, carga_codigo=self.m.lead.codigo, texto="x")
        self.assertEqual(r.codigo_error, "perfil_no_autorizado")

    def test_encolar_revision(self):
        with mock.patch("apps.cotizador.delivery.queue_revision_whatsapp") as q:
            r = ejecutar("encolar_revision_whatsapp", self.m.p_asesor,
                         cotizacion_codigo=self.m.cotizacion.codigo)
        self.assertTrue(r.ok, r.error)
        q.assert_called_once()


class AuditoriaCriticaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.m = Mundo()

    def test_escritura_critica_queda_auditada_con_servicio(self):
        AccionAgente.objects.all().delete()
        r = ejecutar("cerrar_precio", self.m.p_asesor, codigo=self.m.lead.codigo, monto=900)
        self.assertTrue(r.ok, r.error)
        fila = AccionAgente.objects.get(capacidad="cerrar_precio")
        self.assertEqual(fila.efecto, "escritura_critica")
        self.assertTrue(fila.ok)
        self.assertIsNotNone(fila.servicio_id)
