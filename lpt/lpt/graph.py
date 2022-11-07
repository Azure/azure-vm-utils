import dataclasses
import logging
from typing import List, Optional, Set, Tuple

from .cloudinit import CloudInitFrame
from .systemd import Systemd, SystemdUnit

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class ServiceGraph:
    def __init__(
        self,
        service_name: str,
        *,
        systemd: Systemd,
        filter_services: List[str],
        filter_conditional_result_no: bool = False,
        filter_inactive: bool = True,
        frames: Optional[List[CloudInitFrame]] = None,
    ) -> None:

        self.service_name = service_name
        self.filter_services = filter_services
        self.filter_conditional_result_no = filter_conditional_result_no
        self.filter_inactive = filter_inactive

        self.systemd = systemd
        self.frames: List[CloudInitFrame] = frames if frames else []

    def get_frame_label(self, frame: CloudInitFrame) -> str:
        """Label cloud-init frame."""
        label = frame.module
        notes = []

        time_to_activate = frame.get_time_to_complete()
        notes.append(f"+{time_to_activate:.03f}s")

        time_of_activation = frame.get_time_of_completion()
        notes.append(f"@{time_of_activation:.03f}s")

        if frame.is_failed():
            notes.append("*FAILED*")

        if notes:
            label += " (" + " ".join(notes) + ")"

        return label

    def get_unit_label(self, unit: SystemdUnit) -> str:
        """Label systemd unit."""
        label = unit.unit
        notes = []

        time_to_activate = unit.get_time_to_activate()
        if time_to_activate:
            notes.append(f"+{time_to_activate:.03f}s")

        time_of_activation = unit.get_time_of_activation()
        notes.append(f"@{time_of_activation:.03f}s")

        if unit.is_failed():
            notes.append("*FAILED*")

        if notes:
            label += " (" + " ".join(notes) + ")"

        return label

    def walk_frame_dependencies(self) -> Set[Tuple[CloudInitFrame, CloudInitFrame]]:
        roots = [f for f in self.frames if f.parent is None]

        deps = set()
        seen = set()

        def _walk_dependencies(frame: CloudInitFrame) -> None:
            # logger.debug("walking: %s", frame)
            if frame in seen:
                # logger.debug("seen: %s", frame)
                return

            seen.add(frame)

            for child in frame.children:
                deps.add((frame, child))
                _walk_dependencies(child)

        for root in roots:
            _walk_dependencies(root)

        return deps

    def walk_unit_dependencies(
        self,
    ) -> Set[Tuple[SystemdUnit, SystemdUnit]]:
        deps = set()
        seen = set()

        def _walk_dependencies(service_name: str) -> None:
            # logger.debug("walking: %s", service_name)
            if service_name in seen:
                # logger.debug("seen: %s", service_name)
                return

            seen.add(service_name)

            service = self.systemd.units.get(service_name)
            if service is None:
                logger.debug("service not found: %r", self.systemd.units)
                return

            for name in service.after:
                dependency = self.systemd.units.get(name)
                if dependency is None:
                    continue

                if not dependency.is_active():
                    continue

                if name in self.filter_services:
                    continue

                if (
                    self.filter_conditional_result_no
                    and not dependency.condition_result
                ):
                    continue

                if (
                    self.filter_inactive
                    and not dependency.active_enter_timestamp_monotonic
                ):
                    continue

                deps.add((service, dependency))
                _walk_dependencies(name)

        _walk_dependencies(self.service_name)
        return deps

    def as_dict(self) -> dict:
        return self.__dict__.copy()

    def generate_digraph(  # pylint: disable=too-many-locals
        self,
    ) -> str:
        lines = [f'digraph "{self.service_name}" {{', "  rankdir=LR;"]
        graphed_units = set()
        unit_dependencies = sorted(
            self.walk_unit_dependencies(), key=lambda x: x[0].unit
        )
        frame_dependencies = self.walk_frame_dependencies()
        # logger.debug("frame dependenices: %r", frame_dependencies)

        edges = []
        for s1, s2 in unit_dependencies:
            graphed_units.add(s1)
            graphed_units.add(s2)
            label_s1 = self.get_unit_label(s1)
            label_s2 = self.get_unit_label(s2)
            color = "red" if s2.is_failed() else "green"

            edge = f'    "{label_s1}"->"{label_s2}" [color="{color}"];'
            edges.append(edge)

        lines += [
            '  subgraph "cluster:systemd" {',
            "    color=lightgrey;",
            "    node [style=filled,color=grey];",
            '    label="systemd"',
            *edges,
            "  }",
        ]

        # Add cloud-init frames.
        for service_name, stage in {
            "cloud-init-local.service": "init-local",
            "cloud-init.service": "init-network",
            "cloud-config.service": "modules-config",
            "cloud-final.service": "modules-final",
        }.items():
            service = self.systemd.units.get(service_name)
            if service is None or service not in graphed_units:
                continue

            service_label = self.get_unit_label(service)

            edges = []
            stage_root_frames = [
                f for f in self.frames if f.stage == stage and f.parent is None
            ]
            for frame in stage_root_frames:
                color = "red" if frame.is_failed() else "green"
                label_f2 = self.get_frame_label(frame)
                edges.append(f'    "{service_label}"->"{label_f2}" [color="{color}"];')

            stage_frames = [
                (f1, f2) for f1, f2 in frame_dependencies if f1.stage == stage
            ]
            for f1, f2 in stage_frames:
                color = "red" if f2.is_failed() else "green"
                label_f1 = self.get_frame_label(f1)
                label_f2 = self.get_frame_label(f2)
                edges.append(f'    "{label_f1}"->"{label_f2}" [color="{color}"];')

            label = f"cloudinit:{stage}"
            lines += [
                f'  subgraph "cluster:{label}" {{',
                "    color=lightblue;",
                "    node [style=filled,color=pink];",
                f'    label="{label}"',
                *edges,
                "  }",
            ]

        start_unit = self.systemd.units[self.service_name]
        start_unit_label = self.get_unit_label(start_unit)
        lines.extend([f'  "{start_unit_label}" [shape=Mdiamond];', "}"])
        digraph = "\n".join(lines)
        return digraph
