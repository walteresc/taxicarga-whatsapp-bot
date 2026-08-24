"""
Event tracing middleware for end-to-end diagnostics.
Logs all 17 checkpoints with unique correlation IDs.
"""
import logging
import json
import hashlib
from datetime import datetime

logger = logging.getLogger(__name__)

class EventTrace:
    """Correlate event across webhook→DB→Redis→SSE→DOM"""

    def __init__(self, event_id, wamid, message_type='inbound'):
        self.event_id = event_id
        self.wamid = wamid
        self.message_type = message_type
        self.trace_id = hashlib.md5(f"{event_id}-{wamid}".encode()).hexdigest()[:8]
        self.checkpoints = {}

    def log(self, checkpoint_num, checkpoint_name, data=None):
        """Log checkpoint with timestamp"""
        ts = datetime.now().isoformat()
        self.checkpoints[checkpoint_num] = {
            'name': checkpoint_name,
            'timestamp': ts,
            'data': data
        }

        # Format: [TRACE-XXXX] [CP-N] checkpoint_name: data
        msg = f"[TRACE-{self.trace_id}] [CP-{checkpoint_num}] {checkpoint_name}"
        if data:
            msg += f": {data}"
        logger.warning(msg)

    def summary(self):
        """Print all checkpoints"""
        logger.warning(f"\n[TRACE-{self.trace_id}] CHECKPOINT SUMMARY:")
        for cp_num in sorted(self.checkpoints.keys()):
            cp = self.checkpoints[cp_num]
            logger.warning(f"  [{cp_num}] {cp['name']} - {cp['timestamp']}")
