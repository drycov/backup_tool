"""Фоновый запуск анализа кластеров провижионинга с накоплением лога (in-process)."""

from __future__ import annotations

import copy
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from services.provision_template_builder import analyze_clusters, clusters_to_api_payload

_MAX_RUNS = 32
_runs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _purge_old_runs() -> None:
    if len(_runs) <= _MAX_RUNS:
        return
    keys = sorted(_runs.keys(), key=lambda k: _runs[k].get("started_at", ""))
    for key in keys[: len(_runs) - _MAX_RUNS]:
        _runs.pop(key, None)


def start_provision_analysis(
    *,
    group: str = "",
    site: str = "",
    model: str = "",
    user=None,
    complexity_threshold: float = 0.85,
    min_devices: int = 2,
) -> str:
    run_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc).isoformat()
    filters = {
        "group": group,
        "site": site,
        "model": model,
        "threshold": complexity_threshold,
        "min_devices": min_devices,
    }
    with _lock:
        _runs[run_id] = {
            "id": run_id,
            "status": "running",
            "log": [{"level": "info", "text": "Анализ запущен…"}],
            "result": None,
            "error": "",
            "filters": filters,
            "started_at": now,
            "finished_at": None,
        }
        _purge_old_runs()

    def _log(level: str, text: str) -> None:
        with _lock:
            run = _runs.get(run_id)
            if run and run["status"] == "running":
                run["log"].append({"level": level, "text": text})

    from services.provision_template_builder import _resolve_analysis_devices

    devices = _resolve_analysis_devices(
        group=group,
        site=site,
        model=model,
        user=user,
    )

    def _worker() -> None:
        try:
            clusters = analyze_clusters(
                group=group,
                site=site,
                model=model,
                user=user,
                devices=devices,
                complexity_threshold=complexity_threshold,
                min_devices=min_devices,
                log_cb=_log,
            )
            payload = clusters_to_api_payload(clusters, filters=filters)
            ready = sum(1 for c in clusters if c.template_body and not c.skipped_reason)
            skipped = sum(1 for c in clusters if c.skipped_reason)
            complex_n = len(payload.get("complex_devices") or [])
            _log(
                "info",
                f"Итог: кластеров {len(clusters)}, готовых к шаблону {ready}, "
                f"пропущено {skipped}, сложных устройств {complex_n}",
            )
            with _lock:
                run = _runs.get(run_id)
                if run:
                    run["status"] = "completed"
                    run["result"] = payload
                    run["finished_at"] = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            _log("error", f"Ошибка анализа: {exc}")
            with _lock:
                run = _runs.get(run_id)
                if run:
                    run["status"] = "failed"
                    run["error"] = str(exc)[:500]
                    run["finished_at"] = datetime.now(timezone.utc).isoformat()

    threading.Thread(
        target=_worker,
        daemon=True,
        name=f"prov-analysis-{run_id}",
    ).start()
    return run_id


def get_provision_analysis_run(run_id: str) -> dict[str, Any] | None:
    with _lock:
        run = _runs.get(run_id)
        if not run:
            return None
        return copy.deepcopy(run)
