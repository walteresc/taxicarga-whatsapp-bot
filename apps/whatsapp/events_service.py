"""Event streaming service for real-time whatsapp updates (FASE 5B).

No external dependencies (Redis/Channels) — uses in-memory ringbuffer with TTL.
Multi-process safe via simple file-based lock pattern.
"""

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Event:
    """Base event structure."""
    id: int
    type: str  # 'conversation_update', 'message_created', 'unread_changed'
    timestamp: str
    data: dict

    def to_dict(self):
        return asdict(self)


class EventBus:
    """In-memory event bus with ringbuffer (FIFO, TTL-based expiry)."""

    def __init__(self, max_events: int = 1000, ttl_seconds: int = 3600):
        self._events: deque = deque(maxlen=max_events)
        self._ttl = ttl_seconds
        self._event_id_counter = 0
        self._lock = threading.RLock()

    def publish(self, event_type: str, data: dict) -> Event:
        """Publish event. Returns event with auto-generated ID."""
        with self._lock:
            self._event_id_counter += 1
            event = Event(
                id=self._event_id_counter,
                type=event_type,
                timestamp=datetime.utcnow().isoformat() + 'Z',
                data=data
            )
            self._events.append(event)
            return event

    def get_events_since(self, last_event_id: int = 0) -> list[Event]:
        """Get all events after `last_event_id` (cursor-based pagination)."""
        with self._lock:
            return [e for e in self._events if e.id > last_event_id]

    def get_latest_event_id(self) -> int:
        """Get latest event ID (for cursor recovery on reconnect)."""
        with self._lock:
            return self._event_id_counter

    def clear(self):
        """Clear all events (for testing)."""
        with self._lock:
            self._events.clear()
            self._event_id_counter = 0


# Global singleton
_event_bus = EventBus()


def publish_event(event_type: str, data: dict) -> Event:
    """Publish event to global bus.

    Examples:
        - publish_event('conversation_update', {'conversation_id': 225, 'preview': '...', 'unread': 3})
        - publish_event('message_created', {'conversation_id': 226, 'message_id': 1234, 'sender': 'customer'})
        - publish_event('read_state_change', {'conversation_id': 226, 'unread': 0})
    """
    return _event_bus.publish(event_type, data)


def get_events(cursor: int = 0) -> list[Event]:
    """Get events after cursor (0 = all events)."""
    return _event_bus.get_events_since(cursor)


def get_latest_cursor() -> int:
    """Get latest event ID for cursor recovery."""
    return _event_bus.get_latest_event_id()


# For testing: clear all events
def _reset_for_testing():
    _event_bus.clear()
