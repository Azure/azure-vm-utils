import dataclasses
import datetime
import logging
from typing import List, Optional

from .cloudinit import CloudInit
from .event import Event, EventSeverity
from .journal import Journal
from .systemd import Systemd

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class EventData:
    events: List[dict]
    warnings: List[dict]


def analyze_events(
    *,
    journals: List[Journal],
    cloudinits: List[CloudInit],
    systemd: Optional[Systemd],
    boot: bool = True,
    event_types: Optional[List[str]] = None,
) -> EventData:
    events: List[Event] = []

    if boot:
        cloudinits = cloudinits[-1:]
        journals = journals[-1:]

    for journal in journals:
        events.extend(journal.get_events_of_interest())

    for cloudinit in cloudinits:
        events.extend(cloudinit.get_events_of_interest())

    if systemd:
        events.extend(systemd.get_events_of_interest())

    if not cloudinits:
        events.append(
            Event(
                label="CLOUDINIT_LOGS_MISSING",
                source="analyze",
                timestamp_realtime=datetime.datetime.utcnow(),
                timestamp_monotonic=0.0,
                severity=EventSeverity.WARNING,
            )
        )

    for event in events:
        assert isinstance(event.timestamp_realtime, datetime.datetime), repr(event)

    events = sorted(events, key=lambda x: x.timestamp_monotonic)
    if event_types:
        events = [e for e in events if e.label in event_types]

    event_dicts = [e.as_dict() for e in events]
    warnings = [e for e in event_dicts if e.get("severity", "info") == "warning"]

    return EventData(events=event_dicts, warnings=warnings)
