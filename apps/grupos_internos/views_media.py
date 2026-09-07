"""Proxy autenticado para los adjuntos del chat de equipo interno — 100% local
(MEDIA_ROOT, privado), nunca pasa por YCloud. Solo lo puede ver un miembro del
grupo (o Administrador/Supervisor), igual que los mensajes."""
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET

from apps.grupos_internos.api.shapes import is_manager
from apps.grupos_internos.models import MensajeGrupoInterno


@login_required
@require_GET
def group_media_proxy(request, message_id):
    mensaje = (
        MensajeGrupoInterno.objects
        .select_related("grupo")
        .filter(pk=message_id)
        .exclude(archivo="")
        .first()
    )
    if not mensaje or not mensaje.archivo:
        raise Http404("Media not available")

    if not (is_manager(request.user) or mensaje.grupo.membresias.filter(usuario=request.user).exists()):
        raise Http404("Media not available")

    response = FileResponse(
        mensaje.archivo.open("rb"),
        content_type=mensaje.mime_type or "application/octet-stream",
    )
    response["Content-Disposition"] = f'inline; filename="{mensaje.filename}"'
    response["Cache-Control"] = "private, max-age=86400"
    return response
