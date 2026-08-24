"""
Static files serving for development/testing only.

PRODUCTION NOTE: This module is for local development and E2E testing.
In production, serve static files using:
  - WhiteNoise (lightweight, no external dependencies)
  - Django's collectstatic with Nginx/Apache reverse proxy
  - CloudFront/CDN with S3 backend

Do NOT use this view in production. It lacks:
  - Compression
  - Caching headers
  - Versioning by hash
  - Security hardening for high-traffic
  - DDoS protection
"""
from django.http import FileResponse, Http404
from django.views.decorators.http import condition
from pathlib import Path
import mimetypes
import logging

logger = logging.getLogger(__name__)

# Rutas donde buscar archivos estáticos
STATIC_DIRS = [
    Path(__file__).resolve().parent.parent.parent / 'static_build',
    Path(__file__).resolve().parent.parent.parent / 'staticfiles',
]

def serve_static(request, filepath):
    """
    Serve static files from STATIC_DIRS (DEVELOPMENT ONLY).

    Security features:
      - Path traversal protection (.., absolute paths)
      - MIME type detection
      - File existence validation

    Args:
        request: Django request object
        filepath: Relative path (e.g., 'static/css/index.css')

    Returns:
        FileResponse with correct Content-Type or Http404
    """
    # Seguridad: no permitir path traversal
    if '..' in filepath or filepath.startswith('/'):
        raise Http404("Invalid path")

    # Buscar el archivo
    file_path = None
    for static_dir in STATIC_DIRS:
        candidate = static_dir / filepath
        if candidate.exists() and candidate.is_file():
            file_path = candidate
            break

    if not file_path:
        logger.warning(f"Static file not found: {filepath}")
        raise Http404(f"File not found: {filepath}")

    # Detectar MIME type
    content_type, _ = mimetypes.guess_type(str(file_path))
    if not content_type:
        content_type = 'application/octet-stream'

    # Servir archivo
    try:
        return FileResponse(open(file_path, 'rb'), content_type=content_type)
    except Exception as e:
        logger.error(f"Error serving {file_path}: {e}")
        raise Http404(f"Error serving file: {e}")
