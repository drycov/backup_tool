from __future__ import annotations

from typing import Any

from services.inventory import devices_for_oxidized_source
from services.oxidized_engine.config import OxidizedConfig
from services.oxidized_engine.source.base import Source


class HttpSource(Source):
    """HTTP source — reads inventory via devices_for_oxidized_source()."""

    def __init__(self, config: OxidizedConfig) -> None:
        self.config = config

    def load(self) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        for item in devices_for_oxidized_source():
            nodes.append(
                {
                    "name": item["hostname"],
                    "ip": item["ip"],
                    "model": item.get("os") or self.config.default_model,
                    "group": item.get("group") or "default",
                    "vars": {"ssh_port": item.get("ssh_port", self.config.default_ssh_port)},
                }
            )
        return nodes
