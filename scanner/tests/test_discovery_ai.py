import json

import pytest

from services import discovery_ai


@pytest.mark.django_db
def test_enrich_discovered_device_persists(monkeypatch):
    from core.models import Device

    row = Device.objects.create(
        name="discovered-10-0-0-10",
        ip="10.0.0.10",
        model="routeros",
        group="discovered",
        ports=[44333],
    )

    monkeypatch.setenv("AI_DISCOVERY_ENABLED", "true")
    monkeypatch.setattr(
        discovery_ai,
        "_analyze",
        lambda payload: {
            "enabled": True,
            "status": "completed",
            "provider": "ollama",
            "model": "qwen3:4b",
            "confidence": 0.93,
            "result": {
                "device_type": "router",
                "vendor": "MikroTik",
                "model_candidate": "RouterOS",
                "os_candidate": "RouterOS",
                "confidence": 0.93,
                "recommended_profile": "routeros",
                "risk": "low",
                "reason": "open management port",
            },
        },
    )

    result = discovery_ai.enrich_discovered_device(row.name)
    row.refresh_from_db()

    assert result["status"] == "completed"
    assert row.ai_enrichment["result"]["vendor"] == "MikroTik"
    assert row.ai_enrichment["confidence"] == 0.93
