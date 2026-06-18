"""Тесты аудита безопасности конфигураций."""

from __future__ import annotations

import pytest

from services.config_security_audit import analyze_config_text, run_config_audit
from services.config_security_rules import rules_for_model


ROUTEROS_SAMPLE = """
/ip service
add name=telnet disabled=no
add name=ftp disabled=no
add name=www disabled=no
add name=api disabled=no

/user
add name=admin password=secret123
"""

IOS_SAMPLE = """
ip http server
snmp-server community public RO
line vty 0 4
 transport input telnet
"""


def test_analyze_routeros_finds_insecure_services():
    findings = analyze_config_text(ROUTEROS_SAMPLE, "routeros")
    rule_ids = {f["rule_id"] for f in findings}
    assert "ros-telnet-enabled" in rule_ids
    assert "ros-ftp-enabled" in rule_ids
    assert "ros-www-http" in rule_ids
    assert "ros-password-in-config" in rule_ids


def test_analyze_ios_finds_snmp_and_telnet():
    findings = analyze_config_text(IOS_SAMPLE, "ios")
    rule_ids = {f["rule_id"] for f in findings}
    assert "ios-snmp-public" in rule_ids
    assert "ios-http-server" in rule_ids
    assert "ios-telnet" in rule_ids


def test_rules_for_model_routeros():
    rules = rules_for_model("routeros")
    assert any(r.id.startswith("ros-") for r in rules)
    assert not any(r.id.startswith("junos-") for r in rules)


def test_clean_config_no_findings():
    clean = """
/ip service
add name=telnet disabled=yes
add name=ftp disabled=yes
/ip firewall filter
add chain=input action=drop
"""
    findings = analyze_config_text(clean, "routeros")
    assert not findings


@pytest.mark.django_db
def test_run_config_audit_persists(monkeypatch):
    from core.models import ConfigAuditRun, ConfigFinding
    from services.schemas import Device, Inventory

    device = Device(
        name="r1",
        ip="10.0.0.1",
        model="routeros",
        group="default",
        enabled=True,
    )
    monkeypatch.setattr(
        "services.config_security_audit.load_inventory",
        lambda: Inventory(devices=[device], networks=[], credential_profiles=[]),
    )
    monkeypatch.setattr(
        "services.config_security_audit.get_node_config",
        lambda name: (ROUTEROS_SAMPLE, None),
    )

    result = run_config_audit(triggered_by="test")
    assert result["status"] == "completed"
    assert result["devices_scanned"] == 1
    assert result["findings_count"] > 0
    assert ConfigAuditRun.objects.filter(pk=result["id"]).exists()
    assert ConfigFinding.objects.filter(run_id=result["id"]).exists()


@pytest.mark.django_db
def test_compute_security_summary_scoped_once(monkeypatch):
    from core.models import ConfigAuditRun, ConfigFinding
    from services.config_security_audit import compute_security_summary
    from services.schemas import Device, Inventory

    from datetime import datetime, timezone

    ConfigAuditRun.objects.all().delete()

    run = ConfigAuditRun.objects.create(
        status=ConfigAuditRun.STATUS_COMPLETED,
        triggered_by="test",
        devices_total=2,
        devices_scanned=2,
        findings_count=3,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    for idx, name in enumerate(("r1", "r1", "r2")):
        ConfigFinding.objects.create(
            run=run,
            device_name=name,
            device_ip="10.0.0.1",
            device_model="routeros",
            rule_id=f"rule-{idx}",
            category="services",
            severity="high",
            title="test",
        )

    inventory_calls = 0

    def _load_inventory():
        nonlocal inventory_calls
        inventory_calls += 1
        return Inventory(
            devices=[
                Device(name="r1", ip="10.0.0.1", model="routeros", group="default", enabled=True),
                Device(name="r2", ip="10.0.0.2", model="routeros", group="default", enabled=True),
            ]
        )

    monkeypatch.setattr("services.config_security_audit.load_inventory", _load_inventory)

    class _User:
        role = "viewer"
        allowed_groups: list[str] = []
        allowed_sites: list[str] = []

    summary = compute_security_summary(user=_User())
    assert summary["findings_total"] == 3
    assert summary["counts"]["high"] == 3
    assert summary["by_category"]["services"] == 3
    assert summary["findings"] == []
    assert inventory_calls == 1


@pytest.mark.django_db
def test_list_security_findings_paginated(monkeypatch):
    from datetime import datetime, timezone

    from core.models import ConfigAuditRun, ConfigFinding
    from services.config_security_audit import list_security_findings
    from services.schemas import Device, Inventory

    run = ConfigAuditRun.objects.create(
        status=ConfigAuditRun.STATUS_COMPLETED,
        triggered_by="test",
        devices_total=1,
        devices_scanned=1,
        findings_count=3,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    for idx in range(3):
        ConfigFinding.objects.create(
            run=run,
            device_name="r1",
            device_ip="10.0.0.1",
            device_model="routeros",
            rule_id=f"rule-{idx}",
            category="services",
            severity="high",
            title=f"finding-{idx}",
        )

    monkeypatch.setattr(
        "services.config_security_audit.load_inventory",
        lambda: Inventory(
            devices=[
                Device(name="r1", ip="10.0.0.1", model="routeros", group="default", enabled=True),
            ]
        ),
    )

    page = list_security_findings(user=None, limit=2, offset=0)
    assert page["total"] == 3
    assert len(page["items"]) == 2
    page2 = list_security_findings(user=None, limit=2, offset=2)
    assert len(page2["items"]) == 1


def test_rules_for_model_eos():
    from services.config_security_rules import rules_for_model

    ids = {r.id for r in rules_for_model("eos")}
    assert "eos-telnet" in ids
    assert "gen-cleartext-password" in ids
