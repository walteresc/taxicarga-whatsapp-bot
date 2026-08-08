from datetime import datetime
from typing import Protocol

from django.utils import timezone


class MetaSenderPort(Protocol):
    def send(self, payload: dict) -> dict: ...


class ChatwootClientPort(Protocol):
    def publish(self, payload: dict) -> dict: ...


class AttachmentStoragePort(Protocol):
    def store(self, content: bytes, metadata: dict) -> str: ...


class ClockPort(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return timezone.now()
