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
from django.views.decorators.cache import cache_control
from django.utils import timezone

from apps.whatsapp.redis_events import get_event_bus, get_events
from apps.dashboard.permissions import can_manage_whatsapp

logger = logging.getLogger(__name__)


class SSEStreamingHttpResponse(StreamingHttpResponse):
    """Custom StreamingHttpResponse that's middleware-safe.

    Some middlewares (clickjacking, etc) try to use response.get() on headers.
    Since StreamingHttpResponse returns a generator, this fails.
    This class implements dict-like access to headers for compatibility.
    """
    def get(self, key, default=None):
        """Dict-like access to headers for middleware compatibility."""
        try:
            return self.__getitem__(key)
        except KeyError:
            return default


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
    logger.info(f"[SSE] View entry: user={request.user.username}, remote_addr={request.META.get('REMOTE_ADDR')}")

    # Check authorization
    if not can_manage_whatsapp(request.user):
        logger.warning(f"[SSE] Unauthorized access from {request.user.username}")
        raise PermissionDenied("No tienes permisos para acceder a eventos de WhatsApp")

    logger.info(f"[SSE] Authorization passed for user={request.user.username}")

    # Get Last-Event-ID from request header (standard SSE) or query param
    last_event_id = request.headers.get('Last-Event-ID', '0')
    if not last_event_id:
        last_event_id = request.GET.get('cursor', '0')

    logger.info(f"[SSE] Last-Event-ID={last_event_id}")

    try:
        bus = get_event_bus()
        logger.info(f"[SSE] Event bus created: {type(bus).__name__}")
    except Exception as e:
        logger.exception(f"[SSE] Failed to get event bus")
        return SSEStreamingHttpResponse(
            _error_stream(f"event_bus_error: {str(e)}"),
            content_type='text/event-stream',
            status=500
        )

    # Check if Redis is available
    if not bus.is_available():
        logger.warning("[SSE] Redis unavailable")
        return SSEStreamingHttpResponse(
            _error_stream("service_unavailable"),
            content_type='text/event-stream',
            status=503
        )

    logger.info("[SSE] Redis available")

    # Check if cursor is valid and pass to generator
    cursor_too_old = (last_event_id != '0' and not bus.check_cursor_valid(last_event_id))
    if cursor_too_old:
        logger.info(f"[SSE] Cursor {last_event_id} too old, requesting resync")

    # Stream events
    try:
        logger.info("[SSE] Creating StreamingHttpResponse with generator")
        response = SSEStreamingHttpResponse(
            _event_generator(request, bus, last_event_id, cursor_too_old),
            content_type='text/event-stream'
        )

        logger.info(f"[SSE] Response created: type={type(response).__name__}")

        # SSE headers
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'

        logger.info("[SSE] Headers set, returning response")
        return response
    except Exception as e:
        logger.exception(f"[SSE] *** EXCEPTION IN VIEW BODY ***")
        import traceback
        logger.error(f"[SSE] Full traceback:\n{traceback.format_exc()}")
        return SSEStreamingHttpResponse(
            _error_stream(f"view_error: {str(e)}"),
            content_type='text/event-stream',
            status=500
        )


def _event_generator(request, bus, last_event_id, cursor_too_old=False):
    """Generator for streaming events from Redis to client.

    Filters events by:
    - Channel must be active
    - Channel must be authorized for user (for now: all active channels if has WhatsApp permission)

    Args:
        cursor_too_old: If True, send resync.required event first
    """
    import time
    from collections import deque
    from apps.whatsapp.models import WhatsAppChannel

    logger.info(f"[GEN] Generator started for user={request.user.username}")

    # SSE initial handshake
    try:
        logger.info("[GEN] Sending initial handshake")
        yield ': connected\n\n'
    except Exception as e:
        logger.exception(f"[GEN] Error on first yield (handshake)")
        return

    # If cursor was too old, request resync
    if cursor_too_old:
        logger.info("[GEN] Sending resync.required")
        yield _format_event(
            event_id='0',
            event_type='resync.required',
            data={'message': 'Cursor too old, use REST to resync'}
        )

    # Get authorized channel IDs for this user
    # Current policy: all active channels if user has WhatsApp permission
    # Future: filter by channel.asesor = request.user for non-admin users
    try:
        logger.info("[GEN] Loading authorized channels")
        authorized_channels = set(
            WhatsAppChannel.objects.filter(activo=True).values_list('id', flat=True)
        )
        logger.info(f"[GEN] Authorized channels: {authorized_channels}")
    except Exception as e:
        logger.exception(f"[GEN] Error loading authorized channels")
        return

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
    try:
        logger.info(f"[GEN] Loading initial events from cursor={last_event_id}")
        events = get_events(cursor=last_event_id)
        logger.info(f"[GEN] Loaded {len(list(events))} events")
        events = get_events(cursor=last_event_id)  # Re-fetch since generator was consumed
        for event in events:
            if is_event_authorized(event):
                pending.append(event)
                last_yielded_id = event.id
        logger.info(f"[GEN] Queued {len(pending)} authorized events")
    except Exception as e:
        logger.exception(f"[GEN] Error loading initial events")
        return

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
                    logger.error(f"[GEN] Error formatting event {event.id}: {e}")

            # Poll for new events (blocking for up to 5 seconds)
            time.sleep(1)
            try:
                new_events = get_events(cursor=last_yielded_id)
                for event in new_events:
                    if is_event_authorized(event):
                        pending.append(event)
                        last_yielded_id = event.id
            except Exception as e:
                logger.error(f"[GEN] Error polling events: {e}")

            # Heartbeat every 30 seconds
            heartbeat_count += 1
            if heartbeat_count >= heartbeat_interval:
                yield f': heartbeat at {timezone.now().isoformat()}\n\n'
                heartbeat_count = 0

    except GeneratorExit:
        logger.debug(f"[GEN] Client {request.META.get('REMOTE_ADDR')} disconnected")
    except Exception as e:
        logger.exception(f"[GEN] Stream error")
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
