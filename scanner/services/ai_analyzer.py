"""Локальный AI-анализ scan/discovery через Ollama + open-weight модель."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def ai_enabled() -> bool:
    return os.getenv("AI_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def ai_config() -> tuple[str, str]:
    return (
        os.getenv("AI_OLLAMA_URL", "http://ollama:11434").rstrip("/"),
        os.getenv("AI_MODEL", "qwen3:4b"),
    )


def analyze_scan(payload: dict[str, Any]) -> dict[str, Any]:
    if not ai_enabled():
        return {"enabled": False, "status": "disabled"}

    base_url, model = ai_config()
    prompt = (
        "Ты сетевой NOC-анализатор. Проанализируй результаты сетевого scan/discovery. "
        "Не придумывай факты. Верни только JSON с ключами summary, risks, recommendations. "
        "risks и recommendations — массивы объектов с severity, title, evidence. "
        "Если данных недостаточно, укажи это явно.\n\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )
    try:
        with httpx.Client(timeout=float(os.getenv("AI_TIMEOUT_SEC", "90"))) as client:
            response = client.post(
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "format": "json",
                    "messages": [
                        {
                            "role": "system",
                            "content": "Ты помогаешь NOC. Анализируй только предоставленные данные.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "options": {"temperature": 0.1},
                },
            )
            response.raise_for_status()
            data = response.json()
        raw = ((data.get("message") or {}).get("content") or "").strip()
        parsed = json.loads(raw)
        return {
            "enabled": True,
            "status": "completed",
            "provider": "ollama",
            "model": model,
            "result": parsed,
        }
    except Exception as exc:
        logger.warning("ai_analyzer | failed | model=%s | %s", model, exc)
        return {
            "enabled": True,
            "status": "failed",
            "provider": "ollama",
            "model": model,
            "error": str(exc)[:500],
        }


def analyze_scan_run(run_id: int) -> dict[str, Any]:
    from core.models import ScanRun

    run = ScanRun.objects.filter(pk=run_id).first()
    if not run:
        return {"status": "not_found"}

    payload = {
        "scan_id": run.id,
        "discover": run.discover,
        "status": run.status,
        "total": run.total,
        "online": run.online,
        "partial": run.partial,
        "offline": run.offline,
        "devices": run.results_json or [],
    }
    result = analyze_scan(payload)
    run.ai_analysis = result
    run.save(update_fields=["ai_analysis"])
    return result
