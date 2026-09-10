"""Bot de transportistas (Fase 3): identifica por OFERTA-<código>, registra la
oferta EN la mesa de negociación, y avisa por WhatsApp al adjudicar / contraofertar.
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.catalogo.models import TipoVehiculo
from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.servicios.models import Servicio
from apps.tercerizacion import adjudicacion as adj
from apps.tercerizacion import bot_service
from apps.tercerizacion.models import (
    HiloNegociacion, MensajeNegociacion, OfertaTransportista, PublicacionCarga,
    Transportista, TransportistaBotState, TransportistaVehiculo,
)
from apps.tercerizacion.services import identificar_posible_transportista
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel

User = get_user_model()
_SENT = "apps.whatsapp_bot_v4.services.ycloud_webhook_service.send_via_ycloud"


def _ok_send(*a, **k):
    return {"success": True}


@override_settings(TRANSPORTISTA_BOT_ENABLED=True)
@patch(_SENT, side_effect=_ok_send)
class BotTransportistaTests(APITestCase):
    def setUp(self):
        self.channel = WhatsAppChannel.objects.create(nombre="Main", phone_number_id="51999", activo=True)
        cli_final = Cliente.objects.create(nombre="Cliente Final", telefono="+51900000001")
        self.lead = Lead.objects.create(cliente=cli_final, tipo_servicio="carga", codigo="CRG-BOT1",
                                        distrito_origen="Lima", distrito_destino="Callao")
        self.svc = Servicio.objects.create(
            lead_origen=self.lead, cliente=cli_final, distrito_origen="Lima", distrito_destino="Callao",
            fecha_servicio=date.today() + timedelta(days=3), horario_servicio="09:00", precio=1500,
            modalidad_ejecucion=Servicio.MODALIDAD_TERCERIZADO,
        )
        self.pub = PublicacionCarga.objects.create(
            servicio=self.svc, codigo="A47", texto_publicado="OFERTA-A47",
            estado=PublicacionCarga.ESTADO_ABIERTA, modo_precio=PublicacionCarga.PRECIO_ABIERTO,
        )
        self.transp = Cliente.objects.create(nombre="Transp Uno", telefono="+51955000001")
        self.conv = ConversacionWhatsApp.objects.create(cliente=self.transp, channel=self.channel)

    def _msg(self, texto):
        return MensajeWhatsApp.objects.create(
            conversacion=self.conv, tipo="texto", contenido=texto,
            direccion=MensajeWhatsApp.ENTRANTE, origen=MensajeWhatsApp.ORIGEN_CLIENTE,
        )

    def _run(self, texto, conv=None):
        conv = conv or self.conv
        m = MensajeWhatsApp.objects.create(
            conversacion=conv, tipo="texto", contenido=texto,
            direccion=MensajeWhatsApp.ENTRANTE, origen=MensajeWhatsApp.ORIGEN_CLIENTE,
        )
        es_transp = identificar_posible_transportista(conv, m)
        if es_transp:
            bot_service.process_transportista_bot_response(conv, m)
        return es_transp

    def test_identifica_por_codigo_y_no_al_cliente(self, _s):
        self.assertTrue(self._run("Hola, OFERTA-A47"))
        self.transp.refresh_from_db()
        self.assertTrue(self.transp.es_transportista)
        # código suelto sin prefijo NO identifica
        otro = Cliente.objects.create(nombre="X", telefono="+51955000009")
        conv2 = ConversacionWhatsApp.objects.create(cliente=otro, channel=self.channel)
        m = MensajeWhatsApp.objects.create(conversacion=conv2, tipo="texto", contenido="A47",
                                           direccion=MensajeWhatsApp.ENTRANTE, origen=MensajeWhatsApp.ORIGEN_CLIENTE)
        self.assertFalse(identificar_posible_transportista(conv2, m))

    def test_oferta_entra_a_la_mesa_de_negociacion(self, _s):
        self._run("OFERTA-A47")
        self._run("ofertar")
        self._run("850")

        oferta = OfertaTransportista.objects.get(publicacion=self.pub, cliente=self.transp)
        self.assertEqual(oferta.precio_ofertado, Decimal("850"))
        # la clave del fix: se abrió el hilo de compra + la publicación pasó a con_ofertas
        self.pub.refresh_from_db()
        self.assertEqual(self.pub.estado, PublicacionCarga.ESTADO_CON_OFERTAS)
        hilo = HiloNegociacion.objects.get(lead=self.lead, tipo=HiloNegociacion.TIPO_COMPRA, contraparte=self.transp)
        self.assertEqual(hilo.monto_actual, Decimal("850"))
        self.assertTrue(hilo.mensajes.filter(emisor=MensajeNegociacion.EMISOR_TRANSPORTISTA,
                                             propuesta_monto=Decimal("850")).exists())

    def test_actualiza_oferta_con_nuevo_monto(self, _s):
        self._run("OFERTA-A47"); self._run("ofertar"); self._run("850")
        self._run("800")
        self.assertEqual(OfertaTransportista.objects.filter(publicacion=self.pub, cliente=self.transp).count(), 1)
        self.assertEqual(
            OfertaTransportista.objects.get(publicacion=self.pub, cliente=self.transp).monto_actual, Decimal("800"))

    def test_contraoferta_del_asesor_llega_por_whatsapp(self, send):
        self._run("OFERTA-A47"); self._run("ofertar"); self._run("850")
        hilo = HiloNegociacion.objects.get(contraparte=self.transp)
        prop = hilo.mensajes.filter(propuesta_monto=Decimal("850")).first()

        Group.objects.get_or_create(name="Despacho")
        u = User.objects.create_user("bot_desp", password="x")
        u.groups.add(Group.objects.get(name="Despacho"))
        self.client.force_authenticate(u)
        send.reset_mock()
        r = self.client.post(f"/api/v2/negotiations/messages/{prop.id}/respond",
                             {"action": "counter", "amount": "780"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(send.called)
        self.assertIn("780", send.call_args[0][1])

    def test_transportista_acepta_por_whatsapp(self, _s):
        self._run("OFERTA-A47"); self._run("ofertar"); self._run("850")
        hilo = HiloNegociacion.objects.get(contraparte=self.transp)
        prop = hilo.mensajes.filter(propuesta_monto=Decimal("850")).first()
        # el asesor contrapropone (directo por servicio, sin API)
        from apps.tercerizacion import negociacion as neg
        neg.responder_propuesta(prop, "contraofertar", usuario=None, monto=Decimal("790"))

        self._run("acepto")
        hilo.refresh_from_db()
        self.assertEqual(hilo.estado, HiloNegociacion.ESTADO_ACUERDO)
        self.assertEqual(hilo.monto_acordado, Decimal("790"))

    def test_adjudicar_notifica_a_los_transportistas(self, send):
        self._run("OFERTA-A47"); self._run("ofertar"); self._run("850")
        # segundo transportista por WhatsApp
        t2 = Cliente.objects.create(nombre="Transp Dos", telefono="+51955000002")
        conv2 = ConversacionWhatsApp.objects.create(cliente=t2, channel=self.channel)
        self._run("OFERTA-A47", conv2); self._run("ofertar", conv2); self._run("900", conv2)
        self.assertEqual(OfertaTransportista.objects.filter(publicacion=self.pub).count(), 2)
        # afiliar al primero y adjudicarle (la adjudicación exige afiliado + vehículo)
        afiliado = Transportista.objects.create(nombre="Transp Uno SAC")
        TransportistaVehiculo.objects.create(transportista=afiliado, placa="BOT-100",
                                             tipo_vehiculo=TipoVehiculo.objects.get(codigo="camion"))
        o1 = OfertaTransportista.objects.get(publicacion=self.pub, cliente=self.transp)
        o1.transportista = afiliado
        o1.save()

        send.reset_mock()
        adj.adjudicar_publicacion(self.pub, o1, User.objects.create_user("adj_bot"), transportista_vehiculo=afiliado.vehiculos.first())
        textos = [c[0][1] for c in send.call_args_list]
        self.assertTrue(any("adjudic" in t.lower() and "A47" in t for t in textos))
        self.assertTrue(any("otro transportista" in t for t in textos))

    @override_settings(TRANSPORTISTA_BOT_ENABLED=False)
    def test_flag_apagado_no_responde(self, send):
        self._run("OFERTA-A47")
        # identificar sí (es clasificación), pero el bot no responde
        self.assertFalse(send.called)
