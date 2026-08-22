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
REDIS_URL = settings.REDIS_URL if hasattr(settings, 'REDIS_URL') else 'redis://localhost:6379/0'
EVENTS_STREAM_KEY = getattr(settings, 'WHATSAPP_EVENTS_STREAM_KEY', 'whatsapp:events')
EVENTS_MAXLEN = getattr(settings, 'WHATSAPP_EVENTS_MAXLEN', 10000)


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
    """Redis Streams-based event bus for FASE 5B real-time."""

    def __init__(self, url: str = REDIS_URL, stream_key: str = EVENTS_STREAM_KEY):
        self.url = url
        self.stream_key = stream_key
        self._redis: Optional[redis.Redis] = None

    @property
    def redis(self) -> redis.Redis:
        """Lazy connection to Redis."""
        if self._redis is None:
            try:
                self._redis = redis.from_url(self.url, decode_responses=True)
                self._redis.ping()
            except Exception as e:
                logger.error(f"Redis connection failed: {e}")
                raise
        return self._redis

    def is_available(self) -> bool:
        """Check if Redis is available."""
        try:
            self.redis.ping()
            return True
        except Exception as e:
            logger.warning(f"Redis unavailable: {e}")
            return False

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
                maxlen=EVENTS_MAXLEN,
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
            # If cursor is '0', start from beginning
            start = cursor if cursor != '0' else '-'

            # Read events
            events_raw = self.redis.xrange(self.stream_key, min=start, count=1000)

            events = []
            for event_id, event_data in events_raw:
                try:
                    event_id_str = event_id.decode() if isinstance(event_id, bytes) else event_id

                    # Skip if this is the cursor itself (we want after, not including)
                    if cursor != '0' and event_id_str == cursor:
                        continue

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


# Global singleton
_event_bus: Optional[RedisEventBus] = None


def get_event_bus() -> RedisEventBus:
    """Get or create Redis event bus singleton."""
    global _event_bus
    if _event_bus is None:
        _event_bus = RedisEventBus()
    return _event_bus


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
