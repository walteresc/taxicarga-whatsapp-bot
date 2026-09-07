from pathlib import Path
import logging

from django.http import FileResponse, HttpResponse, HttpResponseRedirect
from django.utils.http import urlencode
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

# Ruta donde está el index.html de Vue compilado
STATIC_BUILD_PATH = Path(__file__).resolve().parent.parent.parent / 'static_build'
INDEX_HTML = STATIC_BUILD_PATH / 'index.html'

# Rutas del SPA que se sirven SIN sesión: solo la propia pantalla de acceso.
# Todo lo demás exige usuario autenticado (el shell de la app no se entrega a
# anónimos — mismo criterio que las APIs del panel).
SPA_PUBLIC_PATHS = {'/login', '/register', '/forgot-password'}

# Rutas que NO deben ser manejadas por SPA fallback
SPA_EXCLUDED_PREFIXES = [
    '/admin/',
    '/api/',
    '/webhooks/',
    '/webhook/',
    '/dashboard/',
    '/static/',
    '/media/',
    '/health/',
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
    """Sirve el shell de la SPA (index.html) para las rutas visuales de Vue.

    Solo a usuarios autenticados. Un anónimo que pida cualquier ruta que no sea
    pública es redirigido a /login conservando el destino en ?next=.
    """
    path = request.path.rstrip('/') or '/'
    if not request.user.is_authenticated and path not in SPA_PUBLIC_PATHS:
        return HttpResponseRedirect('/login?' + urlencode({'next': request.get_full_path()}))

    if not INDEX_HTML.exists():
        logger.error("index.html no encontrado en %s", INDEX_HTML)
        return HttpResponse("La aplicación no está compilada.", status=503)

    resp = FileResponse(open(INDEX_HTML, 'rb'), content_type='text/html')
    # index.html nunca se cachea: es lo único que apunta a los bundles con hash.
    resp['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp['Pragma'] = 'no-cache'
    resp['Expires'] = '0'
    return resp
