from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

from services.oxidized_engine.outputs import ModelOutputs

if TYPE_CHECKING:
    from services.oxidized_engine.node import Node


class Model(ABC):
    comment_prefix = "# "

    def __init__(self) -> None:
        self._ros_version: int | None = None

    @abstractmethod
    def collect(self, node: Node, exec_cmd: Callable[[str], str]) -> ModelOutputs:
        raise NotImplementedError

    def comment(self, text: str) -> str:
        lines = []
        for line in text.splitlines():
            stripped = line.rstrip()
            if not stripped:
                lines.append("")
                continue
            if stripped.startswith(self.comment_prefix):
                lines.append(stripped)
            else:
                lines.append(f"{self.comment_prefix}{stripped}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def strip_ansi(text: str) -> str:
        return re.sub(r"\x1B\[([0-9]{1,3}(;[0-9]{1,3})*)?[mK]", "", text)

    @staticmethod
    def clean_lines(text: str) -> str:
        return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
