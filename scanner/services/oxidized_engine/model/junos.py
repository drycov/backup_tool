from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable

from services.oxidized_engine.model.base import Model
from services.oxidized_engine.outputs import ModelOutputs

if TYPE_CHECKING:
    from services.oxidized_engine.node import Node


class JunOSModel(Model):
    """Juniper JunOS — show configuration | display set | no-more."""

    def collect(self, node: Node, exec_cmd: Callable[[str], str]) -> ModelOutputs:
        outputs = ModelOutputs()
        commands = [
            "show configuration | display set | no-more",
            "show configuration | no-more",
        ]
        raw = ""
        for cmd in commands:
            try:
                raw = exec_cmd(cmd)
                if raw.strip() and "error:" not in raw.lower()[:200]:
                    break
            except Exception:
                continue
        cfg = self._clean_config(raw)
        outputs.add(cfg)
        return outputs

    def _clean_config(self, text: str) -> str:
        lines = []
        for line in text.splitlines():
            if line.strip().startswith("##"):
                continue
            if re.match(r"^\{master\}", line.strip()):
                line = line.replace("{master}", "", 1).strip()
            lines.append(line.rstrip())
        return self.clean_lines("\n".join(lines))
