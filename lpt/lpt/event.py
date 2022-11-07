import dataclasses
import datetime
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class EventSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclasses.dataclass(eq=True)
class Event:
    label: str
    timestamp_realtime: datetime.datetime
    timestamp_monotonic: float
    source: str
    severity: EventSeverity

    def estimate_timestamp_monotonic(
        self, reference_monotonic: datetime.datetime
    ) -> None:
        self.timestamp_monotonic = (
            self.timestamp_realtime - reference_monotonic
        ).total_seconds()

    def as_dict(self) -> dict:
        obj = self.__dict__.copy()

        if self.severity == EventSeverity.INFO:
            obj.pop("severity")

        for k, v in obj.items():
            if isinstance(v, datetime.datetime):
                obj[k] = str(v)
            if isinstance(v, Enum):
                obj[k] = str(v.value)

        return obj
