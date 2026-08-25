"""Redis Streams event bus for real-time updates (FASE 5B).

Replaces in-memory event bus. Supports multiple processes, persistence, cursor recovery.
"""

import json
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

# Redis configuration
def _get_redis_url():
    """Get Redis URL from settings."""
    url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
    return url

# Default values - will be overridden in class initialization
REDIS_URL = 'redis://localhost:6379/0'
EVENTS_STREAM_KEY = 'whatsapp:events'
EVENTS_MAXLEN = 10000


@dataclass
class Event:
    """Event structure matching frontend expectations."""
    id: str  # Redis stream ID (timestamp-sequence)
    type: str  # event type
    timestamp: str  # ISO format
    data: dict

    def to_dict(self):
        return asdict(self)


class RedisEventBus:
    """Redis Streams-based event bus for FASE 5B real-time.

    Uses ConnectionPool for safe multi-threaded access and automatic reconnection.
    Lazy initialization: pool and client created on first use, not in __init__.
    """

    def __init__(self, url: str = None, stream_key: str = None):
        if url is None:
            url = _get_redis_url()
        if stream_key is None:
            stream_key = getattr(settings, 'WHATSAPP_EVENTS_STREAM_KEY', 'whatsapp:events')
        self.url = url
        self.stream_key = stream_key
        self._pool = None
        self._client = None

    def _init_pool(self) -> None:
        """Lazy initialize connection pool on first use."""
        if self._pool is None:
            try:
                import threading
                logger.info(f"[REDIS] Initializing pool from thread: {threading.current_thread().name}")
                self._pool = redis.ConnectionPool.from_url(
                    self.url,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                    max_connections=10,
                    retry_on_timeout=True
                )
                logger.info(f"[REDIS] ConnectionPool initialized for {self.url} (thread={threading.current_thread().name})")
            except Exception as e:
                logger.error(f"[REDIS] Failed to initialize pool: {e}", exc_info=True)
                raise

    @property
    def redis(self) -> redis.Redis:
        """Get Redis client using connection pool (lazy initialization)."""
        if self._client is None:
            self._init_pool()
            self._client = redis.Redis(connection_pool=self._pool)
        return self._client

    def is_available(self) -> bool:
        """Check if Redis is available via PING."""
        try:
            self.redis.ping()
            return True
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"[REDIS] Connection check failed: {type(e).__name__}")
            return False
        except Exception as e:
            logger.error(f"[REDIS] Unexpected error in is_available: {e}", exc_info=True)
            return False

    def close(self) -> None:
        """Close connection pool on shutdown."""
        if self._pool is not None:
            try:
                self._pool.disconnect()
                logger.info("[REDIS] ConnectionPool closed")
            except Exception as e:
                logger.warning(f"[REDIS] Error closing pool: {e}")
            finally:
                self._pool = None
                self._client = None

    def publish(self, event_type: str, data: dict) -> Event:
        """Publish event to stream.

        Args:
            event_type: Event type (message.created, conversation.updated, etc.)
            data: Event payload

        Returns:
            Event with Redis stream ID
        """
        try:
            timestamp = datetime.utcnow().isoformat() + 'Z'

            # Add to stream
            # Returns ID like "1629372800000-0"
            event_id = self.redis.xadd(
                self.stream_key,
                {
                    'type': event_type,
                    'timestamp': timestamp,
                    'data': json.dumps(data),
                },
                maxlen=getattr(settings, 'WHATSAPP_EVENTS_MAXLEN', 10000),
                approximate=False
            )

            return Event(
                id=event_id.decode() if isinstance(event_id, bytes) else event_id,
                type=event_type,
                timestamp=timestamp,
                data=data
            )
        except Exception as e:
            logger.error(f"Failed to publish event: {e}")
            raise

    def get_events_since(self, cursor: str = '0') -> List[Event]:
        """Get all events after cursor.

        Args:
            cursor: Event ID to start after (e.g., "1629372800000-0"), or '0' for all

        Returns:
            List of events
        """
        try:
            # If cursor is '0', start from beginning, otherwise start AFTER cursor
            # XRANGE with min=X returns events with ID >= X
            # To get events AFTER cursor, use (cursor syntax (exclusive)
            if cursor == '0':
                start = '-'
            else:
                # Use exclusive range: events with ID > cursor
                start = f'({cursor}'

            # Read events
            events_raw = self.redis.xrange(self.stream_key, min=start, count=1000)

            events = []
            for event_id, event_data in events_raw:
                try:
                    event_id_str = event_id.decode() if isinstance(event_id, bytes) else event_id

                    data_dict = {}
                    for key, value in event_data.items():
                        if key == 'data':
                            # Data is stored as JSON string
                            data_dict = json.loads(value)
                        elif key == 'type':
                            event_type = value
                        elif key == 'timestamp':
                            timestamp = value

                    events.append(Event(
                        id=event_id_str,
                        type=event_type,
                        timestamp=timestamp,
                        data=data_dict
                    ))
                except Exception as e:
                    logger.error(f"Error parsing event {event_id}: {e}")
                    continue

            return events
        except Exception as e:
            logger.error(f"Failed to read events: {e}")
            return []

    def get_latest_id(self) -> Optional[str]:
        """Get the latest event ID in stream."""
        try:
            result = self.redis.xrevrange(self.stream_key, count=1)
            if result:
                event_id = result[0][0]
                return event_id.decode() if isinstance(event_id, bytes) else event_id
            return '0'
        except Exception as e:
            logger.error(f"Failed to get latest ID: {e}")
            return '0'

    def check_cursor_valid(self, cursor: str) -> bool:
        """Check if cursor exists in stream (for resync detection)."""
        if cursor == '0':
            return True
        try:
            # Try to read from that ID
            result = self.redis.xrange(self.stream_key, min=cursor, max=cursor, count=1)
            return len(result) > 0
        except Exception:
            return False

    def health_check(self) -> Dict[str, Any]:
        """Return health status."""
        return {
            'available': self.is_available(),
            'stream_key': self.stream_key,
            'stream_length': self.redis.xlen(self.stream_key) if self.is_available() else 0,
        }

    def clear(self):
        """Clear stream (for testing only)."""
        try:
            self.redis.delete(self.stream_key)
        except Exception as e:
            logger.error(f"Failed to clear stream: {e}")


def get_event_bus() -> RedisEventBus:
    """Get Redis event bus.

    Creates a fresh instance each time to avoid post-fork socket corruption
    in gunicorn gthread workers. The lazy connection in RedisEventBus ensures
    socket is created in the correct process context.
    """
    return RedisEventBus()


def publish_event(event_type: str, data: dict) -> Optional[Event]:
    """Publish event to Redis stream."""
    try:
        bus = get_event_bus()
        return bus.publish(event_type, data)
    except Exception as e:
        logger.error(f"Event publishing failed: {e}")
        return None


def get_events(cursor: str = '0') -> List[Event]:
    """Get events from Redis since cursor."""
    try:
        bus = get_event_bus()
        return bus.get_events_since(cursor)
    except Exception as e:
        logger.error(f"Event retrieval failed: {e}")
        return []


def get_latest_cursor() -> str:
    """Get latest event ID."""
    try:
        bus = get_event_bus()
        return bus.get_latest_id() or '0'
    except Exception:
        return '0'
