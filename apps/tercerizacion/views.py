from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.dashboard.permissions import role_required
from apps.servicios.models import Servicio

from .models import PublicacionCarga
from .services import tercerizar_carga


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_POST
def tercerizar(request, servicio_id):
    servicio = get_object_or_404(Servicio, pk=servicio_id)
    publicacion, creada = tercerizar_carga(servicio, request.user)

    if creada:
        messages.success(request, f"Publicación OFERTA-{publicacion.codigo} creada.")
    else:
        messages.info(
            request,
            f"Ya existe una publicación abierta para esta carga: "
            f"OFERTA-{publicacion.codigo}.",
        )

    return redirect("tercerizacion-detail", pk=publicacion.pk)


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def lista_publicaciones(request):
    publicaciones = (
        PublicacionCarga.objects
        .select_related("servicio", "creado_por")
        .prefetch_related("ofertas")
        .all()
    )

    return render(request, "tercerizacion/lista.html", {
        "publicaciones": publicaciones,
        "active_section": "servicios",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def detalle_publicacion(request, pk):
    publicacion = get_object_or_404(
        PublicacionCarga.objects.select_related("servicio", "creado_por"),
        pk=pk,
    )
    ofertas = publicacion.ofertas.select_related("cliente").all()

    return render(request, "tercerizacion/detalle.html", {
        "publicacion": publicacion,
        "ofertas": ofertas,
        "active_section": "servicios",
    })


def _get_bot_config():
    from apps.whatsapp_bot_v4.models import BotGlobalConfig
    config = BotGlobalConfig.objects.first()
    if not config:
        config = BotGlobalConfig.objects.create()
    return config


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_GET
def api_bot_estado(request):
    """Estado de AMBOS bots — independientes entre sí. flag_habilitado refleja
    TRANSPORTISTA_BOT_ENABLED (settings): si está en False, el interruptor de
    abajo no tiene efecto aunque se active, por diseño (kill-switch de
    despliegue por encima del control diario)."""
    from django.conf import settings as dj_settings

    config = _get_bot_config()
    return JsonResponse({
        "clientes_pausado": config.is_paused,
        "transportistas_pausado": config.transportistas_paused,
        "transportistas_flag_habilitado": dj_settings.TRANSPORTISTA_BOT_ENABLED,
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_POST
def api_bot_pausar(request):
    config = _get_bot_config()
    config.transportistas_paused = True
    config.transportistas_paused_at = timezone.now()
    config.save(update_fields=["transportistas_paused", "transportistas_paused_at"])
    return JsonResponse({"success": True, "transportistas_pausado": True})


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_POST
def api_bot_activar(request):
    config = _get_bot_config()
    config.transportistas_paused = False
    config.transportistas_paused_at = None
    config.save(update_fields=["transportistas_paused", "transportistas_paused_at"])
    return JsonResponse({"success": True, "transportistas_pausado": False})
