"""Фоновая генерация шаблонов провижионинга через task queue с накоплением лога."""

from __future__ import annotations

import copy
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

_MAX_RUNS = 32
_runs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _purge_old_runs() -> None:
    if len(_runs) <= _MAX_RUNS:
        return
    keys = sorted(_runs.keys(), key=lambda k: _runs[k].get("started_at", ""))
    for key in keys[: len(_runs) - _MAX_RUNS]:
        _runs.pop(key, None)


def _append_run_log(run_id: str, level: str, text: str) -> None:
    with _lock:
        run = _runs.get(run_id)
        if run and run["status"] == "running":
            run["log"].append({"level": level, "text": text})


def run_provision_generate_task(payload: dict[str, Any]) -> dict[str, Any]:
    from core.models import User
    from services.provision_template_builder import generate_templates_from_configs

    run_id = str(payload.get("run_id") or "")
    if not run_id:
        raise ValueError("run_id обязателен")

    user = None
    user_id = payload.get("user_id")
    if user_id:
        user = User.objects.filter(pk=int(user_id)).first()

    def _log(level: str, text: str) -> None:
        _append_run_log(run_id, level, text)

    try:
        result = generate_templates_from_configs(
            group=str(payload.get("group") or ""),
            site=str(payload.get("site") or ""),
            model=str(payload.get("model") or ""),
            user=user,
            complexity_threshold=float(payload.get("threshold", 0.85)),
            min_devices=int(payload.get("min_devices", 2)),
            upsert=bool(payload.get("upsert", True)),
            log_cb=_log,
        )
        _log(
            "info",
            f"Итог генерации: создано {len(result['created'])}, "
            f"обновлено {len(result['updated'])}, пропущено {len(result['skipped'])}",
        )
        with _lock:
            run = _runs.get(run_id)
            if run:
                run["status"] = "completed"
                run["result"] = result
                run["finished_at"] = datetime.now(timezone.utc).isoformat()
        return result
    except Exception as exc:
        _log("error", f"Ошибка генерации: {exc}")
        with _lock:
            run = _runs.get(run_id)
            if run:
                run["status"] = "failed"
                run["error"] = str(exc)[:500]
                run["finished_at"] = datetime.now(timezone.utc).isoformat()
        raise


def start_provision_generate(
    *,
    group: str = "",
    site: str = "",
    model: str = "",
    user=None,
    complexity_threshold: float = 0.85,
    min_devices: int = 2,
    upsert: bool = True,
) -> str:
    from core.models import BackgroundTask
    from services.task_queue import enqueue

    run_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc).isoformat()
    filters = {
        "group": group,
        "site": site,
        "model": model,
        "threshold": complexity_threshold,
        "min_devices": min_devices,
        "upsert": upsert,
    }
    with _lock:
        _runs[run_id] = {
            "id": run_id,
            "status": "running",
            "log": [{"level": "info", "text": "Генерация шаблонов поставлена в очередь…"}],
            "result": None,
            "error": "",
            "filters": filters,
            "started_at": now,
            "finished_at": None,
        }
        _purge_old_runs()

    task = enqueue(
        BackgroundTask.TASK_PROVISION_GENERATE,
        payload={
            "run_id": run_id,
            "group": group,
            "site": site,
            "model": model,
            "threshold": complexity_threshold,
            "min_devices": min_devices,
            "upsert": upsert,
            "user_id": user.id if user else None,
        },
        dedupe=False,
    )
    if not task:
        with _lock:
            run = _runs.get(run_id)
            if run:
                run["status"] = "failed"
                run["error"] = "Не удалось поставить задачу в очередь"
                run["finished_at"] = datetime.now(timezone.utc).isoformat()
        raise RuntimeError("Не удалось поставить задачу в очередь")

    _append_run_log(run_id, "info", "Генерация шаблонов запущена…")
    return run_id


def get_provision_generate_run(run_id: str) -> dict[str, Any] | None:
    with _lock:
        run = _runs.get(run_id)
        if not run:
            return None
        return copy.deepcopy(run)
