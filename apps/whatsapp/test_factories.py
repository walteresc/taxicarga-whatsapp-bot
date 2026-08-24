"""Test factories for WhatsApp tests with guaranteed unique phone numbers."""
import uuid
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime

from apps.clientes.models import Cliente
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp, MensajeWhatsApp


_phone_counter = {}


def get_unique_phone(test_name):
    """Generate unique Peruvian phone number per test."""
    if test_name not in _phone_counter:
        _phone_counter[test_name] = 0
    _phone_counter[test_name] += 1

    # Format: +51 9XX YY CCN where CCN is the counter
    counter = _phone_counter[test_name]
    last_three = str(counter).zfill(3)[-3:]
    phone = f"+5191{counter:06d}"
    return phone


def get_unique_event_id(test_name):
    """Generate unique event_id per test."""
    return f"event_{test_name}_{uuid.uuid4().hex[:8]}"


def get_unique_wamid(test_name):
    """Generate unique wamid per test."""
    counter = _phone_counter.get(test_name, 0)
    return f"wamid_{test_name}_{counter}_{uuid.uuid4().hex[:4]}"


def create_test_user(username=None):
    """Create or get test user."""
    if not username:
        username = f"testuser_{uuid.uuid4().hex[:4]}"
    return User.objects.create_user(username, f"{username}@test.com", "pass123")


def create_test_channel(user=None, nombre=None):
    """Create test WhatsApp channel."""
    if not user:
        user = create_test_user()
    if not nombre:
        nombre = f"TestChannel_{uuid.uuid4().hex[:4]}"

    return WhatsAppChannel.objects.create(
        nombre=nombre,
        phone_number_id=f"test_ch_{uuid.uuid4().hex[:6]}",
        asesor=user,
        activo=True
    )


def create_test_cliente(test_name=None, telefono=None, nombre=None):
    """Create test client with unique phone."""
    if not telefono:
        telefono = get_unique_phone(test_name or "default")
    if not nombre:
        nombre = f"TestCliente_{uuid.uuid4().hex[:4]}"

    return Cliente.objects.create(telefono=telefono, nombre=nombre)


def create_test_conversation(test_name=None, cliente=None, channel=None):
    """Create test conversation."""
    if not cliente:
        cliente = create_test_cliente(test_name)
    if not channel:
        channel = create_test_channel()

    return ConversacionWhatsApp.objects.create(
        cliente=cliente,
        channel=channel
    )


def create_test_message(conversation, test_name=None, texto=None, direccion=None, sender_type=None):
    """Create test message."""
    if not texto:
        texto = f"TestMsg_{uuid.uuid4().hex[:6]}"
    if not direccion:
        direccion = MensajeWhatsApp.ENTRANTE
    if not sender_type:
        sender_type = MensajeWhatsApp.SENDER_CUSTOMER

    return MensajeWhatsApp.objects.create(
        conversacion=conversation,
        texto=texto,
        direccion=direccion,
        sender_type=sender_type,
        meta_message_id=get_unique_wamid(test_name or "default")
    )


def reset_phone_counter():
    """Reset phone counter between test runs."""
    global _phone_counter
    _phone_counter = {}
