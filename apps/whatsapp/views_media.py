"""Authenticated proxy for locally-stored WhatsApp multimedia attachments.

YCloud does not expose an authenticated "GET media by id" endpoint for inbound
media — the only access is the short-lived signed 'link' URL embedded in the
original webhook payload (apps.whatsapp.services_ycloud downloads and stores it
immediately on arrival, via apps.whatsapp.services.download_mensaje_adjunto).

This view therefore only ever serves the locally stored copy (MEDIA_ROOT, private,
not exposed by nginx). It cannot re-fetch from YCloud on demand — for messages
whose media was never downloaded (predating the fix, or a failed download), there
is nothing to serve and it returns 404.
"""
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET

from apps.whatsapp.models import MensajeAdjunto


@login_required
@require_GET
def media_proxy(request, media_id):
    adjunto = (
        MensajeAdjunto.objects
        .filter(ycloud_media_id=media_id)
        .exclude(archivo="")
        .first()
    )
    if not adjunto or not adjunto.archivo:
        raise Http404("Media not available")

    response = FileResponse(
        adjunto.archivo.open("rb"),
        content_type=adjunto.mime_type or "application/octet-stream",
    )
    response["Content-Disposition"] = f'inline; filename="{adjunto.filename}"'
    response["Cache-Control"] = "private, max-age=86400"
    return response
