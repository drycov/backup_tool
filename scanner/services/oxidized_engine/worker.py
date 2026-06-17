from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from services.oxidized_engine.config import OxidizedConfig
from services.oxidized_engine.hooks import HookRunner
from services.oxidized_engine.job import Job
from services.oxidized_engine.node import JobRecord
from services.oxidized_engine.nodes import Nodes
from services.oxidized_engine.output.git import GitOutput

logger = logging.getLogger(__name__)


class Worker:
    """Background worker — port of Oxidized::Worker scheduling loop."""

    def __init__(self, nodes: Nodes, config: OxidizedConfig) -> None:
        self.nodes = nodes
        self.config = config
        self.output = GitOutput(config)
        self.hooks = HookRunner(config)
        self.executor = ThreadPoolExecutor(max_workers=config.threads)
        self._jobs_done = 0
        self._nodes_count = 0

    def reload(self) -> None:
        self.nodes.load()
        self._nodes_count = len(self.nodes)

    def work(self) -> None:
        if not self._nodes_count:
            self.reload()
        now = time.time()
        for node in list(self.nodes):
            if node.running:
                continue
            if not (node.nexted or node.due(now, self.config.interval)):
                continue
            node.nexted = False
            node.running = True
            self.executor.submit(self._process, node)

    def _process(self, node) -> None:
        job = Job(node=node, start=datetime.now(timezone.utc))
        status, outputs = node.run()
        job.end = datetime.now(timezone.utc)
        job.status = status
        job.config = outputs
        node.last = JobRecord(
            start=job.start,
            end=job.end,
            status=job.status,
            time=job.time,
        )
        node.stats.add(job.status)
        node.running = False

        if job.status == "success" and outputs:
            self._process_success(node, job, outputs)
        else:
            self._process_failure(node, job)

    def _process_success(self, node, job, outputs) -> None:
        msg = f"update {node.group}/{node.name}"
        if node.msg:
            msg += f" with message '{node.msg}'"
        stored = self.output.store(
            node.name,
            outputs,
            msg=msg,
            group=node.group,
            user=node.user or self.config.git.user,
            email=node.email or self.config.git.email,
        )
        if stored:
            node.modified()
            self.hooks.post_store(node, job, self.output.last_commit)
            logger.info(
                "oxidized | Configuration updated for %s/%s",
                node.group,
                node.name,
            )
        else:
            logger.info(
                "oxidized | no change for %s/%s",
                node.group,
                node.name,
            )
        node.reset()
        self._jobs_done += 1

    def _process_failure(self, node, job) -> None:
        detail = f": {node.err_reason}" if node.err_reason else ""
        if node.retry < self.config.retries:
            node.retry += 1
            logger.warning(
                "oxidized | %s/%s status %s, retry %d%s",
                node.group,
                node.name,
                job.status,
                node.retry,
                detail,
            )
            self.nodes.next(node.name)
        else:
            logger.warning(
                "oxidized | %s/%s status %s, retries exhausted%s",
                node.group,
                node.name,
                job.status,
                detail,
            )
            node.retry = 0
            self.hooks.node_fail(node, job)
            self._jobs_done += 1
        node.reset()

    def fetch_node(self, name: str) -> tuple[str, str | None]:
        self.reload()
        node = self.nodes.find(name)
        node.nexted = True
        node.running = True
        self._process(node)
        node = self.nodes.find(name)
        if node.last and node.last.status == "success":
            return "success", self.output.fetch(node)
        return node.last.status if node.last else "fail", None
