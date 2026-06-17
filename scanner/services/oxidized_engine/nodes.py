from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

from services.oxidized_engine.config import OxidizedConfig
from services.oxidized_engine.exceptions import NodeNotFound
from services.oxidized_engine.node import Node
from services.oxidized_engine.source.http import HttpSource

logger = logging.getLogger(__name__)


def _node_sort_key(node: Node) -> float:
    """Comparable sort key — always float (mtime or last job end)."""
    if node.last and node.last.end:
        end = node.last.end
        if isinstance(end, datetime):
            return end.timestamp()
        if isinstance(end, (int, float)):
            return float(end)
    return float(node.stats.mtime or 0)


class Nodes(list[Node]):
    """Thread-safe node list — mirrors Oxidized::Nodes."""

    def __init__(self, config: OxidizedConfig) -> None:
        super().__init__()
        self.config = config
        self._lock = threading.RLock()
        self._source = HttpSource(config)

    def load(self, node_want: str | None = None) -> None:
        with self._lock:
            raw_nodes = self._source.load()
            built: list[Node] = []
            for raw in raw_nodes:
                if node_want and not self._node_want(node_want, raw):
                    continue
                try:
                    built.append(Node(raw, self.config))
                except Exception as exc:
                    logger.error(
                        "oxidized | load | node %s: %s",
                        raw.get("name"),
                        exc,
                    )
            if not self:
                self.extend(built)
            else:
                self._update_nodes(built)

    def _node_want(self, node_want: str, node: dict[str, Any]) -> bool:
        if node_want in (node.get("name"), node.get("ip")):
            return True
        return node_want in str(node.get("name", ""))

    def _update_nodes(self, new_nodes: list[Node]) -> None:
        old = {node.name: node for node in self}
        self.clear()
        self.extend(new_nodes)
        for node in self:
            prev = old.get(node.name)
            if prev:
                node.stats = prev.stats
                node.last = prev.last
        self.sort(key=_node_sort_key)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [node.serialize() for node in self]

    def find(self, name: str) -> Node:
        with self._lock:
            for node in self:
                if node.name == name:
                    return node
        raise NodeNotFound(f"unable to find '{name}'")

    def next(self, name: str, opt: dict[str, Any] | None = None) -> None:
        with self._lock:
            node = self.find(name)
            node.user = (opt or {}).get("user")
            node.email = (opt or {}).get("email")
            node.msg = (opt or {}).get("msg")
            node.last = None
            node.nexted = True
            self.remove(node)
            self.insert(0, node)

    def get(self) -> Node | None:
        with self._lock:
            if not self:
                return None
            node = self.pop(0)
            self.append(node)
            return node
