from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.core.management import call_command
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.cotizador.models import ServicioHistorico
from apps.ia.conversation_engine import handle_incoming_message
from apps.ia.data_extractor import extract_lead_data, extract_route_locations
from apps.leads.models import Lead
from apps.ia.models import EjemploConversacion
from apps.ia.history import conversation_examples_for


class DataExtractorTests(TestCase):
    def test_extrae_datos_comerciales_en_mensaje_largo(self):
        today = timezone.localdate()

        data = extract_lead_data(
            "Soy Juan Perez, quiero mudanza de Miraflores a Surco con cama, "
            "refrigeradora y 10 cajas. Origen 2do piso con ascensor, destino "
            "4to piso sin ascensor, manana 9am"
        )

        self.assertEqual(data["cliente_nombre"], "Juan Perez")
        self.assertEqual(data["tipo_servicio"], "mudanza")
        self.assertEqual(data["distrito_origen"], "Miraflores")
        self.assertEqual(data["distrito_destino"], "Surco")
        self.assertEqual(data["piso_origen"], 2)
        self.assertEqual(data["piso_destino"], 4)
        self.assertEqual(data["fecha_servicio"], today + timedelta(days=1))
        self.assertEqual(data["horario_servicio"], "9:00 am")
        self.assertIn("lista_objetos", data)

    def test_extrae_proximo_dia_de_semana(self):
        today = timezone.localdate()
        expected = today + timedelta(days=(0 - today.weekday()) % 7)

        data = extract_lead_data("el dia lunes a las 10 am")

        self.assertEqual(data["fecha_servicio"], expected)
        self.assertEqual(data["horario_servicio"], "10:00 am")

    def test_extrae_ruta_desde_frase_natural(self):
        data = extract_lead_data(
            "Se recogen de Surco y va a La Molina",
        )

        self.assertEqual(data["distrito_origen"], "Surco")
        self.assertEqual(data["distrito_destino"], "La Molina")

    def test_personal_para_cargar_no_cambia_mudanza_a_carga(self):
        data = extract_lead_data("lo quiero con personal para cargar")

        self.assertNotIn("tipo_servicio", data)
        self.assertTrue(data["incluye_personal_carga"])

    def test_distingue_los_tres_tipos_de_embalaje(self):
        self.assertEqual(
            extract_lead_data("quiero embalaje basico")["modalidad_servicio"],
            "embalaje basico",
        )
        self.assertEqual(
            extract_lead_data("embalaje de muebles y artefactos")["modalidad_servicio"],
            "embalaje de muebles y artefactos",
        )
        self.assertEqual(
            extract_lead_data("quiero embalaje full")["modalidad_servicio"],
            "embalaje full",
        )

    def test_extrae_pisos_abreviados_sin_la_palabra_piso(self):
        data = extract_lead_data("1ero a 1ero")

        self.assertEqual(data["piso_origen"], 1)
        self.assertEqual(data["piso_destino"], 1)

    def test_numeros_de_carga_personal_y_peso_no_se_reutilizan_como_pisos(self):
        cases = [
            ("Mudanza de Surco a Miraflores. Tengo 15 cajas", "lista_objetos", "15"),
            ("Mudanza de Surco a Miraflores. Tengo 2 camas y 20 cajas", "lista_objetos", "20"),
            ("Necesito 2 ayudantes", "cantidad_operarios", 2),
            ("La carga pesa 800 kg", "peso_carga_kg", Decimal("800")),
        ]
        for message, field, expected in cases:
            with self.subTest(message=message):
                data = extract_lead_data(message)
                locations = extract_route_locations(message)
                self.assertNotIn("piso_origen", data)
                self.assertNotIn("piso_destino", data)
                self.assertTrue(all(item["piso"] is None for item in locations))
                self.assertIn(expected, data[field]) if isinstance(expected, str) else self.assertEqual(data[field], expected)

    def test_cajas_y_piso_explicito_se_extraen_como_entidades_distintas(self):
        data = extract_lead_data("15 cajas, destino piso 2")
        self.assertIn("15 cajas", data["lista_objetos"])
        self.assertEqual(data["piso_destino"], 2)

    def test_piso_quince_con_ascensor_es_nivel(self):
        data = extract_lead_data("destino piso 15 con ascensor")
        self.assertEqual(data["piso_destino"], 15)


class WhatsappHistoryImportTests(TestCase):
    def test_importa_ejemplos_anonimizados(self):
        call_command(
            "importar_chats_whatsapp",
            "apps/ia/tests_data/whatsapp_sample.txt",
        )

        self.assertEqual(EjemploConversacion.objects.count(), 3)
        combined = " ".join(
            EjemploConversacion.objects.values_list(
                "mensaje_cliente",
                flat=True,
            )
        )
        self.assertNotIn("999 888 777", combined)
        self.assertNotIn("cliente@example.com", combined)
        self.assertIn("[CORREO]", combined)
        self.assertTrue(
            EjemploConversacion.objects.filter(requiere_revision=True).exists()
        )

    def test_recupera_solo_ejemplos_aprobables_y_relevantes(self):
        approved = EjemploConversacion.objects.create(
            referencia_chat="chat-approved",
            turno=1,
            mensaje_cliente="Estoy en un piso alto",
            respuesta_negocio="Hay ascensor?",
            etiquetas=["acceso"],
        )
        EjemploConversacion.objects.create(
            referencia_chat="chat-review",
            turno=1,
            mensaje_cliente="Mi direccion exacta es privada",
            respuesta_negocio="Gracias",
            etiquetas=["acceso"],
            requiere_revision=True,
        )

        examples = conversation_examples_for(
            "sale del piso 4",
            "Hay ascensor?",
        )

        self.assertIn(approved, examples)
        self.assertTrue(all(not example.requiere_revision for example in examples))


@override_settings(OPENAI_API_KEY="")
class ConversationEngineTests(TestCase):
    def test_pregunta_siguiente_dato_faltante(self):
        cliente = Cliente.objects.create(telefono="51933333333")

        reply = handle_incoming_message(cliente, "Hola, quiero una mudanza")

        lead = cliente.leads.first()
        self.assertEqual(lead.tipo_servicio, "mudanza")
        self.assertEqual(lead.estado, Lead.DATOS_INCOMPLETOS)
        self.assertIn("distrito", reply.lower())

    def test_saludo_inicial_pregunta_que_desea_trasladar(self):
        cliente = Cliente.objects.create(telefono="51933333334")

        reply = handle_incoming_message(cliente, "Hola")

        self.assertEqual(reply, "Hola, que deseas trasladar?")
        lead = cliente.leads.first()
        self.assertEqual(lead.tipo_servicio, "")

    def test_inventario_inicial_clasifica_traslado_pequeno(self):
        cliente = Cliente.objects.create(telefono="51933333335")
        handle_incoming_message(cliente, "Hola")

        reply = handle_incoming_message(
            cliente,
            "una refrigeradora y un estante",
        )

        lead = cliente.leads.first()
        self.assertEqual(lead.tipo_servicio, "traslado pequeno")
        self.assertIn("refrigeradora", lead.lista_objetos.lower())
        self.assertIn("partida", reply.lower())
        self.assertNotIn("mudanza", reply.lower())

    def test_primer_mensaje_completo_guarda_todo_y_pide_solo_lo_faltante(self):
        cliente = Cliente.objects.create(telefono="51933333336")

        reply = handle_incoming_message(
            cliente,
            "Hola, quiero trasladar una refrigeradora de Surco a La Molina",
        )

        lead = cliente.leads.first()
        self.assertEqual(lead.tipo_servicio, "traslado pequeno")
        self.assertEqual(lead.distrito_origen, "Surco")
        self.assertEqual(lead.distrito_destino, "La Molina")
        self.assertIn("refrigeradora", lead.lista_objetos.lower())
        self.assertIn("piso", reply.lower())
        self.assertNotIn("que deseas trasladar", reply.lower())
        self.assertNotIn("distrito", reply.lower())

    def test_cotiza_cuando_hay_datos_suficientes(self):
        cliente = Cliente.objects.create(telefono="51944444444")
        for price in ["400.00", "450.00", "500.00"]:
            ServicioHistorico.objects.create(
                fecha="2026-01-01",
                tipo_servicio="mudanza",
                distrito_origen="Miraflores",
                distrito_destino="Surco",
                piso_origen=2,
                piso_destino=1,
                ascensor_origen=True,
                ascensor_destino=True,
                lista_objetos="cama queen refrigeradora sofa mesa cajas",
                precio_cotizado=Decimal(price),
                precio_final=Decimal(price),
                cerrado=True,
            )

        reply = handle_incoming_message(
            cliente,
            "Soy Ana Torres, quiero mudanza de Miraflores a Surco con cama queen, "
            "refrigeradora, sofa, mesa y cajas, manana 10am",
        )

        lead = cliente.leads.first()
        cliente.refresh_from_db()
        self.assertEqual(cliente.nombre, "Ana Torres")
        self.assertEqual(lead.estado, Lead.DATOS_INCOMPLETOS)
        self.assertIn("piso", reply.lower())

    def test_completa_flujo_con_respuestas_cortas(self):
        cliente = Cliente.objects.create(telefono="51955550001")

        self.assertIn("que deseas trasladar", handle_incoming_message(cliente, "hola").lower())
        self.assertIn("distrito", handle_incoming_message(cliente, "mudanza").lower())
        self.assertIn("distrito", handle_incoming_message(cliente, "Miraflores").lower())
        self.assertIn("cosas", handle_incoming_message(cliente, "Surco").lower())
        self.assertIn(
            "cosas",
            handle_incoming_message(
                cliente,
                "2do piso con ascensor, el camion llega a la puerta",
            ).lower(),
        )
        self.assertIn(
            "muebles",
            handle_incoming_message(
                cliente,
                "1er piso con ascensor, se estaciona en la puerta",
            ).lower(),
        )
        self.assertIn(
            "camion",
            handle_incoming_message(cliente, "cama, refrigeradora y 10 cajas").lower(),
        )
        self.assertIn(
            "costo",
            handle_incoming_message(cliente, "en ambos llega a la puerta").lower(),
        )
        self.assertIn("costo", handle_incoming_message(cliente, "con personal").lower())
        self.assertIn("costo", handle_incoming_message(cliente, "sin embalaje").lower())
        self.assertIn("precio", handle_incoming_message(cliente, "no").lower())
        reply = handle_incoming_message(cliente, "mañana")

        lead = cliente.leads.first()
        self.assertEqual(lead.tipo_servicio, "mudanza")
        self.assertEqual(lead.distrito_origen, "Miraflores")
        self.assertEqual(lead.distrito_destino, "Surco")
        self.assertEqual(lead.estado, Lead.COTIZADO)
        self.assertIn("precio", reply.lower())

    def test_pasa_de_cotizacion_a_reserva(self):
        cliente = Cliente.objects.create(telefono="51955550002")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Miraflores",
            distrito_destino="Surco",
            piso_origen=1,
            piso_destino=2,
            ascensor_origen=True,
            ascensor_destino=True,
            lista_objetos="cama, mesa y cajas",
            modalidad_servicio="solo traslado",
            requiere_desarmado=False,
            fecha_servicio=timezone.localdate() + timedelta(days=2),
            estado=Lead.COTIZADO,
            precio_recomendado=Decimal("350.00"),
        )

        self.assertIn("nombre", handle_incoming_message(cliente, "si, quiero reservar").lower())
        address_question = handle_incoming_message(cliente, "Maria Lopez").lower()
        self.assertIn("direcciones", address_question)
        self.assertIn(
            "hora",
            handle_incoming_message(
                cliente,
                "Av. Uno 123, Miraflores y Av. Dos 456, Surco",
            ).lower(),
        )
        reply = handle_incoming_message(cliente, "9 am")

        lead.refresh_from_db()
        self.assertEqual(lead.etapa_conversacion, Lead.ETAPA_RESERVA)
        self.assertEqual(lead.estado, Lead.COTIZADO)
        self.assertTrue(lead.requiere_asesor)
        self.assertIn("asesor", reply.lower())

    def test_consulta_pago_despues_de_reservar_no_reabre_cotizacion(self):
        cliente = Cliente.objects.create(
            telefono="51955550040",
            nombre="Walter Escobar",
        )
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            direccion_origen="Av. Primavera 123, Surco",
            direccion_destino="Calle Los Pinos 456, La Molina",
            piso_origen=2,
            piso_destino=3,
            etapa_conversacion=Lead.ETAPA_RESERVADO,
            estado=Lead.ASIGNADO,
            dni_reserva="12345678",
            fecha_servicio=timezone.localdate() + timedelta(days=1),
            horario_servicio="10:00 am",
            precio_cotizado=Decimal("160"),
            precio_final=Decimal("160"),
        )

        reply = handle_incoming_message(cliente, "ok. como seria el pago?")

        lead.refresh_from_db()
        self.assertEqual(lead.etapa_conversacion, Lead.ETAPA_RESERVADO)
        self.assertEqual(lead.estado, Lead.ASIGNADO)
        self.assertIn("yape", reply.lower())
        self.assertIn("996797907", reply)
        self.assertIn("19409223621088", reply)
        self.assertNotIn("ascensor", reply.lower())
        self.assertNotIn("escalera", reply.lower())
        self.assertNotIn("piso", reply.lower())

    @patch("apps.ia.conversation_engine.generate_reply")
    def test_consulta_titular_cuenta_responde_dato_verificado(self, ai_mock):
        cliente = Cliente.objects.create(telefono="51955550050")
        Lead.objects.create(
            cliente=cliente,
            etapa_conversacion=Lead.ETAPA_RESERVADO,
            estado=Lead.ASIGNADO,
            precio_cotizado=Decimal("286"),
            precio_final=Decimal("286"),
        )

        reply = handle_incoming_message(
            cliente,
            "la cuenta tambien sale al mismo nombre?",
        )

        self.assertIn("si", reply.lower())
        self.assertIn("cuenta bcp", reply.lower())
        self.assertIn("walter escobar", reply.lower())
        ai_mock.assert_not_called()

    @patch("apps.ia.conversation_engine.generate_reply")
    def test_consulta_libre_despues_de_reservar_usa_openai(self, ai_mock):
        ai_mock.return_value = (
            "El conductor te escribira cuando este cerca de la direccion."
        )
        cliente = Cliente.objects.create(telefono="51955550051")
        lead = Lead.objects.create(
            cliente=cliente,
            etapa_conversacion=Lead.ETAPA_RESERVADO,
            estado=Lead.ASIGNADO,
            direccion_origen="Av. Uno 123",
            direccion_destino="Av. Dos 456",
            fecha_servicio=timezone.localdate() + timedelta(days=1),
            horario_servicio="10:00 am",
            precio_cotizado=Decimal("286"),
            precio_final=Decimal("286"),
        )

        reply = handle_incoming_message(
            cliente,
            "me avisan cuando esten llegando?",
        )

        lead.refresh_from_db()
        self.assertEqual(lead.etapa_conversacion, Lead.ETAPA_RESERVADO)
        self.assertEqual(lead.estado, Lead.ASIGNADO)
        self.assertIn("conductor", reply.lower())
        prompt = ai_mock.call_args.args[0][0]["content"]
        self.assertIn("servicio ya esta reservado", prompt.lower())
        self.assertIn("no vuelvas a pedir", prompt.lower())

    def test_reserva_rechaza_distritos_como_direcciones_exactas(self):
        cliente = Cliente.objects.create(
            telefono="51955550035",
            nombre="Walter Escobar",
        )
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            etapa_conversacion=Lead.ETAPA_RESERVA,
            estado=Lead.COTIZADO,
            dni_reserva="12345678",
            precio_cotizado=Decimal("160"),
        )

        reply = handle_incoming_message(cliente, "surco y la molina")

        lead.refresh_from_db()
        self.assertEqual(lead.direccion_origen, "")
        self.assertEqual(lead.direccion_destino, "")
        self.assertIn("direccion mas precisa", reply.lower())
        self.assertIn("numero", reply.lower())

    def test_reserva_guarda_nombre_y_dni_en_una_respuesta(self):
        cliente = Cliente.objects.create(telefono="51955550038")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            etapa_conversacion=Lead.ETAPA_RESERVA,
            estado=Lead.COTIZADO,
            precio_cotizado=Decimal("160"),
        )

        reply = handle_incoming_message(cliente, "Walter Escobar, DNI 12345678")

        cliente.refresh_from_db()
        lead.refresh_from_db()
        self.assertEqual(cliente.nombre, "Walter Escobar")
        self.assertEqual(lead.dni_reserva, "12345678")
        self.assertIn("direcciones", reply.lower())

    def test_reserva_guarda_dos_direcciones_en_una_respuesta(self):
        cliente = Cliente.objects.create(
            telefono="51955550036",
            nombre="Walter Escobar",
        )
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            etapa_conversacion=Lead.ETAPA_RESERVA,
            estado=Lead.COTIZADO,
            dni_reserva="12345678",
            precio_cotizado=Decimal("160"),
        )

        reply = handle_incoming_message(
            cliente,
            "Partida: Av. Primavera 123, Surco. "
            "Llegada: Calle Los Pinos 456, La Molina",
        )

        lead.refresh_from_db()
        self.assertIn("Primavera 123", lead.direccion_origen)
        self.assertIn("Los Pinos 456", lead.direccion_destino)
        self.assertIn("fecha", reply.lower())
        self.assertIn("hora", reply.lower())

    def test_reserva_rechaza_fecha_pasada(self):
        cliente = Cliente.objects.create(
            telefono="51955550037",
            nombre="Walter Escobar",
        )
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            direccion_origen="Av. Primavera 123, Surco",
            direccion_destino="Calle Los Pinos 456, La Molina",
            etapa_conversacion=Lead.ETAPA_RESERVA,
            estado=Lead.COTIZADO,
            dni_reserva="12345678",
            precio_cotizado=Decimal("160"),
        )
        yesterday = timezone.localdate() - timedelta(days=1)

        reply = handle_incoming_message(
            cliente,
            f"{yesterday:%d/%m/%Y} a las 6:00 pm",
        )

        lead.refresh_from_db()
        self.assertIsNone(lead.fecha_servicio)
        self.assertEqual(lead.horario_servicio, "")
        self.assertNotEqual(lead.etapa_conversacion, Lead.ETAPA_RESERVADO)
        self.assertIn("ya paso", reply.lower())

    def test_reserva_rechaza_hora_pasada_de_hoy(self):
        cliente = Cliente.objects.create(
            telefono="51955550039",
            nombre="Walter Escobar",
        )
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            direccion_origen="Av. Primavera 123, Surco",
            direccion_destino="Calle Los Pinos 456, La Molina",
            etapa_conversacion=Lead.ETAPA_RESERVA,
            estado=Lead.COTIZADO,
            dni_reserva="12345678",
            precio_cotizado=Decimal("160"),
        )
        past_time = timezone.localtime() - timedelta(minutes=5)

        reply = handle_incoming_message(
            cliente,
            f"hoy a las {past_time:%I:%M %p}",
        )

        lead.refresh_from_db()
        self.assertIsNone(lead.fecha_servicio)
        self.assertEqual(lead.horario_servicio, "")
        self.assertNotEqual(lead.etapa_conversacion, Lead.ETAPA_RESERVADO)
        self.assertIn("ya paso", reply.lower())

    def test_dia_de_semana_se_confirma_antes_de_reservar(self):
        cliente = Cliente.objects.create(
            telefono="51955550049",
            nombre="Walter Escobar",
        )
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            direccion_origen="Calle El Manzano 120, Surco",
            direccion_destino="Calle La Molina 150, La Molina",
            etapa_conversacion=Lead.ETAPA_RESERVA,
            estado=Lead.COTIZADO,
            dni_reserva="12345678",
            precio_cotizado=Decimal("286"),
        )
        expected = timezone.localdate() + timedelta(
            days=(0 - timezone.localdate().weekday()) % 7
        )
        candidate = timezone.make_aware(
            timezone.datetime.combine(expected, timezone.datetime.strptime("10:00 am", "%I:%M %p").time()),
            timezone.get_current_timezone(),
        )
        if candidate <= timezone.now():
            expected += timedelta(days=7)

        confirmation = handle_incoming_message(cliente, "lunes a las 10 am")

        lead.refresh_from_db()
        self.assertEqual(lead.fecha_servicio, expected)
        self.assertEqual(lead.horario_servicio, "10:00 am")
        self.assertTrue(lead.horario_por_confirmar)
        self.assertEqual(lead.etapa_conversacion, Lead.ETAPA_RESERVA)
        self.assertIn(f"{expected.day:02d} de", confirmation.lower())
        self.assertIn("10:00 am", confirmation.lower())

        reply = handle_incoming_message(cliente, "si")

        lead.refresh_from_db()
        self.assertFalse(lead.horario_por_confirmar)
        self.assertEqual(lead.etapa_conversacion, Lead.ETAPA_RESERVA)
        self.assertTrue(lead.requiere_asesor)
        self.assertIn("asesor", reply.lower())

    def test_pregunta_solo_parte_faltante_del_acceso(self):
        cliente = Cliente.objects.create(telefono="51955550003")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            lista_objetos="cama y cajas",
        )

        reply = handle_incoming_message(cliente, "sale del piso 2 si hay ascensor")

        lead = cliente.leads.first()
        self.assertEqual(lead.piso_origen, 2)
        self.assertTrue(lead.ascensor_origen)
        self.assertIsNone(lead.camion_llega_origen)
        self.assertIn("a que piso llega", reply.lower())
        self.assertIn("piso", reply.lower())

        reply = handle_incoming_message(
            cliente,
            "en el destino llega al primer piso",
        )

        lead.refresh_from_db()
        self.assertEqual(lead.piso_destino, 1)
        self.assertIn("camion", reply.lower())

    def test_pregunta_un_solo_componente_pendiente_por_turno(self):
        cliente = Cliente.objects.create(telefono="51955550004")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            piso_origen=2,
            ascensor_origen=True,
            camion_llega_origen=True,
        )

        reply = handle_incoming_message(cliente, "en el destino no hay ascensor")

        lead = cliente.leads.first()
        self.assertFalse(lead.ascensor_destino)
        self.assertIn("cosas", reply.lower())
        self.assertNotIn("camion", reply.lower())

        reply = handle_incoming_message(cliente, "piso 3")

        lead.refresh_from_db()
        self.assertEqual(lead.piso_destino, 3)
        self.assertIn("cosas", reply.lower())

    def test_cotiza_sin_fecha_si_cliente_solo_esta_cotizando(self):
        cliente = Cliente.objects.create(telefono="51955550005")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            piso_origen=2,
            piso_destino=1,
            ascensor_origen=True,
            ascensor_destino=False,
            camion_llega_origen=True,
            camion_llega_destino=True,
            lista_objetos="cama, refrigeradora y cajas",
            incluye_personal_carga=True,
            modalidad_servicio="sin embalaje",
            requiere_desarmado=False,
        )

        reply = handle_incoming_message(
            cliente,
            "recien estoy cotizando, no tengo fecha",
        )

        lead = cliente.leads.first()
        self.assertTrue(lead.fecha_por_confirmar)
        self.assertIsNone(lead.fecha_servicio)
        self.assertEqual(lead.estado, Lead.COTIZADO)
        self.assertIn("costo", reply.lower())

    def test_cotiza_si_cliente_no_esta_seguro_de_la_fecha(self):
        cliente = Cliente.objects.create(telefono="51955550021")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            piso_origen=1,
            piso_destino=1,
            lista_objetos="refrigeradora y estante",
            incluye_personal_carga=True,
            modalidad_servicio="sin embalaje",
            requiere_desarmado=False,
        )

        reply = handle_incoming_message(
            cliente,
            "aun no estoy seguro de la fecha, solo quiero el precio",
        )

        lead = cliente.leads.first()
        self.assertTrue(lead.fecha_por_confirmar)
        self.assertEqual(lead.estado, Lead.COTIZADO)
        self.assertIn("costo", reply.lower())
        self.assertNotIn("para que fecha", reply.lower())

    def test_no_repite_fecha_si_cliente_responde_otra_cosa(self):
        cliente = Cliente.objects.create(telefono="51955550031")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            piso_origen=1,
            piso_destino=1,
            lista_objetos="refrigeradora y estante",
            incluye_personal_carga=True,
            modalidad_servicio="sin embalaje",
            requiere_desarmado=False,
        )

        reply = handle_incoming_message(cliente, "hola")

        lead = cliente.leads.first()
        self.assertTrue(lead.fecha_por_confirmar)
        self.assertEqual(lead.estado, Lead.COTIZADO)
        self.assertIn("costo", reply.lower())
        self.assertNotIn("para que fecha", reply.lower())

    def test_no_repite_fecha_ante_respuesta_con_error_ortografico(self):
        cliente = Cliente.objects.create(telefono="51955550032")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            piso_origen=1,
            piso_destino=1,
            lista_objetos="refrigeradora y estante",
            incluye_personal_carga=True,
            modalidad_servicio="sin embalaje",
            requiere_desarmado=False,
        )

        reply = handle_incoming_message(cliente, "aun no lose")

        lead = cliente.leads.first()
        self.assertTrue(lead.fecha_por_confirmar)
        self.assertEqual(lead.estado, Lead.COTIZADO)
        self.assertIn("costo", reply.lower())
        self.assertNotIn("para que fecha", reply.lower())

    def test_pregunta_de_embalaje_incluye_descripciones_breves(self):
        cliente = Cliente.objects.create(telefono="51955550022")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            piso_origen=1,
            piso_destino=1,
            lista_objetos="refrigeradora y estante",
        )

        reply = handle_incoming_message(cliente, "con ayudantes")

        self.assertIn("costo", reply.lower())

    def test_muestra_solo_precio_alto_al_cliente(self):
        cliente = Cliente.objects.create(telefono="51955550023")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            piso_origen=1,
            piso_destino=1,
            lista_objetos="refrigeradora y estante",
            incluye_personal_carga=True,
            modalidad_servicio="sin embalaje",
            requiere_desarmado=False,
        )

        reply = handle_incoming_message(
            cliente,
            "solo estoy cotizando, no tengo fecha",
        )

        lead.refresh_from_db()
        self.assertEqual(lead.precio_cotizado, lead.precio_estimado_max)
        self.assertIn(f"s/ {lead.precio_estimado_max:.0f}", reply.lower())
        self.assertNotIn("entre", reply.lower())
        self.assertNotIn(f"s/ {lead.precio_estimado_min:.0f}", reply.lower())

    def test_negocia_en_pasos_sin_bajar_del_minimo(self):
        cliente = Cliente.objects.create(telefono="51955550024")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("180"),
            precio_recomendado=Decimal("200"),
            precio_estimado_max=Decimal("240"),
            precio_cotizado=Decimal("240"),
        )

        first = handle_incoming_message(cliente, "esta caro, me haces descuento?")
        lead.refresh_from_db()
        self.assertEqual(lead.precio_cotizado, Decimal("220"))
        self.assertIn("s/ 220", first.lower())

        handle_incoming_message(cliente, "puedes mejorar un poco mas?")
        final = handle_incoming_message(cliente, "otro descuento")
        lead.refresh_from_db()
        self.assertEqual(lead.precio_cotizado, Decimal("180"))
        self.assertIn("s/ 180", final.lower())

        floor_reply = handle_incoming_message(cliente, "algo menos")
        lead.refresh_from_db()
        self.assertEqual(lead.precio_cotizado, Decimal("180"))
        self.assertIn("mejor precio", floor_reply.lower())

    def test_me_parece_muy_elevado_negocia_en_lugar_de_reservar(self):
        cliente = Cliente.objects.create(telefono="51955550043")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("274.50"),
            precio_recomendado=Decimal("305"),
            precio_estimado_max=Decimal("366"),
            precio_cotizado=Decimal("366"),
        )

        reply = handle_incoming_message(cliente, "me parece muy elevado")

        lead.refresh_from_db()
        self.assertEqual(lead.etapa_conversacion, Lead.ETAPA_COTIZACION)
        self.assertEqual(lead.precio_cotizado, Decimal("326"))
        self.assertIn("descuento", reply.lower())
        self.assertIn("s/ 326", reply.lower())
        self.assertIn("reserv", reply.lower())
        self.assertNotIn("dni", reply.lower())

    def test_objeciones_equivalentes_se_interpretan_como_precio(self):
        for index, objection in enumerate(
            ["es demasiado", "esta fuera de mi presupuesto", "se me hace mucho"],
            start=44,
        ):
            cliente = Cliente.objects.create(telefono=f"519555500{index}")
            lead = Lead.objects.create(
                cliente=cliente,
                tipo_servicio="traslado pequeno",
                estado=Lead.COTIZADO,
                precio_estimado_min=Decimal("180"),
                precio_recomendado=Decimal("200"),
                precio_estimado_max=Decimal("240"),
                precio_cotizado=Decimal("240"),
            )

            reply = handle_incoming_message(cliente, objection)

            lead.refresh_from_db()
            self.assertEqual(lead.precio_cotizado, Decimal("220"))
            self.assertIn("s/ 220", reply.lower())

    def test_no_me_parece_negocia_y_reserva_con_el_ultimo_precio(self):
        cliente = Cliente.objects.create(
            telefono="51955550048",
            nombre="Walter Escobar",
        )
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("274.50"),
            precio_recomendado=Decimal("305"),
            precio_estimado_max=Decimal("366"),
            precio_cotizado=Decimal("326"),
        )

        discount_reply = handle_incoming_message(cliente, "no me parece")

        lead.refresh_from_db()
        self.assertEqual(lead.precio_cotizado, Decimal("286"))
        self.assertIn("s/ 286", discount_reply.lower())

        reservation_reply = handle_incoming_message(
            cliente,
            "ok. qyuiero reservar",
        )

        lead.refresh_from_db()
        self.assertEqual(lead.precio_cotizado, Decimal("286"))
        self.assertEqual(lead.etapa_conversacion, Lead.ETAPA_RESERVA)
        self.assertIn("direcciones", reservation_reply.lower())
        self.assertNotIn("s/ 366", reservation_reply.lower())

    def test_saludo_despues_del_precio_ofrece_una_rebaja(self):
        cliente = Cliente.objects.create(telefono="51955550033")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("135"),
            precio_recomendado=Decimal("150"),
            precio_estimado_max=Decimal("180"),
            precio_cotizado=Decimal("180"),
        )

        reply = handle_incoming_message(cliente, "hol")

        lead.refresh_from_db()
        self.assertEqual(lead.precio_cotizado, Decimal("160"))
        self.assertIn("s/ 160", reply.lower())
        self.assertIn("reserv", reply.lower())
        self.assertNotIn("s/ 180", reply.lower())

    def test_otro_saludo_no_aplica_descuentos_sucesivos(self):
        cliente = Cliente.objects.create(telefono="51955550034")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("135"),
            precio_recomendado=Decimal("150"),
            precio_estimado_max=Decimal("180"),
            precio_cotizado=Decimal("160"),
        )

        reply = handle_incoming_message(cliente, "hola")

        lead.refresh_from_db()
        self.assertEqual(lead.precio_cotizado, Decimal("160"))
        self.assertIn("detalle", reply.lower())
        self.assertNotIn("s/ 160", reply.lower())

    def test_acepta_contraoferta_dentro_del_rango(self):
        cliente = Cliente.objects.create(telefono="51955550025")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("180"),
            precio_recomendado=Decimal("200"),
            precio_estimado_max=Decimal("240"),
            precio_cotizado=Decimal("240"),
        )

        reply = handle_incoming_message(cliente, "te doy 200")

        lead.refresh_from_db()
        self.assertEqual(lead.precio_cotizado, Decimal("200"))
        self.assertIn("podemos dejar", reply.lower())

    def test_contraoferta_menor_recibe_el_precio_minimo(self):
        cliente = Cliente.objects.create(telefono="51955550026")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("180"),
            precio_recomendado=Decimal("200"),
            precio_estimado_max=Decimal("240"),
            precio_cotizado=Decimal("240"),
        )

        reply = handle_incoming_message(cliente, "te doy 140")

        lead.refresh_from_db()
        self.assertEqual(lead.precio_cotizado, Decimal("180"))
        self.assertIn("minimo", reply.lower())
        self.assertIn("s/ 180", reply.lower())

    def test_te_aviso_pregunta_el_motivo_sin_repetir_precio(self):
        cliente = Cliente.objects.create(telefono="51955550027")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("180"),
            precio_recomendado=Decimal("200"),
            precio_estimado_max=Decimal("240"),
            precio_cotizado=Decimal("240"),
        )

        reply = handle_incoming_message(cliente, "te aviso")

        lead.refresh_from_db()
        self.assertTrue(lead.esperando_motivo_no_reserva)
        self.assertIn("que te detiene", reply.lower())
        self.assertIn("precio", reply.lower())
        self.assertIn("fecha", reply.lower())
        self.assertNotIn("s/ 240", reply.lower())

    def test_motivo_precio_aplica_descuento_contextual(self):
        cliente = Cliente.objects.create(telefono="51955550028")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("180"),
            precio_recomendado=Decimal("200"),
            precio_estimado_max=Decimal("240"),
            precio_cotizado=Decimal("240"),
            esperando_motivo_no_reserva=True,
        )

        reply = handle_incoming_message(cliente, "es por el precio")

        lead.refresh_from_db()
        self.assertFalse(lead.esperando_motivo_no_reserva)
        self.assertEqual(lead.precio_cotizado, Decimal("220"))
        self.assertIn("s/ 220", reply.lower())
        self.assertIn("te serviria", reply.lower())

    def test_motivo_fecha_no_aplica_descuento(self):
        cliente = Cliente.objects.create(telefono="51955550029")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("180"),
            precio_recomendado=Decimal("200"),
            precio_estimado_max=Decimal("240"),
            precio_cotizado=Decimal("240"),
            esperando_motivo_no_reserva=True,
        )

        reply = handle_incoming_message(cliente, "todavia no tengo fecha")

        lead.refresh_from_db()
        self.assertFalse(lead.esperando_motivo_no_reserva)
        self.assertTrue(lead.fecha_por_confirmar)
        self.assertEqual(lead.precio_cotizado, Decimal("240"))
        self.assertIn("cuando tengas la fecha", reply.lower())

    def test_limpia_cotizacion_anterior_si_cambian_datos_operativos(self):
        cliente = Cliente.objects.create(telefono="51955550006")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            piso_origen=2,
            ascensor_origen=True,
            camion_llega_origen=True,
            precio_estimado_min=Decimal("300.00"),
            precio_estimado_max=Decimal("450.00"),
            precio_recomendado=Decimal("380.00"),
        )

        handle_incoming_message(cliente, "piso 3")

        lead.refresh_from_db()
        self.assertEqual(lead.piso_destino, 3)
        self.assertIsNone(lead.precio_estimado_min)
        self.assertIsNone(lead.precio_estimado_max)
        self.assertIsNone(lead.precio_recomendado)

    def test_piano_no_se_interpreta_como_respuesta_negativa(self):
        cliente = Cliente.objects.create(telefono="51955550007")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            piso_origen=2,
            piso_destino=3,
            ascensor_origen=True,
            ascensor_destino=False,
            camion_llega_origen=True,
            camion_llega_destino=True,
            lista_objetos="piano y cajas",
            incluye_personal_carga=True,
            modalidad_servicio="solo traslado",
            fecha_servicio=timezone.localdate(),
        )

        handle_incoming_message(cliente, "si, hay que desarmar el piano")

        lead = cliente.leads.first()
        self.assertTrue(lead.requiere_desarmado)

    def test_personal_para_cargar_no_desvia_el_flujo_a_peso_de_carga(self):
        cliente = Cliente.objects.create(telefono="51955550008")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Miraflores",
            piso_origen=1,
            piso_destino=1,
            ascensor_origen=False,
            ascensor_destino=False,
            camion_llega_origen=True,
            camion_llega_destino=True,
            lista_objetos="un escritorio, una silla y una PC",
        )

        reply = handle_incoming_message(cliente, "con personal para cargar")

        lead = cliente.leads.first()
        self.assertEqual(lead.tipo_servicio, "mudanza")
        self.assertTrue(lead.incluye_personal_carga)
        self.assertIn("costo", reply.lower())
        self.assertNotIn("peso", reply.lower())

    def test_referencia_a_foto_no_se_guarda_como_inventario(self):
        cliente = Cliente.objects.create(telefono="51955550009")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Miraflores",
            piso_origen=1,
            piso_destino=1,
            ascensor_origen=False,
            ascensor_destino=False,
            camion_llega_origen=True,
            camion_llega_destino=True,
        )

        reply = handle_incoming_message(cliente, "es lo que ves")

        lead = cliente.leads.first()
        self.assertEqual(lead.lista_objetos, "")
        self.assertIn("cosas", reply.lower())

    def test_explica_embalaje_sin_tomarlo_como_eleccion(self):
        cliente = Cliente.objects.create(telefono="51955550010")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Miraflores",
            piso_origen=1,
            piso_destino=1,
            ascensor_origen=False,
            ascensor_destino=False,
            camion_llega_origen=True,
            camion_llega_destino=True,
            lista_objetos="escritorio, silla y PC",
            incluye_personal_carga=True,
        )

        reply = handle_incoming_message(cliente, "que incluye el embalaje basico?")

        lead = cliente.leads.first()
        self.assertEqual(lead.modalidad_servicio, "")
        self.assertIn("stretch film", reply.lower())
        self.assertIn("ropa", reply.lower())

    def test_primer_piso_no_pregunta_por_ascensor(self):
        cliente = Cliente.objects.create(telefono="51955550011")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Miraflores",
        )

        reply = handle_incoming_message(cliente, "sale del primer piso")

        lead = cliente.leads.first()
        self.assertEqual(lead.piso_origen, 1)
        self.assertIsNone(lead.ascensor_origen)
        self.assertIn("cosas", reply.lower())
        self.assertNotIn("ascensor", reply.lower())
        self.assertNotIn("escalera", reply.lower())

    def test_segundo_piso_exige_ascensor_o_escaleras(self):
        cliente = Cliente.objects.create(telefono="51955550012")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Miraflores",
        )

        reply = handle_incoming_message(cliente, "sale del segundo piso")

        lead = cliente.leads.first()
        self.assertEqual(lead.piso_origen, 2)
        self.assertIsNone(lead.ascensor_origen)
        self.assertIn("cosas", reply.lower())

    def test_carga_tambien_exige_pisos_antes_de_cotizar(self):
        cliente = Cliente.objects.create(telefono="51955550013")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="carga",
            distrito_origen="Lima",
            distrito_destino="Callao",
            lista_objetos="20 cajas",
            peso_carga_kg=Decimal("200"),
        )

        reply = handle_incoming_message(cliente, "el camion llega a la puerta")

        lead = cliente.leads.first()
        self.assertNotEqual(lead.estado, Lead.COTIZADO)
        self.assertIn("piso", reply.lower())

    def test_ruta_a_provincia_no_usa_precio_local_automatico(self):
        cliente = Cliente.objects.create(telefono="51955550014")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Huancayo",
            piso_origen=1,
            piso_destino=1,
            camion_llega_origen=True,
            camion_llega_destino=True,
            lista_objetos="refrigeradora y estante",
            incluye_personal_carga=True,
            modalidad_servicio="sin embalaje",
            requiere_desarmado=False,
        )

        reply = handle_incoming_message(cliente, "todavia no tengo fecha")

        lead = cliente.leads.first()
        self.assertTrue(lead.atencion_humana)
        self.assertNotEqual(lead.estado, Lead.COTIZADO)
        self.assertIsNone(lead.precio_recomendado)
        self.assertIn("fuera de lima", reply.lower())
        self.assertIn("peajes", reply.lower())

    def test_pide_origen_y_destino_en_una_sola_pregunta(self):
        cliente = Cliente.objects.create(telefono="51955550015")

        reply = handle_incoming_message(cliente, "quiero una mudanza")

        self.assertIn("partida", reply.lower())
        self.assertIn("llegada", reply.lower())

        reply = handle_incoming_message(
            cliente,
            "sale de Surco y llega a La Molina",
        )

        lead = cliente.leads.first()
        self.assertEqual(lead.distrito_origen, "Surco")
        self.assertEqual(lead.distrito_destino, "La Molina")
        self.assertIn("cosas", reply.lower())

    def test_pisos_no_reemplazan_la_ruta(self):
        cliente = Cliente.objects.create(telefono="51955550016")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
        )

        reply = handle_incoming_message(
            cliente,
            "sale de primer piso y llega a primer piso",
        )

        lead = cliente.leads.first()
        self.assertEqual(lead.distrito_origen, "Surco")
        self.assertEqual(lead.distrito_destino, "La Molina")
        self.assertEqual(lead.piso_origen, 1)
        self.assertEqual(lead.piso_destino, 1)
        self.assertIn("cosas", reply.lower())

    def test_respuesta_1ero_a_1ero_completa_ambos_pisos(self):
        cliente = Cliente.objects.create(telefono="51955550030")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            lista_objetos="cosas de una habitacion",
        )

        reply = handle_incoming_message(cliente, "1ero a 1ero")

        lead = cliente.leads.first()
        self.assertEqual(lead.piso_origen, 1)
        self.assertEqual(lead.piso_destino, 1)
        self.assertIn("costo", reply.lower())
        self.assertNotIn("piso", reply.lower())
        self.assertNotIn("camion", reply.lower())

    def test_pisos_con_error_opiso_se_interpretan_como_par(self):
        cliente = Cliente.objects.create(telefono="51955550041")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Miraflores",
            distrito_destino="San Miguel",
            lista_objetos="cama, colchon y tarima",
        )

        reply = handle_incoming_message(cliente, "1er opiso a 3er piso")

        lead = cliente.leads.first()
        self.assertEqual(lead.piso_origen, 1)
        self.assertEqual(lead.piso_destino, 3)
        self.assertIsNone(lead.ascensor_origen)
        self.assertIsNone(lead.ascensor_destino)
        self.assertIn("destino", reply.lower())
        self.assertIn("ascensor", reply.lower())
        self.assertNotIn("origen", reply.lower())
        self.assertNotIn("en en", reply.lower())

    def test_escaleras_se_asigna_al_unico_punto_pendiente(self):
        cliente = Cliente.objects.create(telefono="51955550042")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Miraflores",
            distrito_destino="San Miguel",
            piso_origen=1,
            piso_destino=3,
            lista_objetos="cama, colchon y tarima",
        )

        reply = handle_incoming_message(cliente, "escaleras")

        lead = cliente.leads.first()
        self.assertIsNone(lead.ascensor_origen)
        self.assertFalse(lead.ascensor_destino)
        self.assertNotIn("ascensor", reply.lower())
        self.assertNotIn("escalera", reply.lower())
        self.assertNotIn("piso", reply.lower())
        self.assertNotIn("camion", reply.lower())
        self.assertIn("costo", reply.lower())

    def test_traslado_pequeno_omite_acceso_del_camion(self):
        cliente = Cliente.objects.create(telefono="51955550017")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            piso_origen=1,
            piso_destino=1,
        )

        reply = handle_incoming_message(
            cliente,
            "una refrigeradora y un estante",
        )

        self.assertIn("costo", reply.lower())
        self.assertNotIn("camion", reply.lower())

    def test_mudanza_mediana_si_pregunta_acceso_del_camion(self):
        cliente = Cliente.objects.create(telefono="51955550018")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            piso_origen=1,
            piso_destino=1,
        )

        reply = handle_incoming_message(
            cliente,
            "cama, sofa, refrigeradora, lavadora y 12 cajas",
        )

        self.assertIn("camion", reply.lower())
        self.assertIn("origen", reply.lower())
        self.assertIn("destino", reply.lower())

    def test_no_repregunta_pisos_ni_camion_en_traslado_pequeno(self):
        cliente = Cliente.objects.create(telefono="51955550019")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            piso_origen=1,
            piso_destino=1,
            lista_objetos="refrigeradora y estante",
            incluye_personal_carga=True,
        )

        reply = handle_incoming_message(cliente, "no necesito embalaje")

        lead = cliente.leads.first()
        self.assertEqual(lead.modalidad_servicio, "sin embalaje")
        self.assertIn("costo", reply.lower())
        self.assertNotIn("camion", reply.lower())
        self.assertNotIn("piso", reply.lower())
        self.assertNotIn("ascensor", reply.lower())
        self.assertNotIn("escalera", reply.lower())

    def test_continua_el_lead_mas_reciente(self):
        cliente = Cliente.objects.create(telefono="51955550020")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            piso_origen=2,
            piso_destino=2,
            ascensor_origen=True,
            ascensor_destino=True,
            lista_objetos="cama y cajas",
            estado=Lead.COTIZADO,
        )
        recent = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Lince",
            distrito_destino="Miraflores",
            piso_origen=1,
            piso_destino=1,
            lista_objetos="una silla",
        )

        reply = handle_incoming_message(cliente, "con ayudante")

        recent.refresh_from_db()
        self.assertTrue(recent.incluye_personal_carga)
        self.assertIn("costo", reply.lower())

    def test_con_embalaje_sin_especificar_cotiza_basico(self):
        cliente = Cliente.objects.create(telefono="51955550030")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            piso_origen=1,
            piso_destino=1,
            lista_objetos="refrigeradora",
            incluye_personal_carga=True,
        )

        reply = handle_incoming_message(cliente, "con embalaje")

        lead = cliente.leads.first()
        self.assertEqual(lead.modalidad_servicio, "embalaje basico")

    def test_con_embalaje_cuanto_seria_cotiza_basico(self):
        cliente = Cliente.objects.create(telefono="51955550031")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            piso_origen=1,
            piso_destino=1,
            lista_objetos="refrigeradora",
            incluye_personal_carga=True,
            requiere_desarmado=False,
            fecha_por_confirmar=True,
        )

        reply = handle_incoming_message(cliente, "con embalaje cuanto seria?")

        lead = cliente.leads.first()
        self.assertEqual(lead.modalidad_servicio, "embalaje basico")
        self.assertEqual(lead.estado, Lead.COTIZADO)
        self.assertIn("costo", reply.lower())

    def test_embalaje_muebles_y_artefactos_cotiza_automaticamente(self):
        cliente = Cliente.objects.create(telefono="51955550032")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Miraflores",
            piso_origen=1,
            piso_destino=1,
            ascensor_origen=False,
            ascensor_destino=False,
            camion_llega_origen=True,
            camion_llega_destino=True,
            lista_objetos="escritorio, silla y PC",
            incluye_personal_carga=True,
            requiere_desarmado=False,
            fecha_por_confirmar=True,
        )

        reply = handle_incoming_message(cliente, "embalaje de muebles y artefactos")

        lead = cliente.leads.first()
        self.assertEqual(lead.modalidad_servicio, "embalaje de muebles y artefactos")
        self.assertEqual(lead.estado, Lead.COTIZADO)
        self.assertIn("costo", reply.lower())

    def test_embalaje_full_pide_fotos_y_deriva_a_asesor(self):
        cliente = Cliente.objects.create(telefono="51955550033")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Miraflores",
            piso_origen=1,
            piso_destino=1,
            ascensor_origen=False,
            ascensor_destino=False,
            camion_llega_origen=True,
            camion_llega_destino=True,
            lista_objetos="escritorio, silla y PC",
            incluye_personal_carga=True,
        )

        reply = handle_incoming_message(cliente, "quiero embalaje full")

        lead = cliente.leads.first()
        self.assertEqual(lead.modalidad_servicio, "embalaje full")
        self.assertTrue(lead.atencion_humana)
        self.assertIn("fotos", reply.lower())
        self.assertIn("asesor", reply.lower())
        self.assertNotEqual(lead.estado, Lead.COTIZADO)

    def test_precio_incluye_embalaje_full_respuesta_informativa(self):
        cliente = Cliente.objects.create(telefono="51955550034")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            modalidad_servicio="embalaje basico",
            precio_estimado_min=Decimal("180"),
            precio_estimado_max=Decimal("240"),
            precio_cotizado=Decimal("240"),
        )

        reply = handle_incoming_message(
            cliente, "ese precio incluye embalaje full?"
        )

        lead.refresh_from_db()
        self.assertEqual(lead.modalidad_servicio, "embalaje basico")
        self.assertIn("embalaje basico", reply.lower())
        self.assertIn("full", reply.lower())

    def test_consulta_tipo_embalaje_actual(self):
        cliente = Cliente.objects.create(telefono="51955550035")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            modalidad_servicio="embalaje basico",
            precio_estimado_min=Decimal("180"),
            precio_estimado_max=Decimal("240"),
            precio_cotizado=Decimal("240"),
        )

        reply = handle_incoming_message(
            cliente, "quiero saber si el embalaje es basico o full"
        )

        lead.refresh_from_db()
        self.assertEqual(lead.modalidad_servicio, "embalaje basico")
        self.assertEqual(lead.precio_cotizado, Decimal("240"))
        self.assertIn("embalaje basico", reply.lower())

    def test_disponibilidad_manana_sin_repetir_precio(self):
        cliente = Cliente.objects.create(telefono="51955550036")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("180"),
            precio_estimado_max=Decimal("240"),
            precio_cotizado=Decimal("240"),
        )

        reply = handle_incoming_message(cliente, "tienen disponibilidad para manana?")

        lead.refresh_from_db()
        self.assertEqual(lead.precio_cotizado, Decimal("240"))
        self.assertIn("hora", reply.lower())
        self.assertNotIn("240", reply)

    def test_rechazo_no_repite_precio(self):
        cliente = Cliente.objects.create(telefono="51955550037")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("180"),
            precio_estimado_max=Decimal("240"),
            precio_cotizado=Decimal("240"),
        )

        reply = handle_incoming_message(
            cliente, "no estoy interesado gracias"
        )

        lead.refresh_from_db()
        self.assertEqual(lead.estado, Lead.PERDIDO)
        self.assertEqual(lead.motivo_perdida, "Cliente no interesado / lo pensara")
        self.assertIn("quedamos atentos", reply.lower())
        self.assertNotIn("240", reply)
        self.assertNotIn("descuento", reply.lower())

    def test_segunda_objecion_no_restablece_precio_original(self):
        cliente = Cliente.objects.create(telefono="51955550050")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("800"),
            precio_estimado_max=Decimal("1146"),
            precio_cotizado=Decimal("1146"),
        )

        reply1 = handle_incoming_message(cliente, "es demasiado")

        lead.refresh_from_db()
        first_discounted = lead.precio_cotizado
        self.assertLess(first_discounted, 1146)
        self.assertIn(str(int(first_discounted)), reply1)

        reply2 = handle_incoming_message(cliente, "es mucho")

        lead.refresh_from_db()
        self.assertLessEqual(lead.precio_cotizado, first_discounted)
        self.assertNotIn("1146", reply2)

    def test_mejor_precio_disponible_si_ya_no_hay_margen(self):
        cliente = Cliente.objects.create(telefono="51955550051")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("800"),
            precio_estimado_max=Decimal("800"),
            precio_cotizado=Decimal("800"),
        )

        reply = handle_incoming_message(cliente, "es demasiado")

        lead.refresh_from_db()
        self.assertEqual(lead.precio_cotizado, 800)
        self.assertIn("mejor precio", reply.lower())
        self.assertIn("800", reply)

    def test_no_retrocede_precio_despues_de_descuento(self):
        cliente = Cliente.objects.create(telefono="51955550052")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("800"),
            precio_estimado_max=Decimal("1146"),
            precio_cotizado=Decimal("1026"),
        )

        reply = handle_incoming_message(cliente, "un momento")

        lead.refresh_from_db()
        self.assertEqual(lead.precio_cotizado, 1026)
        self.assertNotIn("1146", reply)

    def test_rechazo_despues_de_descuento_no_repite_precio(self):
        cliente = Cliente.objects.create(telefono="51955550053")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("800"),
            precio_estimado_max=Decimal("1146"),
            precio_cotizado=Decimal("1026"),
        )

        reply = handle_incoming_message(cliente, "no gracias")

        lead.refresh_from_db()
        self.assertEqual(lead.estado, Lead.PERDIDO)
        self.assertNotIn("1026", reply)
        self.assertNotIn("1146", reply)
        self.assertNotIn("reserva", reply.lower())

    def test_yo_le_aviso_cierra_sin_insistir(self):
        cliente = Cliente.objects.create(telefono="51955550038")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("180"),
            precio_estimado_max=Decimal("240"),
            precio_cotizado=Decimal("240"),
        )

        reply = handle_incoming_message(cliente, "yo le aviso cualquier cosa")

        lead.refresh_from_db()
        self.assertEqual(lead.estado, Lead.PERDIDO)
        self.assertEqual(lead.motivo_perdida, "Cliente no interesado / lo pensara")
        self.assertIn("quedamos atentos", reply.lower())
        self.assertNotIn("240", reply)
        self.assertNotIn("descuento", reply.lower())

    @patch("apps.ia.conversation_engine._ai_detects_new_quote")
    def test_nueva_cotizacion_despues_de_cotizado_crea_lead_nuevo(
        self, mock_ai_detect
    ):
        mock_ai_detect.return_value = True
        cliente = Cliente.objects.create(telefono="51955550039")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("180"),
            precio_estimado_max=Decimal("240"),
            precio_cotizado=Decimal("240"),
        )

        reply = handle_incoming_message(
            cliente, "quiero trasladar las cosas de un estudiante"
        )

        lead.refresh_from_db()
        self.assertEqual(lead.estado, Lead.PERDIDO)
        self.assertEqual(
            lead.motivo_perdida, "Cliente inicio nueva cotizacion"
        )
        new_lead = cliente.leads.filter(estado=Lead.DATOS_INCOMPLETOS).first()
        self.assertIsNotNone(new_lead)
        self.assertNotEqual(new_lead.id, lead.id)
        self.assertIn("distrito", reply.lower())

    def test_no_estoy_interesado_marca_perdido(self):
        cliente = Cliente.objects.create(telefono="51955550040")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("180"),
            precio_estimado_max=Decimal("240"),
            precio_cotizado=Decimal("240"),
        )

        reply = handle_incoming_message(cliente, "no estoy interesado")

        lead.refresh_from_db()
        self.assertEqual(lead.estado, Lead.PERDIDO)
        self.assertEqual(lead.motivo_perdida, "Cliente no interesado / lo pensara")
        self.assertIn("quedamos atentos", reply.lower())
        self.assertNotIn("240", reply)
        self.assertNotIn("descuento", reply.lower())
        self.assertNotIn("reserva", reply.lower())

    def test_gracias_solo_cierra_sin_repetir_precio(self):
        cliente = Cliente.objects.create(telefono="51955550041")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="traslado pequeno",
            estado=Lead.COTIZADO,
            precio_estimado_min=Decimal("180"),
            precio_estimado_max=Decimal("240"),
            precio_cotizado=Decimal("240"),
        )

        reply = handle_incoming_message(cliente, "gracias")

        lead.refresh_from_db()
        self.assertEqual(lead.estado, Lead.PERDIDO)
        self.assertEqual(lead.motivo_perdida, "Cliente no interesado / lo pensara")
        self.assertIn("quedamos atentos", reply.lower())
        self.assertNotIn("240", reply)
        self.assertNotIn("descuento", reply.lower())
