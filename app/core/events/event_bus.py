# app/core/events/event_bus.py
# =======================================================================================
from typing import Dict, List, Callable, Any
import logging
from dataclasses import dataclass
from datetime import datetime
import threading


@dataclass
class Event:
    type: str
    data: Dict[str, Any]
    timestamp: datetime
    source: str = "unknown"


class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._event_history: List[Event] = []
        self._max_history = 1000
        self._lock = threading.RLock()

    def subscribe(self, event_type: str, handler: Callable[[Event], None]):
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)

    def publish(self, event_type: str, data: Dict[str, Any], source: str = "unknown"):
        event = Event(type=event_type, data=data,
                      timestamp=datetime.now(), source=source)
        with self._lock:
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history.pop(0)
            handlers = self._subscribers.get(event_type, []).copy()

        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logging.error(f"Error in event handler for {event_type}: {e}")
