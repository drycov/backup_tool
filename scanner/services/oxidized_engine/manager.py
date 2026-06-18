from __future__ import annotations

import logging
import threading
import time
from typing import Any

from services.oxidized_engine.config import OxidizedConfig
from services.oxidized_engine.exceptions import NodeNotFound
from services.oxidized_engine.nodes import Nodes
from services.oxidized_engine.output.git import GitOutput
from services.oxidized_engine.worker import Worker

logger = logging.getLogger(__name__)

_manager: OxidizedManager | None = None
_lock = threading.Lock()


class OxidizedManager:
    """Singleton manager — loads nodes and runs worker loop."""

    def __init__(self, config: OxidizedConfig | None = None) -> None:
        self.config = config or OxidizedConfig.from_django()
        self.nodes = Nodes(self.config)
        self.worker = Worker(self.nodes, self.config)
        self.output = GitOutput(self.config)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._setup_file_logging()
        logger.info(
            "oxidized | engine | start interval=%ss threads=%d repo=%s",
            self.config.interval,
            self.config.threads,
            self.config.git.repo,
        )
        self.worker.reload()
        self._thread = threading.Thread(target=self._loop, name="oxidized-worker", daemon=True)
        self._thread.start()

    def _setup_file_logging(self) -> None:
        from services.oxidized_logging import configure_oxidized_file_logging

        configure_oxidized_file_logging()

    def stop(self) -> None:
        self._stop.set()

    def reload_config(self) -> None:
        self.config = OxidizedConfig.from_django()
        self.nodes.config = self.config
        self.worker.config = self.config
        self.worker.output = GitOutput(self.config)
        self.worker.hooks.config = self.config
        self.output = GitOutput(self.config)
        self.worker.reload()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.worker.work()
            except Exception:
                logger.exception("oxidized | worker loop error")
            time.sleep(1)

    def list_nodes(self) -> list[dict[str, Any]]:
        self.worker.reload()
        result = []
        for item in self.nodes.list():
            last = item.get("last") or {}
            status = last.get("status") if last else "never"
            result.append(
                {
                    "name": item["name"],
                    "full_name": item.get("full_name") or item["name"],
                    "ip": item["ip"],
                    "group": item.get("group"),
                    "model": item.get("model"),
                    "status": status,
                    "mtime": item.get("mtime"),
                    "last": last,
                }
            )
        return result

    def show_node(self, name: str) -> str | None:
        try:
            node = self.nodes.find(name)
        except NodeNotFound:
            self.worker.reload()
            try:
                node = self.nodes.find(name)
            except NodeNotFound:
                return None
        text = self.output.fetch(node)
        if text == "node not found":
            return None
        return text

    def fetch_node(self, name: str) -> dict[str, Any]:
        status, config = self.worker.fetch_node(name)
        return {"status": status, "config": config}

    def backup_all(self, only_names: set[str] | None = None) -> dict[str, int]:
        self.worker.reload()
        count = 0
        for node in list(self.nodes):
            if only_names is not None and node.name not in only_names:
                continue
            self.nodes.next(node.name)
            count += 1
        return {"queued": count}

    def node_versions(self, name: str) -> dict[str, Any]:
        node = self.nodes.find(name)
        group = node.group or ""
        node_full = f"{group}/{name}" if group and group not in ("", "default") else name
        return {
            "node": name,
            "group": group,
            "node_full": node_full,
            "versions": self.output.version(node),
        }

    def get_version(self, name: str, oid: str) -> str:
        return self.output.get_version(self.nodes.find(name), oid)

    def get_diff(self, name: str, oid1: str, oid2: str | None = None) -> dict[str, Any]:
        return self.output.get_diff(self.nodes.find(name), oid1, oid2)

    def health(self) -> dict[str, Any]:
        from services.oxidized_engine.collector.ruby_bridge import ruby_available
        from services.oxidized_logging import engine_title, is_python_engine, oxidized_log_path

        engine = "python" if is_python_engine() else "external"
        try:
            nodes = self.list_nodes()
            payload: dict[str, Any] = {
                "reachable": True,
                "error": None,
                "nodes_count": len(nodes),
                "engine": engine,
                "engine_title": engine_title(),
                "log_path": str(oxidized_log_path()),
            }
            if is_python_engine():
                payload["models"] = (
                    "oxidized-gem" if ruby_available() else "python-fallback"
                )
            return payload
        except Exception as exc:
            return {
                "reachable": False,
                "error": str(exc),
                "nodes_count": 0,
                "engine": engine,
                "engine_title": engine_title(),
                "log_path": str(oxidized_log_path()),
            }


def get_manager() -> OxidizedManager:
    global _manager
    with _lock:
        if _manager is None:
            _manager = OxidizedManager()
        return _manager


def start_engine() -> None:
    get_manager().start()


def reload_engine() -> None:
    get_manager().reload_config()
