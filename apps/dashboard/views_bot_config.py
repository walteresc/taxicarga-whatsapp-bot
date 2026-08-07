from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.dashboard.permissions import whatsapp_config_required
from apps.whatsapp.models import ConfiguracionBot, MODOS_OPERACION, WhatsAppChannel


MODE_TO_LEGACY = {
    "asesor": ("humano", False),
    "recopilar": ("bot", True),
    "automatica": ("bot", True),
    "hibrido": ("mixto", True),
}


@login_required
@whatsapp_config_required
def whatsapp_configuracion(request):
    channels = list(WhatsAppChannel.objects.select_related("asesor").order_by("nombre"))
    channel_id = request.GET.get("channel", "")
    channel = WhatsAppChannel.objects.filter(pk=int(channel_id)).first() if channel_id.isdigit() else None
    config = ConfiguracionBot.obtener(channel=channel) if channel else None
    if request.method == "POST":
        channel = get_object_or_404(WhatsAppChannel, pk=request.POST.get("channel_id"))
        config = ConfiguracionBot.obtener(channel=channel)
        try:
            _update_config(config, request.POST)
            messages.success(request, f"Configuración de {channel.nombre} guardada.")
            return redirect(f"{request.path}?channel={channel.id}")
        except ValueError as exc:
            messages.error(request, str(exc))

    configs = {item.channel_id: item for item in ConfiguracionBot.objects.filter(channel__in=channels)}
    channel_cards = [{"channel": item, "config": configs.get(item.id)} for item in channels]
    advisors = get_user_model().objects.filter(
        Q(groups__name__in=["Administrador", "Supervisor", "Asesor de Ventas"]) | Q(is_superuser=True), is_active=True
    ).distinct().order_by("first_name", "username")
    return render(request, "dashboard/whatsapp_bot_config.html", {
        "active_section": "whatsapp-configuracion",
        "channel_cards": channel_cards,
        "channel": channel,
        "config": config,
        "modes": MODOS_OPERACION,
        "advisors": advisors,
        "rules": [
            ("provincia", "Derivar rutas fuera de Lima"),
            ("objetos_especiales", "Derivar objetos especiales o pesados"),
            ("pisos_altos", "Derivar pisos altos sin ascensor"),
            ("embalaje_full", "Derivar embalaje completo"),
        ],
    })


def _update_config(config, data):
    mode = data.get("modo_operacion", "")
    if mode not in dict(MODOS_OPERACION):
        raise ValueError("Modo de operación inválido.")
    try:
        start = datetime.strptime(data.get("hora_inicio_bot", ""), "%H:%M").time()
        end = datetime.strptime(data.get("hora_fin_bot", ""), "%H:%M").time()
    except ValueError as exc:
        raise ValueError("Horario inválido.") from exc
    timezone_name = data.get("zona_horaria", "America/Lima").strip()
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Zona horaria inválida.") from exc
    confidence = _decimal_range(data.get("confianza_minima"), "confianza mínima", 0, 100)
    margin = _decimal_range(data.get("margen_minimo_porcentaje"), "margen mínimo", 0, 100)
    wait = _integer_range(data.get("espera_asesor_minutos"), "espera del asesor", 1, 1440)
    follow = _integer_range(data.get("seguimiento_horas"), "seguimiento", 1, 720)
    advisor_id = data.get("asesor_predeterminado", "")
    advisor = get_user_model().objects.filter(pk=int(advisor_id), is_active=True).first() if advisor_id.isdigit() else None
    legacy_mode, active = MODE_TO_LEGACY[mode]
    config.modo_operacion = mode
    config.modo_atencion = legacy_mode
    config.bot_activo = active
    config.hora_inicio_bot = start
    config.hora_fin_bot = end
    config.zona_horaria = timezone_name
    config.confianza_minima = confidence
    config.margen_minimo_porcentaje = margin
    config.espera_asesor_minutos = wait
    config.seguimiento_horas = follow
    config.asesor_predeterminado = advisor
    config.transferir_fuera_horario = data.get("transferir_fuera_horario") == "1"
    config.mensaje_bienvenida = data.get("mensaje_bienvenida", "").strip()
    config.mensaje_fuera_horario = data.get("mensaje_fuera_horario", "").strip()
    config.reglas_automaticas = data.getlist("reglas_automaticas")
    for day in ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]:
        setattr(config, f"{day}_activo", data.get(f"{day}_activo") == "1")
    config.save()


def _decimal_range(value, label, minimum, maximum):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"Valor inválido para {label}.") from exc
    if number < minimum or number > maximum:
        raise ValueError(f"{label.capitalize()} debe estar entre {minimum} y {maximum}.")
    return number


def _integer_range(value, label, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Valor inválido para {label}.") from exc
    if number < minimum or number > maximum:
        raise ValueError(f"{label.capitalize()} debe estar entre {minimum} y {maximum}.")
    return number
