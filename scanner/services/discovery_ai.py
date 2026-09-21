"""AI enrichment для discovery-кандидатов через локальный Ollama/Qwen3.

AI только предлагает классификацию. Регистрация устройства и его сетевые параметры
остаются детерминированными результатами discovery.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return os.getenv("AI_DISCOVERY_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def _config() -> tuple[str, str]:
    return (
        os.getenv("AI_OLLAMA_URL", "http://ollama:11434").rstrip("/"),
        os.getenv("AI_MODEL", "qwen3:4b"),
    )


def _analyze(payload: dict[str, Any]) -> dict[str, Any]:
    if not enabled():
        return {"enabled": False, "status": "disabled"}

    base_url, model = _config()
    prompt = (
        "Ты помощник NOC для классификации сетевого устройства. "
        "Используй только факты из JSON. Ничего не выдумывай. "
        "Верни только JSON с полями: device_type, vendor, model_candidate, "
        "os_candidate, confidence, recommended_profile, risk, reason. "
        "confidence должен быть числом от 0 до 1. "
        "Если данных недостаточно, используй null или пустую строку и confidence 0."
        "\n\nДанные:\n" + json.dumps(payload, ensure_ascii=False, default=str)
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
                        {"role": "system", "content": "Классифицируй только по предоставленным сетевым данным."},
                        {"role": "user", "content": prompt},
                    ],
                    "options": {"temperature": 0.0},
                },
            )
            response.raise_for_status()
            data = response.json()
        parsed = json.loads(((data.get("message") or {}).get("content") or "{}").strip())
        confidence = parsed.get("confidence", 0)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.0
        return {
            "enabled": True,
            "status": "completed",
            "provider": "ollama",
            "model": model,
            "confidence": confidence,
            "result": parsed,
        }
    except Exception as exc:
        logger.warning("discovery_ai | failed | model=%s | %s", model, exc)
        return {
            "enabled": True,
            "status": "failed",
            "provider": "ollama",
            "model": model,
            "error": str(exc)[:500],
        }


def enrich_discovered_device(device_name: str) -> dict[str, Any]:
    from core.models import Device as DeviceModel

    row = DeviceModel.objects.filter(name=device_name).first()
    if not row:
        return {"status": "not_found", "device_name": device_name}

    payload = {
        "name": row.name,
        "ip": row.ip,
        "model": row.model,
        "group": row.group,
        "ports": row.ports or [],
        "site": row.site or "",
        "role": row.role or "",
        "tags": row.tags or [],
    }
    result = _analyze(payload)
    row.ai_enrichment = result
    row.save(update_fields=["ai_enrichment"])
    return {"status": result.get("status"), "device_name": row.name, "analysis": result}
