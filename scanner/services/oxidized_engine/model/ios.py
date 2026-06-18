from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable

from services.oxidized_engine.input.shell import shell_exec
from services.oxidized_engine.model.base import Model
from services.oxidized_engine.outputs import ModelOutputs

if TYPE_CHECKING:
    from services.oxidized_engine.node import Node


class IOSModel(Model):
    """Cisco IOS / IOS-XE — show running-config (shell + enable)."""

    def collect(self, node: Node, exec_cmd: Callable[[str], str]) -> ModelOutputs:
        outputs = ModelOutputs()
        enable = str(node.vars.get("enable") or node.vars.get("enable_password") or "")
        if not enable:
            enable = node.auth.get("password") or ""

        init: list[str] = []
        if enable:
            init = ["terminal length 0", f"enable\n{enable}", "terminal length 0"]
        else:
            init = ["terminal length 0"]

        try:
            raw = shell_exec(
                node,
                init_commands=init,
                command="show running-config",
                prompt_pattern=r"[>#]\s*$",
                timeout=float(node.timeout),
            )
        except ConnectionError:
            raw = exec_cmd("show running-config")

        cfg = self._clean_config(raw)
        outputs.add(cfg)
        return outputs

    def _clean_config(self, text: str) -> str:
        lines = []
        for line in text.splitlines():
            if line.strip().startswith("Building configuration"):
                continue
            if re.match(r"^Current configuration\s*:", line):
                continue
            if line.strip() in (">", "#"):
                continue
            if "show running-config" in line.lower():
                continue
            lines.append(line.rstrip())
        return self.clean_lines("\n".join(lines))
