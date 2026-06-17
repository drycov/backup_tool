from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConfigOutput:
    name: str | None
    text: str


class ModelOutputs:
    """Aggregated configuration sections (oxidized Model::Outputs)."""

    def __init__(self) -> None:
        self._sections: list[ConfigOutput] = []

    def add(self, text: str, name: str | None = None) -> None:
        if text:
            self._sections.append(ConfigOutput(name=name, text=text))

    def merge(self, other: ModelOutputs) -> None:
        self._sections.extend(other._sections)

    def to_cfg(self) -> str:
        return "".join(section.text for section in self._sections)

    @property
    def sections(self) -> list[ConfigOutput]:
        return list(self._sections)
