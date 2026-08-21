"""Global SSE stream for real-time conversation updates"""
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.whatsapp.models import MensajeWhatsApp
import json
import logging
import queue
import threading

logger = logging.getLogger(__name__)

# In-memory event queues per user
_user_queues = {}
_queue_lock = threading.Lock()


def get_user_queue(user_id):
    """Get or create event queue for user"""
    with _queue_lock:
        if user_id not in _user_queues:
            _user_queues[user_id] = queue.Queue()
        return _user_queues[user_id]


def broadcast_to_user(user_id, event_type, data):
    """Send event to specific user"""
    try:
        q = get_user_queue(user_id)
        q.put_nowait({'type': event_type, 'data': data})
    except queue.Full:
        logger.warning(f"Event queue full for user {user_id}")


@receiver(post_save, sender=MensajeWhatsApp)
def on_message_created(sender, instance, created, **kwargs):
    """Broadcast new message to all users with access"""
    if not created:
        return

    from apps.whatsapp.models import ConversacionWhatsApp
    conv = instance.conversacion

    # Broadcast to all users (in production: only users with access to this conversation)
    from django.contrib.auth import get_user_model
    User = get_user_model()

    for user in User.objects.filter(is_active=True):
        broadcast_to_user(user.id, 'message.created', {
            'conversation_id': conv.id,
            'message_id': instance.id,
            'timestamp': instance.fecha_mensaje.isoformat(),
        })
        logger.info(f"[SSE] Broadcast message {instance.id} to user {user.id}")


@login_required
@require_http_methods(["GET"])
def sse_global_updates(request):
    """Server-Sent Events stream for ALL conversation updates"""
    user_id = request.user.id
    user_queue = get_user_queue(user_id)

    def event_stream():
        """Generator for SSE events"""
        try:
            # Send initial connection confirmation
            yield "data: connected\n\n"
            logger.info(f"[SSE] User {user_id} connected")

            while True:
                try:
                    # Wait for event (with timeout to keep connection alive)
                    event = user_queue.get(timeout=30)

                    # Send as SSE
                    yield f"event: {event['type']}\n"
                    yield f"data: {json.dumps(event['data'])}\n\n"
                    logger.info(f"[SSE] Sent {event['type']} to user {user_id}")

                except queue.Empty:
                    # Send keepalive every 30 seconds
                    yield ": keepalive\n\n"

        except GeneratorExit:
            logger.info(f"[SSE] User {user_id} disconnected")
        except Exception as e:
            logger.error(f"[SSE] Error for user {user_id}: {e}")

    return StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )
