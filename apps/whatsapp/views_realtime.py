"""
Server-Sent Events endpoints for real-time updates.
Frontend can connect: const sse = new EventSource('/api/whatsapp/sse/conversation/201/');
"""
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from apps.whatsapp.models import ConversacionWhatsApp
import json
import logging
import time
from threading import Event

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def sse_conversation_updates(request, conversation_id):
    """
    Server-Sent Events stream for conversation updates.

    Usage (frontend):
        const sse = new EventSource(`/api/whatsapp/sse/conversation/${convId}/`);
        sse.addEventListener('message.created', (e) => {
            const data = JSON.parse(e.data);
            console.log('New message:', data);
        });
        sse.addEventListener('conversation.updated', (e) => {
            const data = JSON.parse(e.data);
            console.log('Conversation changed:', data);
        });
    """
    # Verify access
    conversation = get_object_or_404(ConversacionWhatsApp, pk=conversation_id)

    def event_stream():
        """Generator for SSE stream"""
        try:
            # Send initial keepalive
            yield ': keepalive\n\n'

            # In production: subscribe to Redis stream or Channels group
            # For now: simple heartbeat (keep connection alive)
            for i in range(10):  # Keep connection for 10 seconds
                yield ': heartbeat\n\n'
                time.sleep(1)

        except GeneratorExit:
            logger.info(f"[SSE] Client disconnected from conversation {conversation_id}")

    return StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # Disable proxy buffering
        }
    )
