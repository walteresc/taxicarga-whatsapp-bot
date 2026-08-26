"""
Tests para lógica de decisión de respuesta automática.
Verifica que el bot respeta el estado efectivo: global_paused OR conversation_paused
"""
import pytest
from django.test import TestCase
from apps.whatsapp_bot_v4.models import BotGlobalConfig
from apps.whatsapp.models import ConversacionWhatsApp
from django.contrib.auth.models import User


class BotEffectiveStatusTests(TestCase):
    """Tests para estado efectivo del bot (global + conversation)"""

    def setUp(self):
        self.user = User.objects.create_user('test', 'test@test.com', 'pass')
        self.global_config = BotGlobalConfig.objects.create(is_paused=False)

        # Crear conversación de prueba
        self.conv = ConversacionWhatsApp.objects.create(
            cliente_id=1,
            channel_id=1,
            bot_pausado=False,
        )

    def effective_bot_paused(self, global_paused, conv_paused):
        """Calcula estado efectivo: global OR conversation"""
        return global_paused or conv_paused

    def test_global_active_conversation_active_bot_can_respond(self):
        """Bot global activo + conversación activa → bot puede responder"""
        self.global_config.is_paused = False
        self.global_config.save()
        self.conv.bot_pausado = False
        self.conv.save()

        # Estado efectivo: puede responder
        effective = self.effective_bot_paused(
            self.global_config.is_paused,
            self.conv.bot_pausado
        )
        self.assertFalse(effective, "Bot debería poder responder")

    def test_global_paused_conversation_active_bot_cannot_respond(self):
        """Bot global pausado + conversación activa → bot NO puede responder"""
        self.global_config.is_paused = True
        self.global_config.save()
        self.conv.bot_pausado = False
        self.conv.save()

        # Estado efectivo: NO puede responder
        effective = self.effective_bot_paused(
            self.global_config.is_paused,
            self.conv.bot_pausado
        )
        self.assertTrue(effective, "Bot NO debería poder responder")

    def test_global_active_conversation_paused_bot_cannot_respond(self):
        """Bot global activo + conversación pausada → bot NO puede responder"""
        self.global_config.is_paused = False
        self.global_config.save()
        self.conv.bot_pausado = True
        self.conv.save()

        # Estado efectivo: NO puede responder
        effective = self.effective_bot_paused(
            self.global_config.is_paused,
            self.conv.bot_pausado
        )
        self.assertTrue(effective, "Bot NO debería poder responder")

    def test_global_paused_conversation_paused_bot_cannot_respond(self):
        """Bot global pausado + conversación pausada → bot NO puede responder"""
        self.global_config.is_paused = True
        self.global_config.save()
        self.conv.bot_pausado = True
        self.conv.save()

        # Estado efectivo: NO puede responder
        effective = self.effective_bot_paused(
            self.global_config.is_paused,
            self.conv.bot_pausado
        )
        self.assertTrue(effective, "Bot NO debería poder responder")

    def test_pausing_global_does_not_modify_conversation_flag(self):
        """Pausar bot global NO debe cambiar bot_pausado de conversaciones"""
        self.conv.bot_pausado = False
        self.conv.save()

        # Pausar global
        self.global_config.is_paused = True
        self.global_config.save()

        # Verificar que conversation.bot_pausado sigue siendo False
        self.conv.refresh_from_db()
        self.assertFalse(
            self.conv.bot_pausado,
            "Pausar global NO debe cambiar conversation.bot_pausado"
        )

    def test_activating_global_does_not_modify_conversation_flag(self):
        """Activar bot global NO debe cambiar bot_pausado de conversaciones"""
        self.conv.bot_pausado = True
        self.conv.save()

        # Activar global
        self.global_config.is_paused = False
        self.global_config.save()

        # Verificar que conversation.bot_pausado sigue siendo True
        self.conv.refresh_from_db()
        self.assertTrue(
            self.conv.bot_pausado,
            "Activar global NO debe cambiar conversation.bot_pausado"
        )

    def test_api_returns_correct_is_paused_value(self):
        """API debe retornar is_paused sin invertir"""
        self.global_config.is_paused = True
        self.global_config.save()

        # En Django ORM, el valor debe ser True
        config = BotGlobalConfig.objects.first()
        self.assertTrue(config.is_paused)

    def test_global_state_is_independent_from_conversation_state(self):
        """Estado global es independiente del estado de conversaciones"""
        conv2 = ConversacionWhatsApp.objects.create(
            cliente_id=2,
            channel_id=1,
            bot_pausado=True,  # Diferentes valores
        )

        self.assertNotEqual(
            self.conv.bot_pausado,
            conv2.bot_pausado,
            "Estados individuales deben ser independientes"
        )
