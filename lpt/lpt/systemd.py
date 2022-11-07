import dataclasses
import datetime
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional

from .event import Event, EventSeverity
from .ssh import SSH

logger = logging.getLogger(__name__)


def convert_systemctl_timestamp(
    timestamp: Optional[str],
) -> Optional[datetime.datetime]:
    if not timestamp or timestamp == "n/a":
        return None

    return datetime.datetime.strptime(timestamp, "%a %Y-%m-%d %H:%M:%S %Z")


def convert_systemctl_timestamp_monotonic(timestamp: Optional[str]) -> Optional[float]:
    if not timestamp:
        return None

    return float(timestamp) / 1000000


def convert_systemctl_bool(value: str) -> bool:
    return not value == "no"


@dataclasses.dataclass
class SystemdEvent(Event):
    pass


@dataclasses.dataclass
class SystemdSystemEvent(SystemdEvent):
    userspace_timestamp: datetime.datetime
    userspace_timestamp_monotonic: float
    finish_timestamp: datetime.datetime
    finish_timestamp_monotonic: float
    system_state: str


@dataclasses.dataclass
class SystemdUnitEvent(SystemdEvent):
    unit: str
    time_to_activate: Optional[float]
    time_of_activation: Optional[float]
    status: str


@dataclasses.dataclass(frozen=True, eq=True)
class SystemdUnitList:
    unit: str
    active: str
    load: str
    sub: str
    description: str

    def is_failed(self) -> bool:
        return self.active == "failed"

    def is_active(self) -> bool:
        return self.active != "inactive"

    @classmethod
    def parse_list(cls, list_properties: dict) -> "SystemdUnitList":
        unit = list_properties["unit"]
        active = list_properties["active"]
        load = list_properties["load"]
        sub = list_properties["sub"]
        description = list_properties["description"]

        return cls(
            unit=unit, active=active, load=load, sub=sub, description=description
        )

    @classmethod
    def parse_legacy_line(cls, line: str) -> "SystemdUnitList":
        parts = line.strip().split()
        logger.debug("parsing legacy line: %r", parts)
        try:
            if parts[0] == "UNIT":
                raise ValueError(f"skipping header: {parts}")

            unit = parts[0]
            if unit == "●":
                parts = parts[1:]
                unit = parts[0]

            load = parts[1]
            active = parts[2]
            sub = parts[3]
            description = " ".join(parts[4:])
        except IndexError as exc:
            raise ValueError(f"not a valid unit: {parts}") from exc

        return cls(
            unit=unit, active=active, load=load, sub=sub, description=description
        )


@dataclasses.dataclass(frozen=True, eq=True)
class SystemdUnitShow:
    after: FrozenSet[str]
    condition_result: Optional[bool]
    exec_main_start_timestamp: Optional[datetime.datetime]
    exec_main_exit_timestamp: Optional[datetime.datetime]
    active_enter_timestamp: Optional[datetime.datetime]
    inactive_enter_timestamp: Optional[datetime.datetime]
    inactive_exit_timestamp: Optional[datetime.datetime]
    exec_main_start_timestamp_monotonic: Optional[float]
    exec_main_exit_timestamp_monotonic: Optional[float]
    active_enter_timestamp_monotonic: Optional[float]
    inactive_enter_timestamp_monotonic: Optional[float]
    inactive_exit_timestamp_monotonic: Optional[float]

    def get_time_to_activate(self) -> float:
        if (
            self.active_enter_timestamp_monotonic
            and self.inactive_exit_timestamp_monotonic
        ):
            return (
                self.active_enter_timestamp_monotonic
                - self.inactive_exit_timestamp_monotonic
            )

        if (
            self.exec_main_exit_timestamp_monotonic
            and self.exec_main_start_timestamp_monotonic
        ):
            return (
                self.exec_main_exit_timestamp_monotonic
                - self.exec_main_start_timestamp_monotonic
            )

        if (
            self.inactive_exit_timestamp_monotonic
            and self.inactive_enter_timestamp_monotonic
        ):
            # Service may have failed to start.
            return (
                self.inactive_exit_timestamp_monotonic
                - self.inactive_enter_timestamp_monotonic
            )

        raise ValueError(f"unable to determine time to activate: {self}")

    def get_time_of_activation(self) -> float:
        if self.active_enter_timestamp_monotonic:
            return self.active_enter_timestamp_monotonic

        if self.exec_main_exit_timestamp_monotonic:
            return self.exec_main_exit_timestamp_monotonic

        if self.inactive_exit_timestamp_monotonic:
            # Service may have failed to start.
            return self.inactive_exit_timestamp_monotonic

        raise ValueError(f"unable to determine time of completion: {self}")

    def get_time_of_activation_realtime(self) -> datetime.datetime:
        if self.active_enter_timestamp:
            return self.active_enter_timestamp

        if self.exec_main_exit_timestamp:
            return self.exec_main_exit_timestamp

        if self.inactive_exit_timestamp:
            # Service may have failed to start.
            return self.inactive_exit_timestamp

        raise ValueError(f"unable to determine realtime of completion: {self}")

    @classmethod
    def parse_show(cls, show_properties: dict) -> "SystemdUnitShow":
        after = frozenset(show_properties.get("After", "").split())
        condition_result = show_properties.get("ConditionResult")
        if condition_result:
            condition_result = convert_systemctl_bool(condition_result)

        # Realtime timestamps.
        active_enter_timestamp = convert_systemctl_timestamp(
            show_properties.get("ActiveEnterTimestamp")
        )
        inactive_exit_timestamp = convert_systemctl_timestamp(
            show_properties.get("InactiveExitTimestamp")
        )
        inactive_enter_timestamp = convert_systemctl_timestamp(
            show_properties.get("InactiveEnterTimestamp")
        )

        exec_main_start_timestamp = convert_systemctl_timestamp(
            show_properties.get("ExecMainStartTimestamp")
        )

        exec_main_exit_timestamp = convert_systemctl_timestamp(
            show_properties.get("ExecMainExitTimestamp")
        )

        # Monotonic timestamps.
        active_enter_timestamp_monotonic = convert_systemctl_timestamp_monotonic(
            show_properties.get("ActiveEnterTimestampMonotonic")
        )
        inactive_exit_timestamp_monotonic = convert_systemctl_timestamp_monotonic(
            show_properties.get("InactiveExitTimestampMonotonic")
        )
        inactive_enter_timestamp_monotonic = convert_systemctl_timestamp_monotonic(
            show_properties.get("InactiveEnterTimestampMonotonic")
        )

        exec_main_start_timestamp_monotonic = convert_systemctl_timestamp_monotonic(
            show_properties.get("ExecMainStartTimestampMonotonic")
        )

        exec_main_exit_timestamp_monotonic = convert_systemctl_timestamp_monotonic(
            show_properties.get("ExecMainExitTimestampMonotonic")
        )

        return cls(
            after=after,
            condition_result=condition_result,
            exec_main_start_timestamp=exec_main_start_timestamp,
            exec_main_exit_timestamp=exec_main_exit_timestamp,
            active_enter_timestamp=active_enter_timestamp,
            inactive_enter_timestamp=inactive_enter_timestamp,
            inactive_exit_timestamp=inactive_exit_timestamp,
            exec_main_start_timestamp_monotonic=exec_main_start_timestamp_monotonic,
            exec_main_exit_timestamp_monotonic=exec_main_exit_timestamp_monotonic,
            active_enter_timestamp_monotonic=active_enter_timestamp_monotonic,
            inactive_enter_timestamp_monotonic=inactive_enter_timestamp_monotonic,
            inactive_exit_timestamp_monotonic=inactive_exit_timestamp_monotonic,
        )


@dataclasses.dataclass(frozen=True, eq=True)
class SystemdUnit(SystemdUnitShow, SystemdUnitList):
    @classmethod
    def parse(cls, *, list_properties: dict, show_properties: dict) -> "SystemdUnit":
        unit_list = SystemdUnitList.parse_list(list_properties)
        unit_show = SystemdUnitShow.parse_show(show_properties)

        return cls(**unit_list.__dict__, **unit_show.__dict__)

    def is_viable_event(self) -> bool:
        try:
            self.get_time_to_activate()
            self.get_time_of_activation()
            self.get_time_of_activation_realtime()
        except ValueError:
            return False

        return True

    def as_dict(self) -> dict:
        obj = self.__dict__.copy()
        obj["after"] = sorted(self.after)
        for k, v in obj.items():
            if isinstance(v, datetime.datetime):
                obj[k] = str(v)
        return obj

    def as_event(self) -> SystemdUnitEvent:
        if self.is_failed():
            severity = EventSeverity.WARNING
        else:
            severity = EventSeverity.INFO

        time_to_activate = self.get_time_to_activate()
        time_of_activation = self.get_time_of_activation()
        time_of_activation_realtime = self.get_time_of_activation_realtime()

        return SystemdUnitEvent(
            label="SYSTEMD_UNIT",
            source="systemd",
            unit=self.unit,
            time_to_activate=time_to_activate,
            time_of_activation=time_of_activation,
            timestamp_monotonic=time_of_activation,
            timestamp_realtime=time_of_activation_realtime,
            status=self.active,
            severity=severity,
        )


class Systemctl:
    @classmethod
    def show(
        cls,
        service_name: Optional[str] = None,
        *,
        run=subprocess.run,
    ) -> str:
        cmd = ["systemctl", "show"]
        if service_name is not None:
            cmd.extend(["--", service_name])
        try:
            logger.debug("Executing: %r", cmd)
            proc = run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            logger.error("cmd (%r) failed (error=%r), retrying as sudo", cmd, error)
            cmd.insert(0, "sudo")
            proc = run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                logger.error("unable to show systemd unit for %s", service_name)
                return ""

        return proc.stdout

    @classmethod
    def parse_show(cls, show_output: str) -> Dict[str, str]:
        properties = {}

        for line in show_output.strip().splitlines():
            line = line.strip()
            try:
                key, value = line.split("=", 1)
            except ValueError:
                logger.debug("failed to parse: %r", line)
                continue

            properties[key] = value

        return properties

    @classmethod
    def list_units(cls, *, run=subprocess.run) -> str:
        cmd = ["systemctl", "list-units", "--all", "-o", "json", "--no-pager"]
        try:
            logger.debug("Executing: %r", cmd)
            proc = run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            logger.error("cmd (%r) failed (error=%r)", cmd, error)
            raise
        return proc.stdout

    @classmethod
    def parse_list_units(cls, list_units_output: str) -> Dict[str, SystemdUnitList]:
        try:
            unit_list = json.loads(list_units_output)
            return {u["unit"]: SystemdUnitList.parse_list(u) for u in unit_list}
        except json.JSONDecodeError:
            logger.warning(
                "failed to parse systemctl as json, falling back to legacy mode"
            )

        return cls.parse_list_units_legacy(list_units_output)

    @classmethod
    def parse_list_units_legacy(
        cls, list_units_output: str
    ) -> Dict[str, SystemdUnitList]:
        """Fall back to parsing non-json output."""
        units = {}

        # First line is header skip it.
        for line in list_units_output.strip().splitlines():
            line = line.strip()

            # A blank line is before the legend, stop here.
            if not line:
                break

            try:
                unit = SystemdUnitList.parse_legacy_line(line)
            except ValueError:
                continue

            units[unit.unit] = unit

        return units


@dataclasses.dataclass(frozen=True, eq=True)
class Systemd:
    units: Dict[str, SystemdUnit]
    userspace_timestamp: datetime.datetime
    userspace_timestamp_monotonic: float
    finish_timestamp: datetime.datetime
    finish_timestamp_monotonic: float
    system_state: str

    def as_event(self) -> SystemdSystemEvent:
        if self.system_state != "running":
            severity = EventSeverity.WARNING
        else:
            severity = EventSeverity.INFO

        return SystemdSystemEvent(
            label="SYSTEMD_SYSTEM",
            source="systemd",
            timestamp_monotonic=self.finish_timestamp_monotonic,
            timestamp_realtime=self.finish_timestamp,
            userspace_timestamp=self.userspace_timestamp,
            userspace_timestamp_monotonic=self.userspace_timestamp_monotonic,
            finish_timestamp=self.finish_timestamp,
            finish_timestamp_monotonic=self.finish_timestamp_monotonic,
            system_state=self.system_state,
            severity=severity,
        )

    def get_events_of_interest(
        self,
    ) -> List[SystemdEvent]:
        events: List[SystemdEvent] = []

        events.extend(
            [u.as_event() for u in self.units.values() if u.is_viable_event()]
        )

        system_event = self.as_event()
        events.append(system_event)

        return events

    @classmethod
    def load_remote(cls, ssh: SSH, *, output_dir: Path) -> "Systemd":
        return cls.load(output_dir=output_dir, run=ssh.run)

    @classmethod
    def load(cls, *, output_dir: Path, run=subprocess.run) -> "Systemd":
        units = {}
        list_units_output = Systemctl.list_units(run=run)
        list_units = Systemctl.parse_list_units(list_units_output)

        for unit_name, list_unit in sorted(list_units.items()):
            logger.debug("querying for service: %s", unit_name)
            show_output = Systemctl.show(unit_name, run=run)
            show_properties = Systemctl.parse_show(show_output)

            unit = SystemdUnit.parse(
                list_properties=list_unit.__dict__.copy(),
                show_properties=show_properties,
            )
            units[unit_name] = unit

        encodable_units = {k: v.as_dict() for k, v in units.items()}
        log = output_dir / "systemd-units.json"
        log.write_text(json.dumps(encodable_units, indent=4, sort_keys=True))

        show_output = Systemctl.show(run=run)
        # logging.debug("read systemd show: %r", show_output)
        properties = Systemctl.parse_show(show_output)
        # logging.debug("parsed systemd show: %r", show_output)

        systemd = cls.parse(properties, units=units)
        # logging.debug("systemd: %r", systemd)
        return systemd

    @classmethod
    def parse(cls, properties: dict, *, units=Dict[str, SystemdUnit]) -> "Systemd":
        userspace_timestamp = convert_systemctl_timestamp(
            properties["UserspaceTimestamp"]
        )
        finish_timestamp = convert_systemctl_timestamp(properties["FinishTimestamp"])

        userspace_timestamp_monotonic = convert_systemctl_timestamp_monotonic(
            properties["UserspaceTimestampMonotonic"]
        )
        finish_timestamp_monotonic = convert_systemctl_timestamp_monotonic(
            properties["FinishTimestampMonotonic"]
        )
        system_state = properties["SystemState"]

        assert userspace_timestamp is not None
        assert finish_timestamp is not None
        assert userspace_timestamp_monotonic is not None
        assert finish_timestamp_monotonic is not None

        return cls(
            userspace_timestamp=userspace_timestamp,
            userspace_timestamp_monotonic=userspace_timestamp_monotonic,
            finish_timestamp=finish_timestamp,
            finish_timestamp_monotonic=finish_timestamp_monotonic,
            system_state=system_state,
            units=units,
        )
