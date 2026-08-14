"""
Request lifecycle enums and types (no circular imports).
"""

from enum import Enum
from datetime import timedelta


class RequestIntent(str, Enum):
    NEW_REQUEST = "NEW_REQUEST"
    CONTINUE_REQUEST = "CONTINUE_REQUEST"
    UNCERTAIN = "UNCERTAIN"
    NO_REQUEST_SIGNAL = "NO_REQUEST_SIGNAL"
    RESUME_PREVIOUS_REQUEST = "RESUME_PREVIOUS_REQUEST"


class RequestLifecycleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    CLOSED = "CLOSED"


# Business rule: Lead is DORMANT if no activity for this duration
INACTIVITY_THRESHOLD = timedelta(hours=2)
