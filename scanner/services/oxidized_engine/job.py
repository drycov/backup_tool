from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from services.oxidized_engine.node import Node
from services.oxidized_engine.outputs import ModelOutputs


@dataclass
class Job:
    node: Node
    config: ModelOutputs | None = None
    status: str = "fail"
    start: datetime | None = None
    end: datetime | None = None

    @property
    def time(self) -> float:
        if not self.start or not self.end:
            return 0.0
        return (self.end - self.start).total_seconds()
