import dataclasses
import datetime
import logging
import re
from collections import deque
from pathlib import Path
from typing import FrozenSet, List, Optional, Union

import dateutil.parser

from .event import Event, EventSeverity
from .ssh import SSH
from .time import calculate_reference_timestamp

logger = logging.getLogger(__name__)


@dataclasses.dataclass(eq=True)
class CloudInitFrame(Event):
    stage: str
    module: str
    timestamp_realtime_finish: datetime.datetime
    timestamp_realtime_start: datetime.datetime
    timestamp_monotonic_finish: float
    timestamp_monotonic_start: float
    duration: float
    result: str
    parent: Optional["CloudInitFrame"]
    children: FrozenSet["CloudInitFrame"]

    def __hash__(self):
        return id(self)

    def get_time_to_complete(self) -> float:
        return self.timestamp_monotonic_finish - self.timestamp_monotonic_start

    def get_time_of_completion(self) -> float:
        return self.timestamp_monotonic_finish

    def is_failed(self) -> bool:
        return self.result != "SUCCESS"

    def as_dict(self) -> dict:
        obj = super().as_dict()

        parent = obj.pop("parent")
        if parent:
            obj["parent"] = "/".join([parent.stage, parent.module])

        children = obj.pop("children")
        obj["children"] = ["/".join([c.stage, c.module]) for c in children]
        return obj


@dataclasses.dataclass
class CloudInitEvent(Event):
    log_line: str
    log_level: str
    message: str
    result: Optional[str]
    timestamp_realtime: datetime.datetime
    timestamp_monotonic: float
    event_type: str
    stage: Optional[str]
    module: str
    python_module: str


@dataclasses.dataclass
class CloudInitEntry:
    log_line: str
    log_level: str
    message: str
    module: Optional[str]
    python_module: Optional[str]
    result: Optional[str]
    timestamp_realtime: datetime.datetime
    timestamp_monotonic: float
    event_type: str
    stage: Optional[str]

    @classmethod
    def parse(
        cls, log_line: str, reference_monotonic: Optional[datetime.datetime] = None
    ) -> "CloudInitEntry":
        line_match = re.search(r"(.*) - (.*)\[(.*)\]: (.*)", log_line)
        if line_match is None:
            raise ValueError(f"unable to parse: {log_line}")

        ts, python_module, log_level, message = line_match.groups()
        timestamp_realtime = cls.convert_timestamp_to_datetime(ts)

        if message.startswith("start:"):
            event_type = "start"
        elif message.startswith("finish:"):
            event_type = "finish"

        event_type = "log"
        result = None
        stage = None
        module = None

        # Finish event
        if message.startswith("finish:"):
            split = message.split(": ")
            event_type = split[0]
            module = split[1]
            result = split[2]
            message = ": ".join(split[3:])

        # Start event
        if message.startswith("start:"):
            split = message.split(": ")
            event_type = split[0]
            module = split[1]
            message = ": ".join(split[2:])

        if module and any(
            module.startswith(s)
            for s in [
                "init-local",
                "init-network",
                "modules-config",
                "modules-final",
            ]
        ):
            stage, module = module.split("/", 1)

        entry = cls(
            log_line=log_line,
            event_type=event_type,
            log_level=log_level,
            message=message,
            module=module,
            python_module=python_module,
            result=result,
            stage=stage,
            timestamp_realtime=timestamp_realtime,
            timestamp_monotonic=0.0,
        )

        if reference_monotonic:
            entry.estimate_timestamp_monotonic(reference_monotonic)
        else:
            entry.check_for_monotonic_reference()

        return entry

    @staticmethod
    def convert_timestamp_to_datetime(timestamp: str) -> datetime.datetime:
        return dateutil.parser.isoparse(timestamp)

    def estimate_timestamp_monotonic(
        self, reference_monotonic: datetime.datetime
    ) -> None:
        self.timestamp_monotonic = (
            self.timestamp_realtime - reference_monotonic
        ).total_seconds()

    def check_for_monotonic_reference(self) -> Optional[datetime.datetime]:
        uptime_match = re.search(".* Up (.*) seconds", self.message)
        if not uptime_match:
            return None

        monotonic_time = float(uptime_match.groups()[0])
        reference_monotonic = calculate_reference_timestamp(
            self.timestamp_realtime, monotonic_time
        )
        self.estimate_timestamp_monotonic(reference_monotonic)
        return reference_monotonic

    def is_start_of_boot_record(self) -> bool:
        return bool(re.search("Cloud-init .* running 'init-local'", self.message))

    def as_event(
        self, label: str, *, severity: EventSeverity = EventSeverity.INFO
    ) -> CloudInitEvent:
        return CloudInitEvent(
            **self.__dict__, label=label, source="cloudinit", severity=severity
        )


@dataclasses.dataclass
class CloudInit:
    logs: str
    entries: List[CloudInitEntry]
    reference_monotonic: Optional[datetime.datetime]

    @classmethod
    def load_remote(
        cls,
        ssh: SSH,
        *,
        output_dir: Path,
    ) -> List["CloudInit"]:
        remote_path = Path("/var/log/cloud-init.log")
        local_path = output_dir / "cloud-init.log"
        try:
            ssh.fetch(remote_path, local_path)
        except FileNotFoundError:
            return []
        return cls.load(local_path, output_dir=output_dir)

    @classmethod
    def load(  # pylint: disable=too-many-branches,too-many-locals
        cls,
        path: Path = Path("/var/log/cloud-init.log"),
        *,
        output_dir: Path,
    ) -> List["CloudInit"]:
        """Parse cloud-init log and split by boot."""
        cloudinits = []
        boot_entries: List[CloudInitEntry] = []
        boot_logs: List[str] = []
        reference_monotonic = None
        last_timestamp = None
        last_stage = "init-local"

        logs = path.read_text(encoding="utf-8")

        output_log = output_dir / "cloud-init.log"
        if path != output_log:
            output_log.write_text(logs)

        for line in logs.splitlines():
            try:
                entry = CloudInitEntry.parse(line, reference_monotonic)
            except ValueError:
                continue
            finally:
                boot_logs.append(line)

            for stage in [
                "init-local",
                "init-network",
                "modules-config",
                "modules-final",
            ]:
                if entry.stage and entry.stage.startswith(stage):
                    last_stage = stage

            if not entry.stage:
                entry.stage = last_stage

            # Due to low resolution, add a microsecond to timestamp if it
            # matches the previous record.
            if (
                last_timestamp is not None
                and entry.timestamp_realtime <= last_timestamp
            ):
                entry.timestamp_realtime = last_timestamp + datetime.timedelta(
                    microseconds=1
                )
            last_timestamp = entry.timestamp_realtime

            timestamp = entry.check_for_monotonic_reference()
            if timestamp is not None:
                reference_monotonic = timestamp

            if entry.is_start_of_boot_record() and boot_entries:
                # New boot, ensure all entries have estimated monotonic.
                for entry in boot_entries:
                    if entry.timestamp_monotonic == 0.0 and reference_monotonic:
                        entry.estimate_timestamp_monotonic(reference_monotonic)

                boot_cloudinit = CloudInit(
                    entries=boot_entries,
                    reference_monotonic=reference_monotonic,
                    logs="\n".join(boot_logs),
                )
                cloudinits.append(boot_cloudinit)
                boot_entries = [entry]
                boot_logs = []
                last_stage = "init-local"
            else:
                boot_entries.append(entry)

        if boot_entries:
            boot_cloudinit = CloudInit(
                entries=boot_entries,
                reference_monotonic=reference_monotonic,
                logs="\n".join(boot_logs),
            )
            cloudinits.append(boot_cloudinit)
        return cloudinits

    def find_entries(
        self, pattern, *, event_type: Optional[str] = None
    ) -> List[CloudInitEntry]:
        return [
            e
            for e in self.entries
            if re.search(pattern, e.message)
            and (event_type is None or event_type == e.event_type)
        ]

    def get_frames(self) -> List[CloudInitFrame]:
        frames: List[CloudInitFrame] = []
        stack: deque[CloudInitFrame] = deque()

        for entry in self.entries:
            try:
                parent = stack[-1]
            except IndexError:
                parent = None

            if entry.event_type == "start":
                assert entry.module
                assert entry.stage

                frame = CloudInitFrame(
                    source="cloudinit",
                    label="CLOUDINIT_FRAME",
                    timestamp_realtime=entry.timestamp_realtime,
                    timestamp_monotonic=entry.timestamp_monotonic,
                    duration=0,
                    stage=entry.stage,
                    module=entry.module,
                    timestamp_realtime_finish=entry.timestamp_realtime,
                    timestamp_monotonic_finish=0,
                    timestamp_realtime_start=entry.timestamp_realtime,
                    timestamp_monotonic_start=entry.timestamp_monotonic,
                    children=frozenset(),
                    parent=parent,
                    result="INCOMPLETE",
                    severity=EventSeverity.WARNING,
                )

                if parent:
                    children = set(parent.children)
                    children.add(frame)
                    parent.children = frozenset(children)

                frames.append(frame)
                stack.append(frame)

            if entry.event_type == "finish":
                try:
                    frame = stack.pop()
                except IndexError:
                    logger.debug("Ignoring finish event without start: %r", entry)
                    continue

                assert entry.module
                assert entry.result
                assert entry.stage
                assert frame.stage == entry.stage
                assert frame.module == entry.module

                frame.timestamp_realtime_finish = entry.timestamp_realtime
                frame.timestamp_monotonic_finish = entry.timestamp_monotonic
                frame.duration = (
                    entry.timestamp_monotonic - frame.timestamp_monotonic_start
                )
                frame.result = entry.result
                if (
                    frame.result == "SUCCESS"
                    or frame.module == "azure-ds/load_azure_ds_dir"
                ):
                    frame.severity = EventSeverity.INFO

        return frames

    def get_events_of_interest(  # pylint:disable=too-many-branches
        self,
    ) -> List[Union[CloudInitEvent, CloudInitFrame]]:
        events: List[Union[CloudInitEvent, CloudInitFrame]] = []

        events.extend(self.get_frames())

        for entry in self.find_entries("running 'init-local'"):
            events.append(entry.as_event("CLOUDINIT_RUNNING_INIT_LOCAL"))

        for entry in self.find_entries("running 'init'"):
            events.append(entry.as_event("CLOUDINIT_RUNNING_INIT"))

        for entry in self.find_entries("running 'modules:config'"):
            events.append(entry.as_event("CLOUDINIT_RUNNING_MODULES_CONFIG"))

        for entry in self.find_entries("running 'modules:final'"):
            events.append(entry.as_event("CLOUDINIT_RUNNING_MODULES_FINAL"))

        for entry in self.find_entries("finished at"):
            events.append(entry.as_event("CLOUDINIT_FINISHED"))

        for entry in self.find_entries("PPS type:"):
            events.append(entry.as_event("CLOUDINIT_PPS_TYPE"))

        for entry in self.find_entries("PreprovisionedVMType:"):
            events.append(entry.as_event("CLOUDINIT_PPS_TYPE"))

        for entry in self.find_entries("", event_type="start"):
            events.append(entry.as_event("CLOUDINIT_FRAME_START"))

        for entry in self.find_entries("", event_type="finish"):
            events.append(entry.as_event("CLOUDINIT_FRAME_FINISH"))

        for entry in self.find_entries("ERROR"):
            events.append(
                entry.as_event("CLOUDINIT_ERROR", severity=EventSeverity.WARNING)
            )

        for entry in self.find_entries("WARNING"):
            events.append(
                entry.as_event("CLOUDINIT_WARNING", severity=EventSeverity.WARNING)
            )

        for entry in self.find_entries("CRITICAL"):
            events.append(
                entry.as_event("CLOUDINIT_CRITICAL", severity=EventSeverity.WARNING)
            )

        for entry in self.find_entries("Traceback"):
            events.append(
                entry.as_event("CLOUDINIT_TRACEBACK", severity=EventSeverity.WARNING)
            )

        failed_entries = [e for e in self.entries if e.result not in (None, "SUCCESS")]
        for entry in failed_entries:
            if entry.message == "load_azure_ds_dir":
                continue
            events.append(
                entry.as_event(
                    f"CLOUDINIT_UNEXPECTED_FAILURE {entry.result}",
                    severity=EventSeverity.WARNING,
                )
            )

        for entry in self.find_entries("FAIL"):
            if "load_azure_ds_dir" in entry.message:
                continue
            events.append(
                entry.as_event("CLOUDINIT_FAIL", severity=EventSeverity.WARNING)
            )

        for entry in self.find_entries("_get_data", event_type="start")[1:]:
            events.append(
                entry.as_event(
                    "CLOUDINIT_UNEXPECTED_GET_DATA", severity=EventSeverity.WARNING
                )
            )

        return events
