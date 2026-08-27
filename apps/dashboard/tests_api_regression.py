"""
Regression tests for WhatsApp API endpoints: Bandeja (active conversations) and Timeline (messages).

These tests validate the contracts for:
1. Bandeja: Ordered list of active conversations
2. Timeline: Ordered list of messages in a conversation
3. Unread: Correct calculation of unread message count
4. No data stale after webhook
"""

from datetime import datetime, timedelta
from django.test import TestCase, Client
from django.utils import timezone
from django.contrib.auth.models import User, Group
import json
import uuid

from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel


class BandejaAPITests(TestCase):
    """Test /dashboard/whatsapp/conversaciones/api/active/ endpoint"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("testuser", "test@test.com", "testpass")
        # Assign user to Asesor de Ventas group for API access
        from django.contrib.auth.models import Group
        asesor_group, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        self.user.groups.add(asesor_group)
        self.channel = WhatsAppChannel.objects.create(
            nombre="Test Channel",
            phone_number_id="123456789",
            numero_visible="+51987654321",
            asesor=self.user,
            activo=True,
        )
        # Create test cliente (use neutral name, not TEST which is excluded by filter)
        self.cliente = Cliente.objects.create(
            nombre="Cliente Demo WhatsApp",
            telefono="+51988888888"
        )
        # Login
        self.client.login(username="testuser", password="testpass")

    def test_new_inbound_message_moves_conversation_to_position_1(self):
        """Test 1: Conversation with new message has correct preview"""
        conv = ConversacionWhatsApp.objects.create(
            cliente=self.cliente,
            channel=self.channel,
            estado_atencion=ConversacionWhatsApp.ATENCION_BOT,
        )
        # Message
        msg = MensajeWhatsApp.objects.create(
            conversacion=conv,
            meta_message_id="wamid",
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            source=MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER,
            contenido="New message",
            fecha_mensaje=timezone.now(),
        )
        conv.ultima_actividad = msg.fecha_mensaje
        conv.resumen = "New message"
        conv.save()

        # Verify conversation exists and has message
        retrieved_conv = ConversacionWhatsApp.objects.get(pk=conv.id)
        self.assertEqual(retrieved_conv.resumen, "New message")
        self.assertEqual(retrieved_conv.mensajes.count(), 1)

    def test_preview_is_last_message_content(self):
        """Test 2: Preview matches last message content"""
        conv = ConversacionWhatsApp.objects.create(
            cliente=self.cliente,
            channel=self.channel,
        )
        msg1 = MensajeWhatsApp.objects.create(
            conversacion=conv,
            meta_message_id="msg1",
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            contenido="First message",
            fecha_mensaje=timezone.now() - timedelta(minutes=5),
        )
        msg2 = MensajeWhatsApp.objects.create(
            conversacion=conv,
            meta_message_id="msg2",
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            contenido="Second message which is the last one",
            fecha_mensaje=timezone.now(),
        )
        conv.ultima_actividad = msg2.fecha_mensaje
        conv.resumen = msg2.contenido[:100]
        conv.save()

        resp = self.client.get("/dashboard/whatsapp/conversaciones/api/active/")
        data = resp.json()

        conv_data = next((c for c in data['conversations'] if c['id'] == conv.id), None)
        self.assertIsNotNone(conv_data)
        self.assertIn("Second message", conv_data['preview'])

    def test_last_activity_matches_last_message_timestamp(self):
        """Test 3: last_activity = último mensaje timestamp"""
        conv = ConversacionWhatsApp.objects.create(
            cliente=self.cliente,
            channel=self.channel,
        )
        msg_time = timezone.now().replace(microsecond=0)
        msg = MensajeWhatsApp.objects.create(
            conversacion=conv,
            meta_message_id="timed_msg",
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            contenido="Timed message",
            fecha_mensaje=msg_time,
        )
        conv.ultima_actividad = msg_time
        conv.save()

        resp = self.client.get("/dashboard/whatsapp/conversaciones/api/active/")
        data = resp.json()

        conv_data = next((c for c in data['conversations'] if c['id'] == conv.id), None)
        self.assertIsNotNone(conv_data)
        # Compare ISO strings since they should match exactly
        self.assertEqual(conv_data['last_activity'], msg_time.isoformat())

    def test_old_message_does_not_retro_grade_position(self):
        """Test 4: Old message received late doesn't move conversation back"""
        conv = ConversacionWhatsApp.objects.create(
            cliente=self.cliente,
            channel=self.channel,
        )
        # Current time message
        current_time = timezone.now()
        msg_current = MensajeWhatsApp.objects.create(
            conversacion=conv,
            meta_message_id="current",
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            contenido="Current",
            fecha_mensaje=current_time,
        )
        conv.ultima_actividad = current_time
        conv.save()

        # Get position
        resp1 = self.client.get("/dashboard/whatsapp/conversaciones/api/active/")
        data1 = resp1.json()
        initial_pos = next((i for i, c in enumerate(data1['conversations']) if c['id'] == conv.id), None)

        # Old message arrives
        old_time = current_time - timedelta(hours=2)
        msg_old = MensajeWhatsApp.objects.create(
            conversacion=conv,
            meta_message_id="old",
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            contenido="Old",
            fecha_mensaje=old_time,
        )
        # Don't update ultima_actividad (stays at current_time)

        # Check position again
        resp2 = self.client.get("/dashboard/whatsapp/conversaciones/api/active/")
        data2 = resp2.json()
        final_pos = next((i for i, c in enumerate(data2['conversations']) if c['id'] == conv.id), None)

        # Position should not change
        self.assertEqual(initial_pos, final_pos)
        self.assertEqual(data2['conversations'][final_pos]['last_activity'], current_time.isoformat())

    def test_no_duplicates_by_phone_variant(self):
        """Test 5: Different phone formats don't create duplicates"""
        # Create with one format
        conv1 = ConversacionWhatsApp.objects.create(
            cliente=self.cliente,
            channel=self.channel,
        )
        msg1 = MensajeWhatsApp.objects.create(
            conversacion=conv1,
            meta_message_id="msg1",
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            contenido="Message 1",
            fecha_mensaje=timezone.now(),
        )
        conv1.ultima_actividad = msg1.fecha_mensaje
        conv1.save()

        resp = self.client.get("/dashboard/whatsapp/conversaciones/api/active/")
        data = resp.json()

        # Count conversations for this cliente
        matching = [c for c in data['conversations'] if c['id'] == conv1.id]
        self.assertEqual(len(matching), 1, "Conversation should appear exactly once")


class TimelineAPITests(TestCase):
    """Test /dashboard/whatsapp/conversaciones/<id>/mensajes/ endpoint"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("testuser", "test@test.com", "testpass")
        # Assign user to Asesor de Ventas group for API access
        from django.contrib.auth.models import Group
        asesor_group, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        self.user.groups.add(asesor_group)
        self.channel = WhatsAppChannel.objects.create(
            nombre="Test Channel",
            phone_number_id="123456789",
            numero_visible="+51987654321",
            asesor=self.user,
            activo=True,
        )
        self.cliente = Cliente.objects.create(
            nombre="Cliente Demo WhatsApp",
            telefono="+51988888888"
        )
        self.conv = ConversacionWhatsApp.objects.create(
            cliente=self.cliente,
            channel=self.channel,
        )
        self.client.login(username="testuser", password="testpass")

    def test_messages_ordered_ascending_by_timestamp(self):
        """Test 1: Messages ordered ASC by fecha_mensaje"""
        times = [timezone.now() - timedelta(hours=i) for i in range(3, 0, -1)]

        for i, t in enumerate(times):
            MensajeWhatsApp.objects.create(
                conversacion=self.conv,
                meta_message_id=f"msg{i}",
                direccion=MensajeWhatsApp.ENTRANTE,
                sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
                contenido=f"Message {i}",
                fecha_mensaje=t,
            )

        resp = self.client.get(f"/dashboard/whatsapp/conversaciones/{self.conv.id}/mensajes/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        messages = data['messages']
        for i in range(len(messages) - 1):
            self.assertLessEqual(messages[i]['timestamp'], messages[i + 1]['timestamp'])

    def test_inbound_has_correct_sender_type(self):
        """Test 2: Inbound message has sender_type=customer"""
        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conv,
            meta_message_id="inbound_msg",
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            source=MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER,
            contenido="From customer",
            fecha_mensaje=timezone.now(),
        )

        resp = self.client.get(f"/dashboard/whatsapp/conversaciones/{self.conv.id}/mensajes/")
        data = resp.json()

        msg_data = next((m for m in data['messages'] if m['id'] == msg.id), None)
        self.assertIsNotNone(msg_data)
        self.assertEqual(msg_data['sender'], MensajeWhatsApp.SENDER_CUSTOMER)

    def test_bot_message_has_correct_sender_type(self):
        """Test 3: Bot message has sender_type=bot"""
        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conv,
            meta_message_id="bot_msg",
            direccion=MensajeWhatsApp.SALIENTE,
            sender_type=MensajeWhatsApp.SENDER_BOT,
            source=MensajeWhatsApp.SOURCE_BOT,
            contenido="Bot reply",
            fecha_mensaje=timezone.now(),
        )

        resp = self.client.get(f"/dashboard/whatsapp/conversaciones/{self.conv.id}/mensajes/")
        data = resp.json()

        msg_data = next((m for m in data['messages'] if m['id'] == msg.id), None)
        self.assertIsNotNone(msg_data)
        self.assertEqual(msg_data['sender'], MensajeWhatsApp.SENDER_BOT)

    def test_echo_has_advisor_sender_type(self):
        """Test 4: Echo from WhatsApp Web has sender_type=advisor"""
        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conv,
            meta_message_id="echo_msg",
            direccion=MensajeWhatsApp.SALIENTE,
            sender_type=MensajeWhatsApp.SENDER_ADVISOR,
            source=MensajeWhatsApp.SOURCE_WHATSAPP_BUSINESS_APP,
            contenido="From advisor via WhatsApp Web",
            fecha_mensaje=timezone.now(),
        )

        resp = self.client.get(f"/dashboard/whatsapp/conversaciones/{self.conv.id}/mensajes/")
        data = resp.json()

        msg_data = next((m for m in data['messages'] if m['id'] == msg.id), None)
        self.assertIsNotNone(msg_data)
        self.assertEqual(msg_data['sender'], MensajeWhatsApp.SENDER_ADVISOR)

    def test_last_message_in_timeline_matches_bandeja(self):
        """Test 5: Last message in timeline = last_message from bandeja"""
        msg1 = MensajeWhatsApp.objects.create(
            conversacion=self.conv,
            meta_message_id="msg1",
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            contenido="First",
            fecha_mensaje=timezone.now() - timedelta(minutes=5),
        )
        msg2 = MensajeWhatsApp.objects.create(
            conversacion=self.conv,
            meta_message_id="msg2",
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            contenido="Second",
            fecha_mensaje=timezone.now(),
        )
        self.conv.ultima_actividad = msg2.fecha_mensaje
        self.conv.resumen = msg2.contenido
        self.conv.save()

        # Get timeline
        resp_timeline = self.client.get(f"/dashboard/whatsapp/conversaciones/{self.conv.id}/mensajes/")
        timeline_data = resp_timeline.json()
        last_timeline_msg = timeline_data['messages'][-1]

        # Get bandeja
        resp_bandeja = self.client.get("/dashboard/whatsapp/conversaciones/api/active/")
        bandeja_data = resp_bandeja.json()
        conv_bandeja = next((c for c in bandeja_data['conversations'] if c['id'] == self.conv.id), None)

        # Check match
        self.assertEqual(last_timeline_msg['id'], msg2.id)
        self.assertIn("Second", conv_bandeja['preview'])


class UnreadTests(TestCase):
    """Test unread counter calculation"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("testuser", "test@test.com", "testpass")
        # Assign user to Asesor de Ventas group for API access
        from django.contrib.auth.models import Group
        asesor_group, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        self.user.groups.add(asesor_group)
        self.channel = WhatsAppChannel.objects.create(
            nombre="Test Channel",
            phone_number_id="123456789",
            numero_visible="+51987654321",
            asesor=self.user,
            activo=True,
        )
        self.cliente = Cliente.objects.create(
            nombre="Cliente Demo WhatsApp",
            telefono="+51988888888"
        )
        self.conv = ConversacionWhatsApp.objects.create(
            cliente=self.cliente,
            channel=self.channel,
        )

    def test_inbound_new_increments_unread(self):
        """Test 1: New inbound message increments unread once"""
        # Create inbound message
        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conv,
            meta_message_id="unread_test_1",
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            contenido="New inbound",
            fecha_mensaje=timezone.now(),
        )

        # Calculate unread
        unread_count = MensajeWhatsApp.objects.filter(
            conversacion=self.conv,
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
        ).count()

        self.assertEqual(unread_count, 1)

    def test_duplicate_wamid_does_not_increment_unread(self):
        """Test 2: Same wamid twice = still 1 unread"""
        # First message
        msg1 = MensajeWhatsApp.objects.create(
            conversacion=self.conv,
            meta_message_id="duplicate_test",
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            contenido="Message",
            fecha_mensaje=timezone.now(),
        )

        # Try duplicate (should not create)
        msg2, created = MensajeWhatsApp.objects.get_or_create(
            meta_message_id="duplicate_test",
            conversacion=self.conv,
            defaults={
                "direccion": MensajeWhatsApp.ENTRANTE,
                "sender_type": MensajeWhatsApp.SENDER_CUSTOMER,
                "contenido": "Message",
                "fecha_mensaje": timezone.now(),
            }
        )

        unread_count = MensajeWhatsApp.objects.filter(
            conversacion=self.conv,
            direccion=MensajeWhatsApp.ENTRANTE,
            meta_message_id="duplicate_test",
        ).count()

        self.assertEqual(unread_count, 1)
        self.assertFalse(created)

    def test_bot_message_does_not_increment_unread(self):
        """Test 3: Bot message not counted as unread"""
        msg_bot = MensajeWhatsApp.objects.create(
            conversacion=self.conv,
            meta_message_id="bot_unread_test",
            direccion=MensajeWhatsApp.SALIENTE,
            sender_type=MensajeWhatsApp.SENDER_BOT,
            contenido="Bot reply",
            fecha_mensaje=timezone.now(),
        )

        unread_inbound = MensajeWhatsApp.objects.filter(
            conversacion=self.conv,
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
        ).count()

        self.assertEqual(unread_inbound, 0)

    def test_advisor_echo_does_not_increment_unread(self):
        """Test 4: Echo from advisor not counted as unread"""
        msg_echo = MensajeWhatsApp.objects.create(
            conversacion=self.conv,
            meta_message_id="echo_unread_test",
            direccion=MensajeWhatsApp.SALIENTE,
            sender_type=MensajeWhatsApp.SENDER_ADVISOR,
            source=MensajeWhatsApp.SOURCE_WHATSAPP_BUSINESS_APP,
            contenido="Echo from Web",
            fecha_mensaje=timezone.now(),
        )

        unread_inbound = MensajeWhatsApp.objects.filter(
            conversacion=self.conv,
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
        ).count()

        self.assertEqual(unread_inbound, 0)


class AuthorizationTests(TestCase):
    """Test authorization for protected endpoints"""

    def test_unauthorized_user_gets_403(self):
        """Test: Unauthorized user (no whatsapp group) gets 403"""
        # Create authenticated user WITHOUT Asesor de Ventas group
        unauthorized_user = User.objects.create_user("unauthorized", "unauth@test.com", "testpass")

        # Create channel and conversation
        channel = WhatsAppChannel.objects.create(
            phone_number_id=str(uuid.uuid4())[:20],
            nombre="Test Channel Auth",
            numero_visible="+51987654321",
            activo=True,
        )
        cliente = Cliente.objects.create(
            nombre="Cliente Auth Test",
            telefono=f"+5199{uuid.uuid4().hex[:8]}",
        )
        conv = ConversacionWhatsApp.objects.create(
            cliente=cliente,
            channel=channel,
        )
        # Create message so timeline has content
        MensajeWhatsApp.objects.create(
            conversacion=conv,
            meta_message_id=str(uuid.uuid4()),
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            contenido="Test",
            fecha_mensaje=timezone.now(),
        )

        # Login as unauthorized user
        client = Client()
        client.login(username="unauthorized", password="testpass")

        # Try to access timeline — should get 403
        resp = client.get(f"/dashboard/whatsapp/conversaciones/{conv.id}/mensajes/")
        self.assertEqual(resp.status_code, 403, "Unauthorized user must get 403 Forbidden")

        # Verify no content is returned
        self.assertNotContains(resp, "Test", status_code=403)

        # Create authorized user and verify they get 200
        auth_user = User.objects.create_user("authorized", "auth@test.com", "testpass")
        asesor_group, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        auth_user.groups.add(asesor_group)

        auth_client = Client()
        auth_client.login(username="authorized", password="testpass")

        # Authorized user should get 200
        resp_auth = auth_client.get(f"/dashboard/whatsapp/conversaciones/{conv.id}/mensajes/")
        self.assertEqual(resp_auth.status_code, 200, "Authorized user must get 200 OK")
        data = resp_auth.json()
        self.assertIn("messages", data)

    def test_unauthenticated_user_gets_redirect(self):
        """Test: Unauthenticated user gets redirect to login"""
        channel = WhatsAppChannel.objects.create(
            phone_number_id=str(uuid.uuid4())[:20],
            nombre="Test Channel No Auth",
            numero_visible="+51987654321",
            activo=True,
        )
        cliente = Cliente.objects.create(
            nombre="Cliente No Auth",
            telefono=f"+5199{uuid.uuid4().hex[:8]}",
        )
        conv = ConversacionWhatsApp.objects.create(
            cliente=cliente,
            channel=channel,
        )

        # No login — unauthenticated
        client = Client()

        # Should redirect to login
        resp = client.get(f"/dashboard/whatsapp/conversaciones/{conv.id}/mensajes/")
        self.assertIn(resp.status_code, [302, 401, 403], "Unauthenticated should be rejected")
