from django.http import FileResponse
from django.views.decorators.http import require_http_methods
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Ruta donde está el index.html de Vue compilado
STATIC_BUILD_PATH = Path(__file__).resolve().parent.parent.parent / 'static_build'
INDEX_HTML = STATIC_BUILD_PATH / 'index.html'

# Rutas que NO deben ser manejadas por SPA fallback
SPA_EXCLUDED_PREFIXES = [
    '/admin/',
    '/api/',
    '/webhooks/',
    '/webhook/',
    '/dashboard/whatsapp/api/',
    '/dashboard/whatsapp/conversaciones/api/',
    '/dashboard/api/auth/',
    '/dashboard/login/',
    '/dashboard/logout/',
    '/static/',
    '/media/',
    '/.well-known/',
]

def should_use_spa_fallback(path):
    """Determinar si una ruta debe usar SPA fallback"""
    for prefix in SPA_EXCLUDED_PREFIXES:
        if path.startswith(prefix):
            return False
    return True


@require_http_methods(["GET"])
def spa_fallback(request):
    """
    Fallback para SPA: devuelve index.html para todas las rutas que no sean API/admin/etc.
    Permite que Vue Router maneje todas las rutas visuales.
    """
    if not INDEX_HTML.exists():
        logger.error(f"index.html not found at {INDEX_HTML}")
        return FileResponse(open(INDEX_HTML, 'rb'), status=404)

    return FileResponse(open(INDEX_HTML, 'rb'), content_type='text/html')
