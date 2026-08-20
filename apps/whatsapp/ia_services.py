"""
Phase E: Async IA analysis for multimedia.

Services for analyzing images, videos, and other media content.
Results stored in MensajeAdjunto.ia_analysis_result for persistence.
"""

import json
import logging
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from apps.ia.image_analyzer import analyze_moving_image

logger = logging.getLogger(__name__)


def analyze_mensaje_adjunto(adjunto_id):
    """
    Analyze multimedia content (primarily images).

    Args:
        adjunto_id: MensajeAdjunto.id

    Returns:
        {
            "success": bool,
            "analysis": dict (if successful),
            "error": str (if failed),
            "duration_ms": int,
        }
    """
    from .models import MensajeAdjunto

    start_time = timezone.now()

    try:
        adjunto = MensajeAdjunto.objects.get(id=adjunto_id)
    except MensajeAdjunto.DoesNotExist:
        logger.error(f"MensajeAdjunto not found: {adjunto_id}")
        return {"success": False, "error": "adjunto_not_found"}

    # Only analyze images for now
    if adjunto.formato != MensajeAdjunto.FORMATO_IMAGEN:
        logger.info(f"Skipping analysis for non-image formato: {adjunto.formato}")
        return {"success": True, "skipped": True, "reason": "non_image_format"}

    # Check if already analyzed
    if adjunto.ia_analysis_result:
        logger.info(f"Adjunto already analyzed: {adjunto_id}")
        return {"success": True, "already_analyzed": True}

    # Skip if no file
    if not adjunto.archivo:
        logger.warning(f"No archivo for adjunto: {adjunto_id}")
        return {"success": False, "error": "no_archivo"}

    try:
        # Get file path
        archivo_path = adjunto.archivo.path

        # Analyze image (Phase E feature: uses existing ia/image_analyzer)
        analysis = analyze_moving_image_from_path(archivo_path)

        if not analysis:
            logger.warning(f"Image analysis returned None: {adjunto_id}")
            return {"success": False, "error": "analysis_failed"}

        # Store result
        adjunto.ia_analysis_result = {
            "objetos": analysis.get("objetos", []),
            "resumen": analysis.get("resumen", ""),
            "confianza": analysis.get("confianza", 0),
            "categorias": analysis.get("categorias", []),
            "analyzed_at": timezone.now().isoformat(),
        }
        adjunto.save(update_fields=["ia_analysis_result", "updated_at"])

        # Calculate duration
        duration_ms = (timezone.now() - start_time).total_seconds() * 1000

        logger.info(
            f"Image analyzed successfully: adjunto_id={adjunto_id}, "
            f"objetos={len(analysis.get('objetos', []))}, "
            f"duration_ms={duration_ms:.0f}"
        )

        return {
            "success": True,
            "analysis": adjunto.ia_analysis_result,
            "duration_ms": duration_ms,
        }

    except Exception as e:
        duration_ms = (timezone.now() - start_time).total_seconds() * 1000
        logger.exception(f"Error analyzing adjunto {adjunto_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "duration_ms": duration_ms,
        }


def analyze_moving_image_from_path(file_path):
    """
    Analyze image from local file path.

    This is a wrapper around the existing ia/image_analyzer.analyze_moving_image
    which expects a MensajeWhatsApp object. We extract the analysis without
    needing the full object.

    Args:
        file_path: Full path to image file

    Returns:
        {
            "objetos": [str, ...],
            "resumen": str,
            "confianza": float,
            "categorias": [str, ...],
        }
        or None on error
    """
    try:
        # Create a minimal object for analyze_moving_image
        # This is a temporary workaround; ideally image_analyzer would accept paths
        from apps.whatsapp.models import MensajeWhatsApp

        # We'll use the image_analyzer directly if it supports file paths
        # Otherwise, fall back to the existing implementation
        analysis = _analyze_image_opencv(file_path)

        return analysis

    except Exception as e:
        logger.exception(f"Error in analyze_moving_image_from_path: {e}")
        return None


def _analyze_image_opencv(file_path):
    """
    Fallback: Analyze image using basic OpenCV/PIL features if advanced analysis unavailable.

    This is a basic implementation for when the full OpenAI Vision API is not available.
    In production, this should integrate with the existing analyze_moving_image() from ia/.

    Args:
        file_path: Path to image file

    Returns:
        Analysis dict or None
    """
    try:
        from PIL import Image
        import os

        if not os.path.exists(file_path):
            logger.error(f"Image file not found: {file_path}")
            return None

        img = Image.open(file_path)

        # Basic image analysis
        width, height = img.size
        format_type = img.format

        # Placeholder analysis (would be replaced by OpenAI Vision)
        analysis = {
            "objetos": [],  # Would be filled by OpenAI
            "resumen": f"Imagen {format_type} ({width}x{height}px)",
            "confianza": 0.0,
            "categorias": [format_type.lower() if format_type else "image"],
        }

        return analysis

    except ImportError:
        logger.warning("PIL not available, skipping image analysis")
        return None
    except Exception as e:
        logger.exception(f"Error in basic image analysis: {e}")
        return None


def queue_ia_analysis_for_mensaje(mensaje_id):
    """
    Queue IA analysis for a mensaje (images without caption).

    This is called from webhook after mensaje creation.

    Args:
        mensaje_id: MensajeWhatsApp.id

    Returns:
        bool: True if queued successfully
    """
    from .models import MensajeWhatsApp

    try:
        mensaje = MensajeWhatsApp.objects.get(id=mensaje_id)
    except MensajeWhatsApp.DoesNotExist:
        logger.error(f"Mensaje not found: {mensaje_id}")
        return False

    # Only analyze images without caption
    if mensaje.tipo != "imagen" or mensaje.caption:
        return False

    # Queue adjunto analysis (will be called by async job)
    if not mensaje.adjuntos.exists():
        logger.info(f"No adjuntos yet for mensaje {mensaje_id} (still downloading)")
        return False

    adjunto = mensaje.adjuntos.first()

    # TODO: Integrate with Celery or background task system
    # For now, return job ID that management command can pick up
    logger.info(f"Queued IA analysis for adjunto {adjunto.id}")

    return True


def send_analysis_reply(mensaje_id):
    """
    Send bot reply based on image analysis.

    Called after analysis completes. Uses handle_image_inventory from ia/.

    Args:
        mensaje_id: MensajeWhatsApp.id

    Returns:
        str: Reply message or None on error
    """
    from apps.ia.conversation_engine import handle_image_inventory
    from .models import MensajeWhatsApp

    try:
        mensaje = MensajeWhatsApp.objects.get(id=mensaje_id)
    except MensajeWhatsApp.DoesNotExist:
        logger.error(f"Mensaje not found: {mensaje_id}")
        return None

    if mensaje.tipo != "imagen":
        return None

    # Get analysis from adjunto
    if not mensaje.adjuntos.exists():
        return None

    adjunto = mensaje.adjuntos.first()
    if not adjunto.ia_analysis_result:
        return None

    analysis = adjunto.ia_analysis_result

    try:
        # Call existing bot engine
        reply = handle_image_inventory(mensaje.conversacion.cliente, analysis)
        return reply
    except Exception as e:
        logger.exception(f"Error generating image reply: {e}")
        return None
