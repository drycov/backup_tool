from __future__ import annotations

import re
from typing import Callable

from services.oxidized_engine.model.base import Model
from services.oxidized_engine.node import Node
from services.oxidized_engine.outputs import ModelOutputs


class RouterOSModel(Model):
    """Port of lib/oxidized/model/routeros.rb."""

    def collect(self, node: Node, exec_cmd: Callable[[str], str]) -> ModelOutputs:
        outputs = ModelOutputs()

        resource = exec_cmd("/system resource print")
        resource_lines = [
            line
            for line in resource.splitlines()
            if re.search(
                r"(version|factory-software|total-memory|cpu|cpu-count|"
                r"total-hdd-space|architecture-name|board-name|platform):",
                line,
            )
        ]
        outputs.add(self.comment("\n".join(resource_lines) + "\n"))

        pkg = exec_cmd("/system package update print")
        version_line = next(
            (
                line
                for line in pkg.splitlines()
                if "installed-version:" in line or "current-version:" in line
            ),
            "",
        )
        if version_line:
            match = re.search(r"([0-9])", version_line)
            self._ros_version = int(match.group(1)) if match else None
            outputs.add(self.comment(version_line + "\n"))

        history = exec_cmd("/system history print without-paging")
        outputs.add(self.comment(history))

        export_cmd = self._export_command(node)
        export_raw = exec_cmd(export_cmd)
        export_cfg = self._clean_export(export_raw)
        outputs.add(export_cfg)
        return outputs

    def _export_command(self, node: Node) -> str:
        if node.vars.get("remove_secret"):
            return "/export hide-sensitive"
        if self._ros_version is not None and self._ros_version >= 7:
            return "/export show-sensitive"
        return "/export"

    def _clean_export(self, cfg: str) -> str:
        cfg = re.sub(r"\\\r?\n\s+", "", cfg)
        cfg = cfg.replace("# inactive time\r\n", "")
        cfg = re.sub(r"# received packet from \S+ bad format\r\n", "", cfg)
        cfg = cfg.replace("# poe-out status: short_circuit\r\n", "")
        cfg = cfg.replace(
            "# Firmware upgraded successfully, please reboot for changes to take effect!\r\n",
            "",
        )
        cfg = re.sub(r"# \S+ not ready\r\n", "", cfg)
        cfg = re.sub(
            r"# .+ please restart the device in order to apply the new setting\r\n",
            "",
            cfg,
        )
        lines = cfg.split("\n")
        lines = [
            line
            for line in lines
            if not re.match(r"^#\s\w{3}/\d{2}/\d{4}.*$", line)
            and not re.match(r"^#\s\d{4}-\d{2}-\d{2}.*$", line)
        ]
        return self.clean_lines("\n".join(lines))
