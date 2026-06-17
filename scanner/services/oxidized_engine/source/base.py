from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Source(ABC):
    @abstractmethod
    def load(self) -> list[dict[str, Any]]:
        raise NotImplementedError
