"""SSE (Server-Sent Events) endpoint for real-time updates (FASE 5B).

Streams events from Redis using HTTP chunked transfer encoding.
Supports Last-Event-ID for cursor recovery and resync.
Applies authorization: only authenticated users in WhatsApp group can receive events.
"""

import logging
import json
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import StreamingHttpResponse, JsonResponse
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
def debug_redis(request):
    """Endpoint de debug para verificar Redis en Gunicorn."""
    import os
    import threading
    import redis
    import traceback

    result = {
        "pid": os.getpid(),
        "thread": threading.current_thread().name,
        "tests": {}
    }

    try:
        # Test 0: DNS resolution from main thread
        import socket
        import threading

        def test_dns_main():
            try:
                ip = socket.gethostbyname("redis")
                return f"OK: redis -> {ip}"
            except Exception as e:
                return f"FAIL: {type(e).__name__}: {str(e)[:60]}"

        def test_dns_thread():
            try:
                ip = socket.gethostbyname("redis")
                return f"OK: redis -> {ip}"
            except Exception as e:
                return f"FAIL: {type(e).__name__}: {str(e)[:60]}"

        result["tests"]["dns_redis_main_thread"] = test_dns_main()

        # Test DNS from new thread
        t = threading.Thread(target=lambda: result["tests"].update({"dns_redis_new_thread": test_dns_thread()}))
        t.start()
        t.join(timeout=2)

        if "dns_redis_new_thread" not in result["tests"]:
            result["tests"]["dns_redis_new_thread"] = "TIMEOUT"

        # Test 1: Direct Redis connection with IP
        try:
            import socket
            ip = socket.gethostbyname("redis")
            r = redis.from_url(f"redis://{ip}:6379/0", decode_responses=True, socket_connect_timeout=2)
            r.ping()
            result["tests"]["direct_redis_ping_by_ip"] = "OK"
        except Exception as e:
            result["tests"]["direct_redis_ping_by_ip"] = f"FAIL: {type(e).__name__}: {str(e)[:60]}"

        # Test 1b: Direct Redis connection with hostname
        try:
            r = redis.from_url("redis://redis:6379/0", decode_responses=True, socket_connect_timeout=2)
            r.ping()
            result["tests"]["direct_redis_ping_by_hostname"] = "OK"
        except Exception as e:
            result["tests"]["direct_redis_ping_by_hostname"] = f"FAIL: {type(e).__name__}: {str(e)[:60]}"

        # Test 2: get_event_bus
        try:
            from apps.whatsapp.redis_events import get_event_bus
            bus = get_event_bus()
            result["tests"]["get_event_bus"] = "OK"
        except Exception as e:
            result["tests"]["get_event_bus"] = f"FAIL: {type(e).__name__}: {str(e)[:50]}"
            result["tests"]["get_event_bus_traceback"] = traceback.format_exc()

        # Test 3: bus.is_available()
        try:
            result["tests"]["bus_is_available"] = bus.is_available()
        except Exception as e:
            result["tests"]["bus_is_available"] = f"ERROR: {type(e).__name__}: {str(e)[:50]}"

        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }, status=500)

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
    """
    import sys
    from apps.whatsapp.redis_events import get_latest_cursor

    # Check authorization
    if not can_manage_whatsapp(request.user):
        logger.warning(f"[SSE] Unauthorized access from {request.user.username}")
        raise PermissionDenied("No tienes permisos para acceder a eventos de WhatsApp")

    # Get Last-Event-ID from request header (standard SSE - sent on browser reconnect)
    # or query param (for explicit cursor reset), or default to latest (new connections)
    last_event_id = request.headers.get('Last-Event-ID')
    if not last_event_id:
        last_event_id = request.GET.get('cursor')

    # PASO 4: Defensa — rechazar cursor=0 explícitamente
    # cursor=0 significa "replay completo" y NO debe usarse en operación normal
    if last_event_id == '0' or last_event_id == '':
        logger.info(f"[SSE] Received cursor={repr(last_event_id)}, using latest instead")
        last_event_id = get_latest_cursor()

    if not last_event_id:
        # NEW CONNECTION: Start from latest event, not from beginning
        last_event_id = get_latest_cursor()

    print(f"[SSE-ENTRY] user={request.user.username}, cursor={last_event_id}", file=sys.stderr)
    sys.stderr.flush()

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
        print(f"[SSE] Creating StreamingHttpResponse with generator", file=sys.stderr)
        sys.stderr.flush()

        response = SSEStreamingHttpResponse(
            _event_generator(request, bus, last_event_id, cursor_too_old),
            content_type='text/event-stream',
            status=200
        )

        print(f"[SSE] Response created: status=200, type={type(response).__name__}", file=sys.stderr)
        sys.stderr.flush()

        # SSE headers
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'

        # CORS headers for EventSource with credentials
        origin = request.META.get('HTTP_ORIGIN', '')
        if origin:
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            logger.info(f"[SSE] CORS headers set for origin={origin}")

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

    iteration_count = 0

    try:
        logger.info(f"[SSE GEN] ENTRY: user={request.user.username}, cursor={last_event_id}")

        # SSE initial handshake
        yield ': connected\n\n'

        # If cursor was too old, request resync
        if cursor_too_old:
            logger.info("[SSE GEN] Sending resync.required")
            yield _format_event(
                event_id='0',
                event_type='resync.required',
                data={'message': 'Cursor too old, use REST to resync'}
            )

        # Get authorized channel IDs for this user
        authorized_channels = set(
            WhatsAppChannel.objects.filter(activo=True).values_list('id', flat=True)
        )
        logger.info(f"[SSE GEN] Loaded {len(authorized_channels)} authorized channels")

        def is_event_authorized(event):
            """Check if event should be sent to this user."""
            channel_id = event.data.get('channel_id')
            if not channel_id:
                return False
            return channel_id in authorized_channels

        # Buffer for unread events
        pending = deque()
        last_yielded_id = last_event_id

        # Initial load (filtered) - MATERIALIZE ONCE
        try:
            events_gen = get_events(cursor=last_event_id)
            events = list(events_gen)
            logger.info(f"[SSE GEN] Initial load: {len(events)} events")
        except Exception as e:
            logger.error(f"[SSE GEN] Error loading initial events: {e}", exc_info=True)
            raise

        for event in events:
            if is_event_authorized(event):
                pending.append(event)
                last_yielded_id = event.id
        logger.info(f"[SSE GEN] Queued {len(pending)} authorized events")

        # Heartbeat counter
        heartbeat_count = 0
        heartbeat_interval = 30  # seconds
        while True:
            iteration_count += 1

            # Yield pending events
            while pending:
                event = pending.popleft()
                yield _format_event(
                    event_id=event.id,
                    event_type=event.type,
                    data=event.data
                )

            # Poll for new events
            time.sleep(1)

            try:
                new_events = list(get_events(cursor=last_yielded_id))
                if new_events:
                    logger.info(f"[SSE GEN IT#{iteration_count}] Polled {len(new_events)} events from cursor={last_yielded_id}")
                    for event in new_events:
                        logger.info(f"[SSE GEN] Event {event.id}: type={event.type}, authorized={is_event_authorized(event)}")
                        if is_event_authorized(event):
                            pending.append(event)
                            last_yielded_id = event.id
                            logger.info(f"[SSE GEN] ✓ Enqueued event {event.id}")
            except Exception as e:
                logger.error(f"[SSE GEN] Error polling events: {e}", exc_info=True)

            # Heartbeat every 30 seconds
            heartbeat_count += 1
            if heartbeat_count >= heartbeat_interval:
                yield f': heartbeat at {timezone.now().isoformat()}\n\n'
                heartbeat_count = 0

    except GeneratorExit:
        logger.info(f"[SSE GEN] Client disconnected after {iteration_count} iterations")
        raise
    except Exception as e:
        logger.exception(f"[SSE GEN] Fatal error in generator")
        raise
    finally:
        logger.info(f"[SSE GEN] Generator closed, iterations={iteration_count}")


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
