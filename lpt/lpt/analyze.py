import dataclasses
import datetime
import logging
from typing import Any, Dict, List, Optional

from .cloudinit import CloudInit, CloudInitFrame
from .event import Event, EventSeverity
from .journal import Journal
from .systemd import Systemd, SystemdUnit

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class Unit:
    name: str
    duration: Optional[float]
    finished: float
    dependencies: List[str]
    failed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_systemd_unit(cls, unit: SystemdUnit) -> "Unit":
        """Convert systemd unit."""
        name = unit.unit
        duration = unit.get_time_to_activate()
        if not duration:
            duration = 0
        duration = round(duration, 4)

        finished = unit.get_time_of_activation()
        finished = round(finished, 4)
        failed = unit.is_failed()

        return cls(
            name=name,
            duration=duration,
            finished=finished,
            dependencies=[],
            failed=failed,
        )

    @classmethod
    def from_cloudinit_frame(cls, frame: CloudInitFrame) -> "Unit":
        """Convert cloud-init frame."""
        name = frame.name
        duration = frame.get_time_to_complete()
        if not duration:
            duration = 0
        duration = round(duration, 4)

        finished = frame.get_time_of_completion()
        finished = round(finished, 4)
        failed = frame.is_failed()
        dependencies = [f.name for f in frame.children]

        return cls(
            name=name,
            duration=duration,
            finished=finished,
            dependencies=dependencies,
            failed=failed,
        )


@dataclasses.dataclass
class EventData:
    events: List[dict]
    warnings: List[dict]
    units: Dict[str, dict]


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

    if systemd:
        json_units: Dict[str, Dict[str, Any]] = {}
        units = analyze_units(cloudinits=cloudinits, systemd=systemd).items()
        for k, v in units:
            json_units[k] = v.as_dict()
    else:
        json_units = {}

    return EventData(events=event_dicts, warnings=warnings, units=json_units)


def analyze_units(
    *,
    cloudinits: List[CloudInit],
    systemd: Systemd,
    filter_conditional_result_no: bool = False,
    filter_inactive: bool = True,
    filter_services: Optional[List[str]] = None,
    service_name: str = "multi-user.target",
) -> Dict[str, Unit]:
    if filter_services is None:
        filter_services = []

    if cloudinits:
        cloudinit = cloudinits[-1]
        frames = cloudinit.get_frames()
    else:
        frames = []

    units: Dict[str, Unit] = {}

    def _walk_frame_dependencies() -> None:
        roots = [f for f in frames if f.parent is None and f.service in units.keys()]
        seen = set()

        def _walk_dependencies(frame: CloudInitFrame) -> None:
            # logger.debug("walking: %s", frame)
            if frame in seen:
                # logger.debug("seen: %s", frame)
                return

            seen.add(frame)
            unit = Unit.from_cloudinit_frame(frame)
            units[frame.name] = unit

            for child in frame.children:
                _walk_dependencies(child)

        for root in roots:
            _walk_dependencies(root)

    def _walk_unit_dependencies() -> None:
        seen = set()

        def _walk_dependencies(service_name: str) -> None:
            # logger.debug("walking: %s", service_name)
            if service_name in seen:
                # logger.debug("seen: %s", service_name)
                return

            seen.add(service_name)

            service = systemd.units.get(service_name)
            if service is None:
                logger.debug("service not found: %r", systemd.units)
                return

            unit_deps = set()
            for name in service.after:
                dependency = systemd.units.get(name)
                if dependency is None:
                    continue

                if not dependency.is_active():
                    continue

                if name in filter_services:  # type: ignore
                    continue

                if filter_conditional_result_no and not dependency.condition_result:
                    continue

                if filter_inactive and not dependency.active_enter_timestamp_monotonic:
                    continue

                unit_deps.add(name)
                _walk_dependencies(name)

            unit = Unit.from_systemd_unit(service)
            unit.dependencies = sorted(unit_deps)
            units[service_name] = unit

        _walk_dependencies(service_name)

    _walk_unit_dependencies()
    _walk_frame_dependencies()

    # Add cloud-init frames.
    for service_name in [
        "cloud-init-local.service",
        "cloud-init.service",
        "cloud-config.service",
        "cloud-final.service",
    ]:
        service = units.get(service_name)
        if service is None:
            continue

        service_frames = [
            f.name for f in frames if f.service == service_name and f.parent is None
        ]
        service.dependencies.extend(service_frames)

    for _, unit in units.items():
        unit.dependencies = sorted(set(unit.dependencies))

    return units
