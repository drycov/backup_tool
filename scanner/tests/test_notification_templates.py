"""Тесты шаблонов уведомлений."""

from __future__ import annotations

from services.notification_templates import (
    MAX_DEVICES_IN_ALERT,
    TELEGRAM_MAX_LEN,
    backup_error,
    compliance_report,
    degradation_alert,
)


def test_degradation_alert_device_count_and_truncation():
    devices = [
        {"name": f"dev{i}", "ip": f"10.0.0.{i}", "state_label": "Нет бэкапа"}
        for i in range(100)
    ]
    bodies = degradation_alert("Просроченные / отсутствующие бэкапы", devices, stale_days=30)

    assert "Устройств: 100" in bodies.email
    assert bodies.email.count("• dev") == MAX_DEVICES_IN_ALERT
    assert "… и ещё 85" in bodies.email

    assert "<b>Устройств:</b> 100" in bodies.telegram
    assert bodies.telegram.count("<b>dev") == MAX_DEVICES_IN_ALERT
    assert "… и ещё 85" in bodies.telegram
    assert len(bodies.telegram) <= TELEGRAM_MAX_LEN


def test_degradation_alert_escapes_html():
    bodies = degradation_alert(
        "Ошибки бэкапа",
        [{"name": "a<b>", "ip": "1.2.3.4", "state_label": "fail & retry"}],
    )
    assert "a&lt;b&gt;" in bodies.telegram
    assert "fail &amp; retry" in bodies.telegram
    assert "a<b>" in bodies.email


def test_backup_error_template():
    bodies = backup_error("router-1", "10.1.1.1", "fail", "timeout")
    assert "❌" in bodies.telegram
    assert "<code>10.1.1.1</code>" in bodies.telegram
    assert "timeout" in bodies.email


def test_compliance_report_empty_problems():
    summary = {
        "compliance_pct": 100,
        "total_enabled": 5,
        "stale_days_threshold": 30,
        "counts": {
            "ok": 5,
            "failed": 0,
            "overdue": 0,
            "stale": 0,
            "unreachable": 0,
            "never": 0,
        },
        "nodes": [{"name": "r1", "ip": "10.0.0.1", "state": "ok", "state_label": "OK"}],
    }
    bodies = compliance_report(summary)
    assert "100%" in bodies.telegram
    assert "(нет)" in bodies.email
