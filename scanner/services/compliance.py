"""Compliance-дашборд: агрегация статуса бэкапов и доступности."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Any

from services.backup_settings import get_config
from services.group_policies import effective_interval
from services.inventory import load_inventory
from services.oxidized_client import get_nodes
from services.oxidized_settings import get_oxidized_settings
from services.scan_history import get_latest_scan_reachability

STATE_OK = "ok"
STATE_FAILED = "failed"
STATE_STALE = "stale"
STATE_OVERDUE = "overdue"
STATE_NEVER = "never"
STATE_UNREACHABLE = "unreachable"

_STATE_LABELS = {
    STATE_OK: "OK",
    STATE_FAILED: "Ошибка бэкапа",
    STATE_STALE: "Нет изменений",
    STATE_OVERDUE: "Просрочен бэкап",
    STATE_NEVER: "Нет бэкапа",
    STATE_UNREACHABLE: "Offline (scan)",
}


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _classify_node(
    node: dict[str, Any],
    *,
    reachability: str | None,
    stale_cutoff: datetime,
    overdue_cutoff: datetime,
) -> tuple[str, list[str], dict[str, Any]]:
    issues: list[str] = []
    last = node.get("last") or {}
    last_status = (last.get("status") if last else None) or node.get("status") or "never"
    last_end = _parse_dt(last.get("end") if last else None)
    mtime = float(node.get("mtime") or 0)
    mtime_dt = _parse_dt(mtime) if mtime > 0 else None

    if reachability == "offline":
        issues.append(STATE_UNREACHABLE)
    if last_status in ("fail", "no_connection"):
        issues.append(STATE_FAILED)
    elif last_status in ("never", None, "") and mtime <= 0:
        issues.append(STATE_NEVER)
    if last_end and last_end < overdue_cutoff:
        if STATE_NEVER not in issues:
            issues.append(STATE_OVERDUE)
    elif mtime_dt and mtime_dt < overdue_cutoff and STATE_NEVER not in issues:
        issues.append(STATE_OVERDUE)
    if mtime_dt and mtime_dt < stale_cutoff and last_status == "success":
        issues.append(STATE_STALE)

    priority = [
        STATE_UNREACHABLE,
        STATE_FAILED,
        STATE_NEVER,
        STATE_OVERDUE,
        STATE_STALE,
        STATE_OK,
    ]
    primary = STATE_OK
    for state in priority:
        if state in issues:
            primary = state
            break

    return primary, issues, {
        "last_status": last_status,
        "last_backup_at": last_end,
        "config_mtime": mtime_dt,
        "reachability": reachability,
    }


def compute_compliance_summary(
    *,
    site: str = "",
    role: str = "",
    critical: str | None = None,
    group: str = "",
    state: str = "",
    user=None,
) -> dict[str, Any]:
    cfg = get_config()
    stale_days = max(1, cfg.stale_days_threshold)
    ox_settings = get_oxidized_settings()
    global_interval = max(60, int(ox_settings.get("interval") or 3600))

    inventory = load_inventory()
    enabled = [d for d in inventory.devices if d.enabled]
    if user is not None:
        from services.object_scope import filter_devices

        enabled = filter_devices(user, enabled)

    if site:
        enabled = [d for d in enabled if (d.site or "").lower() == site.lower()]
    if role:
        enabled = [d for d in enabled if (d.role or "").lower() == role.lower()]
    if critical == "true":
        enabled = [d for d in enabled if d.critical]
    elif critical == "false":
        enabled = [d for d in enabled if not d.critical]
    if group:
        enabled = [d for d in enabled if (d.group or "").lower() == group.lower()]

    reachability = get_latest_scan_reachability()

    nodes, oxidized_error = get_nodes()
    node_map = {n.get("name"): n for n in (nodes or []) if n.get("name")}

    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=stale_days)

    counts = {s: 0 for s in _STATE_LABELS}
    items: list[dict[str, Any]] = []

    for device in enabled:
        node = node_map.get(device.name, {})
        interval = effective_interval(device.group, global_interval)
        overdue_cutoff = now - timedelta(seconds=interval * 2)
        primary, issues, meta = _classify_node(
            node,
            reachability=reachability.get(device.name),
            stale_cutoff=stale_cutoff,
            overdue_cutoff=overdue_cutoff,
        )
        if state and primary != state:
            continue
        counts[primary] = counts.get(primary, 0) + 1
        items.append(
            {
                "name": device.name,
                "ip": device.ip,
                "group": device.group,
                "model": device.model,
                "site": device.site or "",
                "role": device.role or "",
                "critical": device.critical,
                "state": primary,
                "state_label": _STATE_LABELS.get(primary, primary),
                "issues": issues,
                "last_status": meta["last_status"],
                "last_backup_at": meta["last_backup_at"],
                "config_mtime": meta["config_mtime"],
                "reachability": meta["reachability"],
                "backup_interval_sec": interval,
            }
        )

    items.sort(key=lambda x: (x["state"] != STATE_OK, x["name"]))
    total = len(items)
    ok_count = counts.get(STATE_OK, 0)
    compliance_pct = round(100.0 * ok_count / total, 1) if total else 100.0

    return {
        "generated_at": now,
        "stale_days_threshold": stale_days,
        "backup_interval_sec": global_interval,
        "total_enabled": total,
        "compliance_pct": compliance_pct,
        "counts": counts,
        "state_labels": _STATE_LABELS,
        "nodes": items,
        "oxidized_error": oxidized_error,
        "filters": {
            "site": site,
            "role": role,
            "critical": critical,
            "group": group,
            "state": state,
        },
    }


def compute_compliance_by_site(*, user=None) -> dict[str, Any]:
    """Группировка compliance по site для дашборда."""
    summary = compute_compliance_summary(user=user)
    buckets: dict[str, dict[str, Any]] = {}
    for node in summary.get("nodes") or []:
        site = (node.get("site") or "").strip() or "(без site)"
        bucket = buckets.setdefault(
            site,
            {"site": site, "total": 0, "ok": 0, "failed": 0, "critical": 0},
        )
        bucket["total"] += 1
        if node.get("state") == "ok":
            bucket["ok"] += 1
        else:
            bucket["failed"] += 1
        if node.get("critical"):
            bucket["critical"] += 1

    sites = []
    for site, bucket in sorted(buckets.items(), key=lambda x: x[0].lower()):
        total = bucket["total"]
        ok = bucket["ok"]
        bucket["compliance_pct"] = round(100.0 * ok / total, 1) if total else 100.0
        sites.append(bucket)

    return {
        "generated_at": summary.get("generated_at"),
        "total_sites": len(sites),
        "sites": sites,
    }


def compliance_to_csv(summary: dict[str, Any] | None = None) -> str:
    data = summary or compute_compliance_summary()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "name",
            "ip",
            "group",
            "site",
            "role",
            "critical",
            "state",
            "state_label",
            "last_status",
            "last_backup_at",
            "reachability",
            "backup_interval_sec",
        ]
    )
    for node in data.get("nodes") or []:
        writer.writerow(
            [
                node.get("name", ""),
                node.get("ip", ""),
                node.get("group", ""),
                node.get("site", ""),
                node.get("role", ""),
                "yes" if node.get("critical") else "no",
                node.get("state", ""),
                node.get("state_label", ""),
                node.get("last_status", ""),
                node.get("last_backup_at", "") or "",
                node.get("reachability", "") or "",
                node.get("backup_interval_sec", ""),
            ]
        )
    return buf.getvalue()


def _pdf_text(value: Any) -> str:
    return str(value or "").encode("latin-1", errors="replace").decode("latin-1")


def compliance_to_pdf(summary: dict[str, Any] | None = None) -> bytes:
    from fpdf import FPDF

    data = summary or compute_compliance_summary()
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, _pdf_text("Backup Tools - Compliance report"), ln=True)
    pdf.set_font("Helvetica", size=10)
    generated = data.get("generated_at")
    if generated:
        pdf.cell(0, 6, _pdf_text(f"Generated: {generated.isoformat()}"), ln=True)
    pdf.cell(0, 6, _pdf_text(f"Compliance: {data.get('compliance_pct', 0)}%"), ln=True)
    pdf.cell(0, 6, _pdf_text(f"Devices (enabled): {data.get('total_enabled', 0)}"), ln=True)
    filters = data.get("filters") or {}
    if any(filters.values()):
        pdf.cell(
            0,
            6,
            _pdf_text(
                "Filters: "
                + ", ".join(f"{k}={v}" for k, v in filters.items() if v)
            ),
            ln=True,
        )
    pdf.ln(2)

    col_widths = (38, 28, 22, 18, 18, 22, 38)
    headers = ("name", "ip", "group", "site", "state", "reach", "last_backup")
    pdf.set_font("Helvetica", "B", 8)
    for idx, header in enumerate(headers):
        pdf.cell(col_widths[idx], 6, header, border=1)
    pdf.ln()

    pdf.set_font("Helvetica", size=7)
    for node in data.get("nodes") or []:
        last_backup = node.get("last_backup_at")
        last_txt = last_backup.isoformat() if hasattr(last_backup, "isoformat") else str(last_backup or "")
        row = (
            node.get("name", ""),
            node.get("ip", ""),
            node.get("group", ""),
            node.get("site", ""),
            node.get("state", ""),
            node.get("reachability", "") or "",
            last_txt,
        )
        for idx, cell in enumerate(row):
            pdf.cell(col_widths[idx], 5, _pdf_text(cell)[:40], border=1)
        pdf.ln()
    return pdf.output()


def collect_degradation_issues() -> dict[str, list[dict[str, Any]]]:
    summary = compute_compliance_summary()
    buckets: dict[str, list[dict[str, Any]]] = {
        "backup_failed": [],
        "backup_overdue": [],
        "config_stale": [],
        "device_offline": [],
    }
    for node in summary["nodes"]:
        issues = node.get("issues") or []
        entry = {
            "name": node["name"],
            "ip": node["ip"],
            "state_label": node["state_label"],
        }
        if STATE_FAILED in issues:
            buckets["backup_failed"].append(entry)
        if STATE_OVERDUE in issues or STATE_NEVER in issues:
            buckets["backup_overdue"].append(entry)
        if STATE_STALE in issues:
            buckets["config_stale"].append(entry)
        if STATE_UNREACHABLE in issues:
            buckets["device_offline"].append(entry)
    return buckets
