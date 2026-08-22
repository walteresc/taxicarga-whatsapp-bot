"""SSE (Server-Sent Events) endpoint for real-time updates (FASE 5B).

Streams events from Redis using HTTP chunked transfer encoding.
Supports Last-Event-ID for cursor recovery and resync.
Applies authorization: only authenticated users in WhatsApp group can receive events.
"""

import logging
import json
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from apps.whatsapp.redis_events import get_event_bus, get_events
from apps.dashboard.permissions import can_manage_whatsapp

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def sse_events_stream(request):
    """
    SSE endpoint for real-time event streaming.

    GET /dashboard/whatsapp/api/events/stream/

    Authorization:
    - User must be authenticated
    - User must have WhatsApp access permission (Administrador, Supervisor, Asesor de Ventas)

    Query parameters:
    - last_event_id: Resume from specific event ID (SSE spec)

    Returns:
        Server-Sent Events stream with events
        Format:
        ```
        id: <event_id>
        event: <event_type>
        data: <json_data>

        ```
    """
    # Check authorization
    if not can_manage_whatsapp(request.user):
        logger.warning(f"Unauthorized SSE access from {request.user.username}")
        raise PermissionDenied("No tienes permisos para acceder a eventos de WhatsApp")

    # Get Last-Event-ID from request header (standard SSE) or query param
    last_event_id = request.headers.get('Last-Event-ID', '0')
    if not last_event_id:
        last_event_id = request.GET.get('cursor', '0')

    bus = get_event_bus()

    # Check if Redis is available
    if not bus.is_available():
        logger.warning("Redis unavailable for SSE")
        return StreamingHttpResponse(
            _error_stream("service_unavailable"),
            content_type='text/event-stream',
            status=503
        )

    # Check if cursor is too old (beyond retention)
    if last_event_id != '0' and not bus.check_cursor_valid(last_event_id):
        # Cursor too old - need full resync
        logger.info(f"Cursor {last_event_id} too old, requesting resync")
        yield _format_event(
            event_id='0',
            event_type='resync.required',
            data={'message': 'Cursor too old, use REST to resync'}
        )

    # Stream events
    try:
        response = StreamingHttpResponse(
            _event_generator(request, bus, last_event_id),
            content_type='text/event-stream'
        )

        # SSE headers
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        response['Connection'] = 'keep-alive'

        return response
    except Exception as e:
        logger.error(f"SSE stream error: {e}")
        return StreamingHttpResponse(
            _error_stream(str(e)),
            content_type='text/event-stream',
            status=500
        )


def _event_generator(request, bus, last_event_id):
    """Generator for streaming events from Redis to client.

    Filters events by:
    - Channel must be active
    - Channel must be authorized for user (for now: all active channels if has WhatsApp permission)
    """
    import time
    from collections import deque
    from apps.whatsapp.models import WhatsAppChannel

    # SSE initial handshake
    yield ': SSE connected\n\n'

    # Get authorized channel IDs for this user
    # Current policy: all active channels if user has WhatsApp permission
    # Future: filter by channel.asesor = request.user for non-admin users
    authorized_channels = set(
        WhatsAppChannel.objects.filter(activo=True).values_list('id', flat=True)
    )

    def is_event_authorized(event):
        """Check if event should be sent to this user."""
        channel_id = event.data.get('channel_id')
        if not channel_id:
            # Events without channel_id are not transmitted
            return False
        return channel_id in authorized_channels

    # Buffer for unread events
    pending = deque()
    last_yielded_id = last_event_id

    # Initial load (filtered)
    events = get_events(cursor=last_event_id)
    for event in events:
        if is_event_authorized(event):
            pending.append(event)
            last_yielded_id = event.id

    # Heartbeat counter
    heartbeat_count = 0
    heartbeat_interval = 30  # seconds

    try:
        while True:
            # Yield pending events
            while pending:
                event = pending.popleft()
                try:
                    yield _format_event(
                        event_id=event.id,
                        event_type=event.type,
                        data=event.data
                    )
                except Exception as e:
                    logger.error(f"Error formatting event {event.id}: {e}")

            # Poll for new events (blocking for up to 5 seconds)
            time.sleep(1)
            try:
                new_events = get_events(cursor=last_yielded_id)
                for event in new_events:
                    if is_event_authorized(event):
                        pending.append(event)
                        last_yielded_id = event.id
            except Exception as e:
                logger.error(f"Error polling events: {e}")

            # Heartbeat every 30 seconds
            heartbeat_count += 1
            if heartbeat_count >= heartbeat_interval:
                yield f': heartbeat at {timezone.now().isoformat()}\n\n'
                heartbeat_count = 0

    except GeneratorExit:
        logger.debug(f"Client {request.META.get('REMOTE_ADDR')} disconnected")
    except Exception as e:
        logger.error(f"Stream error: {e}")
        yield _format_event(
            event_id='error',
            event_type='error',
            data={'error': str(e)}
        )


def _format_event(event_id: str, event_type: str, data: dict) -> str:
    """Format event as Server-Sent Events."""
    return (
        f'id: {event_id}\n'
        f'event: {event_type}\n'
        f'data: {json.dumps(data)}\n\n'
    )


def _error_stream(error_msg: str):
    """Generate error event stream."""
    yield _format_event(
        event_id='error',
        event_type='error',
        data={'error': error_msg}
    )
