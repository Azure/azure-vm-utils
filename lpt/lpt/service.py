import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True, eq=True)
class Service:
    name: str
    time_to_activate: float
    timestamp_monotonic_start: float
    timestamp_monotonic_finish: float
    failed: bool

    def get_label(self) -> str:
        """Label service using times relative to start of systemd."""
        label = self.name
        notes = []

        if self.time_to_activate:
            notes.append(f"+{self.time_to_activate:.03f}s")

        notes.append(f"@{self.timestamp_monotonic_finish:.03f}s")
        if self.failed:
            notes.append("*FAILED*")

        if notes:
            label += " (" + " ".join(notes) + ")"

        return label

    def as_dict(self) -> dict:
        return self.__dict__.copy()
