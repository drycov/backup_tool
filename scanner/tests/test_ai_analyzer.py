import json

import pytest
from datetime import datetime, timezone


@pytest.mark.django_db
def test_analyze_scan_run_persists_ollama_result(monkeypatch):
    from core.models import ScanRun
    from services import ai_analyzer

    run = ScanRun.objects.create(
        status="completed",
        total=2,
        online=1,
        offline=1,
        partial=0,
        scanned_at=datetime(2026, 9, 21, 10, tzinfo=timezone.utc),
        results_json=[
            {"name": "r1", "ip": "10.0.0.1", "status": "online"},
            {"name": "r2", "ip": "10.0.0.2", "status": "offline"},
        ],
    )

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "summary": "1 device offline",
                            "risks": [],
                            "recommendations": [],
                        }
                    )
                }
            }

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("AI_MODEL", "qwen3:4b")
    monkeypatch.setattr(ai_analyzer.httpx, "Client", Client)

    result = ai_analyzer.analyze_scan_run(run.id)

    assert result["status"] == "completed"
    assert result["model"] == "qwen3:4b"
    assert result["result"]["summary"] == "1 device offline"
    assert ScanRun.objects.get(pk=run.id).ai_analysis["status"] == "completed"
