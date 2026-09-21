from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from services.compliance import compute_compliance_summary


def _device(name, *, critical=False, group="default"):
    return SimpleNamespace(
        name=name,
        ip="10.0.0.1",
        model="routeros",
        group=group,
        enabled=True,
        site="dc1",
        role="core",
        critical=critical,
        tags=["prod"],
    )


def _patch_compliance(monkeypatch, devices, nodes):
    cfg = SimpleNamespace(stale_days_threshold=30)
    monkeypatch.setattr("services.compliance.get_config", lambda: cfg)
    monkeypatch.setattr(
        "services.compliance.get_oxidized_settings",
        lambda: {"interval": 3600},
    )
    monkeypatch.setattr(
        "services.compliance.load_inventory",
        lambda: SimpleNamespace(devices=devices),
    )
    monkeypatch.setattr("services.compliance.get_nodes", lambda: (nodes, None))
    monkeypatch.setattr(
        "services.compliance.get_latest_scan_reachability",
        lambda: {d.name: "online" for d in devices},
    )
    monkeypatch.setattr("services.compliance.effective_interval", lambda group, global_interval: global_interval)
    monkeypatch.setattr("services.compliance.effective_compliance_sla_hours", lambda group: 24)


def test_compliance_exposes_backup_age_and_sla(monkeypatch):
    now = datetime.now(timezone.utc)
    devices = [_device("router-1", critical=True)]
    nodes = [{
        "name": "router-1",
        "status": "success",
        "last": {"status": "success", "end": (now - timedelta(hours=1)).isoformat()},
        "mtime": 0,
    }]
    _patch_compliance(monkeypatch, devices, nodes)

    summary = compute_compliance_summary()

    item = summary["nodes"][0]
    assert item["backup_age_hours"] is not None
    assert item["compliance_sla_hours"] == 24
    assert item["sla_breached"] is False
    assert summary["critical_noncompliant"] == 0
    assert summary["sla_breached"] == 0


def test_compliance_sla_filter_returns_only_breached(monkeypatch):
    now = datetime.now(timezone.utc)
    devices = [_device("router-1"), _device("router-2")]
    nodes = [
        {
            "name": "router-1",
            "status": "success",
            "last": {"status": "success", "end": (now - timedelta(hours=2)).isoformat()},
            "mtime": 0,
        },
        {
            "name": "router-2",
            "status": "success",
            "last": {"status": "success", "end": (now - timedelta(hours=30)).isoformat()},
            "mtime": 0,
        },
    ]
    _patch_compliance(monkeypatch, devices, nodes)

    summary = compute_compliance_summary(sla="breached")

    assert [n["name"] for n in summary["nodes"]] == ["router-2"]
    assert summary["sla_breached"] == 1
