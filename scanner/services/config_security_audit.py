"""Аудит конфигураций: анализ на misconfiguration и риски безопасности."""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any

from core.models import ConfigAuditRun, ConfigFinding
from django.db.models import Count
from services.config_security_rules import SEVERITY_ORDER, SecurityRule, rules_for_model
from services.inventory import load_inventory
from services.oxidized_client import get_node_config

logger = logging.getLogger(__name__)


def _model_matches(rule: SecurityRule, model: str) -> bool:
    model_key = (model or "").strip().lower()
    if not rule.models:
        return True
    if model_key in rule.models:
        return True
    return any(model_key.startswith(m) for m in rule.models)


def analyze_config_text(
    text: str,
    model: str,
) -> list[dict[str, Any]]:
    if not (text or "").strip():
        return []

    findings: list[dict[str, Any]] = []
    lines = text.splitlines()
    for rule in rules_for_model(model):
        if not _model_matches(rule, model):
            continue

        if rule.require_absence:
            if not rule.pattern.search(text):
                findings.append(_finding_from_rule(rule, evidence="(отсутствует в конфиге)"))
            continue

        if rule.match_full_text:
            match = rule.pattern.search(text)
            if match:
                line_no = text[: match.start()].count("\n") + 1
                evidence = _evidence_line(lines, line_no, match.group(0))
                findings.append(_finding_from_rule(rule, evidence=evidence, line_number=line_no))
            continue

        for idx, line in enumerate(lines, start=1):
            if rule.pattern.search(line):
                findings.append(
                    _finding_from_rule(rule, evidence=line.strip()[:500], line_number=idx)
                )
    return findings


def _evidence_line(lines: list[str], line_no: int, fallback: str) -> str:
    if 1 <= line_no <= len(lines):
        return lines[line_no - 1].strip()[:500]
    return fallback[:500]


def _finding_from_rule(
    rule: SecurityRule,
    *,
    evidence: str,
    line_number: int | None = None,
) -> dict[str, Any]:
    return {
        "rule_id": rule.id,
        "category": rule.category,
        "severity": rule.severity,
        "title": rule.title,
        "evidence": evidence,
        "line_number": line_number,
        "remediation": rule.remediation,
    }


def _resolve_devices(
    *,
    device_name: str = "",
    user=None,
) -> list[Any]:
    inventory = load_inventory()
    devices = [d for d in inventory.devices if d.enabled]
    if user is not None:
        from services.object_scope import filter_devices

        devices = filter_devices(user, devices)
    if device_name:
        devices = [d for d in devices if d.name == device_name]
    return devices


def run_config_audit(
    *,
    device_name: str = "",
    triggered_by: str = "system",
    user=None,
    run_id: int | None = None,
) -> dict[str, Any]:
    devices = _resolve_devices(device_name=device_name, user=user)
    now = datetime.now(timezone.utc)

    if run_id:
        run = ConfigAuditRun.objects.filter(pk=run_id).first()
        if not run:
            raise ValueError(f"ConfigAuditRun {run_id} not found")
        run.status = ConfigAuditRun.STATUS_RUNNING
        run.devices_total = len(devices)
        run.save(update_fields=["status", "devices_total"])
    else:
        run = ConfigAuditRun.objects.create(
            status=ConfigAuditRun.STATUS_RUNNING,
            triggered_by=triggered_by[:64],
            devices_total=len(devices),
            started_at=now,
        )

    scanned = 0
    skipped = 0
    findings_count = 0
    errors: list[str] = []

    try:
        for device in devices:
            config_text, err = get_node_config(device.name)
            if err or not config_text:
                skipped += 1
                if err:
                    errors.append(f"{device.name}: {err}")
                continue

            scanned += 1
            model = device.model or "routeros"
            for item in analyze_config_text(config_text, model):
                ConfigFinding.objects.create(
                    run=run,
                    device_name=device.name,
                    device_ip=device.ip or "",
                    device_model=model,
                    device_group=device.group or "",
                    device_site=device.site or "",
                    rule_id=item["rule_id"],
                    category=item["category"],
                    severity=item["severity"],
                    title=item["title"],
                    evidence=item.get("evidence", ""),
                    line_number=item.get("line_number"),
                    remediation=item.get("remediation", ""),
                )
                findings_count += 1

        run.status = ConfigAuditRun.STATUS_COMPLETED
        run.devices_scanned = scanned
        run.devices_skipped = skipped
        run.findings_count = findings_count
        run.finished_at = datetime.now(timezone.utc)
        run.error = "; ".join(errors[:20])[:2000]
        run.save()
        logger.info(
            "config_audit | completed | run=%s scanned=%s findings=%s",
            run.id,
            scanned,
            findings_count,
        )
        return _run_to_dict(run)
    except Exception as exc:
        logger.exception("config_audit | failed | run=%s", run.id)
        run.status = ConfigAuditRun.STATUS_FAILED
        run.error = str(exc)[:2000]
        run.finished_at = datetime.now(timezone.utc)
        run.save(update_fields=["status", "error", "finished_at"])
        raise


def get_latest_run() -> ConfigAuditRun | None:
    return (
        ConfigAuditRun.objects.filter(status=ConfigAuditRun.STATUS_COMPLETED)
        .order_by("-finished_at")
        .first()
    )


def _allowed_device_names(user) -> set[str] | None:
    if user is None:
        return None
    from services.object_scope import filter_devices

    return {d.name for d in filter_devices(user, load_inventory().devices)}


def compute_security_summary(
    *,
    severity: str = "",
    category: str = "",
    device: str = "",
    acknowledged: str | None = None,
    user=None,
) -> dict[str, Any]:
    run = get_latest_run()
    if not run:
        return {
            "run": None,
            "generated_at": _dt_iso(datetime.now(timezone.utc)),
            "devices_scanned": 0,
            "findings_total": 0,
            "counts": {s: 0 for s in SEVERITY_ORDER},
            "by_category": {},
            "findings": [],
            "rules_total": len(_all_rule_ids()),
        }

    allowed_names = _allowed_device_names(user)
    scoped_qs = ConfigFinding.objects.filter(run=run)
    if allowed_names is not None:
        scoped_qs = scoped_qs.filter(device_name__in=allowed_names)

    qs = scoped_qs
    if severity:
        qs = qs.filter(severity=severity.lower())
    if category:
        qs = qs.filter(category=category.lower())
    if device:
        qs = qs.filter(device_name=device)
    if acknowledged == "true":
        qs = qs.filter(acknowledged=True)
    elif acknowledged == "false":
        qs = qs.filter(acknowledged=False)

    findings = list(qs.order_by("severity", "device_name")[:500])

    counts = {s: 0 for s in SEVERITY_ORDER}
    for row in scoped_qs.values("severity").annotate(n=Count("id")):
        sev = row["severity"] if row["severity"] in counts else "info"
        counts[sev] = counts.get(sev, 0) + int(row["n"])

    by_category: dict[str, int] = {
        str(row["category"]): int(row["n"])
        for row in scoped_qs.values("category").annotate(n=Count("id"))
    }

    devices_with_findings = scoped_qs.values("device_name").distinct().count()

    return {
        "run": _run_to_dict(run),
        "generated_at": _dt_iso(run.finished_at or run.started_at),
        "devices_scanned": run.devices_scanned,
        "devices_with_findings": devices_with_findings,
        "findings_total": sum(counts.values()),
        "counts": counts,
        "by_category": by_category,
        "findings": [_finding_to_dict(f) for f in findings],
        "rules_total": len(_all_rule_ids()),
    }


def list_audit_runs(*, limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 100))
    return [_run_to_dict(r) for r in ConfigAuditRun.objects.order_by("-started_at")[:limit]]


def findings_to_csv(summary: dict[str, Any] | None = None) -> str:
    data = summary or compute_security_summary()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "device_name",
            "device_ip",
            "device_model",
            "device_group",
            "device_site",
            "severity",
            "category",
            "rule_id",
            "title",
            "evidence",
            "line_number",
            "remediation",
            "acknowledged",
        ]
    )
    for item in data.get("findings") or []:
        writer.writerow(
            [
                item.get("device_name", ""),
                item.get("device_ip", ""),
                item.get("device_model", ""),
                item.get("device_group", ""),
                item.get("device_site", ""),
                item.get("severity", ""),
                item.get("category", ""),
                item.get("rule_id", ""),
                item.get("title", ""),
                item.get("evidence", ""),
                item.get("line_number", "") or "",
                item.get("remediation", ""),
                "yes" if item.get("acknowledged") else "no",
            ]
        )
    return buf.getvalue()


def acknowledge_finding(finding_id: int, *, acknowledged: bool = True) -> dict[str, Any] | None:
    row = ConfigFinding.objects.filter(pk=finding_id).first()
    if not row:
        return None
    row.acknowledged = acknowledged
    row.save(update_fields=["acknowledged"])
    return _finding_to_dict(row)


def _all_rule_ids() -> set[str]:
    from services.config_security_rules import SECURITY_RULES

    return {r.id for r in SECURITY_RULES}


def _dt_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _run_to_dict(run: ConfigAuditRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status,
        "triggered_by": run.triggered_by,
        "devices_total": run.devices_total,
        "devices_scanned": run.devices_scanned,
        "devices_skipped": run.devices_skipped,
        "findings_count": run.findings_count,
        "error": run.error,
        "started_at": _dt_iso(run.started_at),
        "finished_at": _dt_iso(run.finished_at),
    }


def _finding_to_dict(row: ConfigFinding) -> dict[str, Any]:
    return {
        "id": row.id,
        "device_name": row.device_name,
        "device_ip": row.device_ip,
        "device_model": row.device_model,
        "device_group": row.device_group,
        "device_site": row.device_site,
        "rule_id": row.rule_id,
        "category": row.category,
        "severity": row.severity,
        "title": row.title,
        "evidence": row.evidence,
        "line_number": row.line_number,
        "remediation": row.remediation,
        "acknowledged": row.acknowledged,
        "created_at": _dt_iso(row.created_at),
    }
