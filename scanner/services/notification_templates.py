"""Шаблоны уведомлений Backup Tools (Telegram HTML + plain text для email)."""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime
from typing import Any

TELEGRAM_MAX_LEN = 4096
MAX_DEVICES_IN_ALERT = 15

_DEGRADE_ICONS = {
    "Ошибки бэкапа": "❌",
    "Просроченные / отсутствующие бэкапы": "⏰",
    "Нет изменений конфига": "📁",
    "Устройства offline (scan)": "📡",
}


def _esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=False)


def _truncate_telegram(text: str, limit: int = TELEGRAM_MAX_LEN) -> str:
    if len(text) <= limit:
        return text
    suffix = "\n\n<i>… сообщение обрезано (лимит Telegram)</i>"
    return text[: max(0, limit - len(suffix))] + suffix


@dataclass
class NotificationBodies:
    telegram: str
    email: str
    parse_mode: str = "HTML"


def _format_device_block_telegram(devices: list[dict[str, Any]], total: int) -> list[str]:
    lines: list[str] = []
    shown = devices[:MAX_DEVICES_IN_ALERT]
    for device in shown:
        name = _esc(device.get("name", ""))
        ip = _esc(device.get("ip", ""))
        status = _esc(device.get("state_label", ""))
        lines.append(f"<b>{name}</b>\n<code>{ip}</code> · {status}")
    remaining = total - len(shown)
    if remaining > 0:
        lines.append(f"<i>… и ещё {remaining}</i>")
        lines.append("<i>Полный список: UI → Compliance</i>")
    return lines


def _format_device_block_email(devices: list[dict[str, Any]], total: int) -> list[str]:
    lines: list[str] = []
    shown = devices[:MAX_DEVICES_IN_ALERT]
    for device in shown:
        lines.append(
            f"• {device.get('name', '')} ({device.get('ip', '')}) — {device.get('state_label', '')}"
        )
    remaining = total - len(shown)
    if remaining > 0:
        lines.append(f"… и ещё {remaining}")
    return lines


def degradation_alert(
    kind_label: str,
    devices: list[dict[str, Any]],
    *,
    stale_days: int = 30,
) -> NotificationBodies:
    total = len(devices)
    icon = _DEGRADE_ICONS.get(kind_label, "⚠️")

    tg_header = [
        f"<b>{icon} Backup Tools · деградация</b>",
        "",
        f"<b>Категория:</b> {_esc(kind_label)}",
        f"<b>Устройств:</b> {total}",
        f"<b>Порог stale:</b> {stale_days} дн.",
        "",
        "────────────────",
    ]
    tg_lines = tg_header + _format_device_block_telegram(devices, total)
    telegram = _truncate_telegram("\n".join(tg_lines))

    email_lines = [
        f"{icon} Backup Tools — деградация",
        f"Категория: {kind_label}",
        f"Устройств: {total}",
        f"Порог stale: {stale_days} дн.",
        "",
        "Список:",
        *_format_device_block_email(devices, total),
    ]
    return NotificationBodies(telegram=telegram, email="\n".join(email_lines))


def backup_error(device: str, ip: str, status: str, detail: str = "") -> NotificationBodies:
    telegram_lines = [
        "<b>❌ Backup Tools · ошибка бэкапа</b>",
        "",
        f"<b>Устройство:</b> {_esc(device)}",
        f"<b>IP:</b> <code>{_esc(ip)}</code>",
        f"<b>Статус:</b> {_esc(status)}",
    ]
    email_lines = [
        "❌ Backup Tools — ошибка бэкапа",
        f"Устройство: {device}",
        f"IP: {ip}",
        f"Статус: {status}",
    ]
    if detail:
        telegram_lines.append(f"<b>Детали:</b> {_esc(detail)}")
        email_lines.append(f"Детали: {detail}")
    return NotificationBodies(
        telegram="\n".join(telegram_lines),
        email="\n".join(email_lines),
    )


def backup_report(
    device: str,
    ip: str,
    *,
    config_changed: bool,
    binary_ok: bool = True,
) -> NotificationBodies:
    change = "конфиг изменён" if config_changed else "без изменений в Git"
    binary = "OK" if binary_ok else "ошибка"
    icon = "✅" if binary_ok else "⚠️"
    return NotificationBodies(
        telegram="\n".join(
            [
                f"<b>{icon} Backup Tools · отчёт о бэкапе</b>",
                "",
                f"<b>Устройство:</b> {_esc(device)}",
                f"<b>IP:</b> <code>{_esc(ip)}</code>",
                f"<b>Git:</b> {_esc(change)}",
                f"<b>Binary/export:</b> {_esc(binary)}",
            ]
        ),
        email="\n".join(
            [
                f"{icon} Backup Tools — отчёт о бэкапе",
                f"Устройство: {device}",
                f"IP: {ip}",
                f"Git: {change}",
                f"Binary/export: {binary}",
            ]
        ),
    )


def test_notification(kind: str) -> NotificationBodies:
    kind = (kind or "report").strip().lower()
    labels = {
        "error": "ошибка",
        "report": "отчёт",
        "degrade": "деградация",
        "compliance": "compliance",
    }
    label = labels.get(kind, kind)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return NotificationBodies(
        telegram="\n".join(
            [
                "<b>🧪 Backup Tools · тест</b>",
                "",
                f"<b>Тип:</b> {_esc(label)}",
                f"<b>Время:</b> {now}",
                "",
                "Каналы уведомлений работают.",
            ]
        ),
        email="\n".join(
            [
                "🧪 Backup Tools — тестовое уведомление",
                f"Тип: {label}",
                f"Время: {now}",
                "",
                "Каналы уведомлений работают.",
            ]
        ),
    )


def compliance_report(summary: dict[str, Any]) -> NotificationBodies:
    counts = summary.get("counts") or {}
    stale_days = summary.get("stale_days_threshold", 30)
    compliance_pct = summary.get("compliance_pct", 0)
    total_enabled = summary.get("total_enabled", 0)

    tg_stats = [
        f"<b>OK:</b> {counts.get('ok', 0)}",
        f"<b>Ошибки:</b> {counts.get('failed', 0)}",
        f"<b>Просрочено:</b> {counts.get('overdue', 0)}",
        f"<b>Stale (&gt;{stale_days}д):</b> {counts.get('stale', 0)}",
        f"<b>Offline:</b> {counts.get('unreachable', 0)}",
        f"<b>Нет бэкапа:</b> {counts.get('never', 0)}",
    ]
    email_stats = [
        f"OK: {counts.get('ok', 0)}",
        f"Ошибки бэкапа: {counts.get('failed', 0)}",
        f"Просрочено: {counts.get('overdue', 0)}",
        f"Stale (>{stale_days}д): {counts.get('stale', 0)}",
        f"Offline: {counts.get('unreachable', 0)}",
        f"Нет бэкапа: {counts.get('never', 0)}",
    ]

    problems = [n for n in summary.get("nodes") or [] if n.get("state") != "ok"]
    problem_devices = [
        {
            "name": node.get("name", ""),
            "ip": node.get("ip", ""),
            "state_label": _problem_label(node),
        }
        for node in problems
    ]

    tg_problem_header = ["", "<b>Проблемные устройства:</b>"]
    if not problem_devices:
        tg_problem_lines = ["<i>(нет)</i>"]
        email_problem_lines = ["  (нет)"]
    else:
        tg_problem_lines = _format_device_block_telegram(problem_devices, len(problem_devices))
        email_problem_lines = [
            f"  {line[2:]}" if line.startswith("• ") else line
            for line in _format_device_block_email(problem_devices, len(problem_devices))
        ]

    telegram_parts = [
        "<b>📊 Backup Tools · compliance</b>",
        "",
        f"<b>Compliance:</b> {compliance_pct}%",
        f"<b>Устройств (enabled):</b> {total_enabled}",
        "",
        *tg_stats,
        *tg_problem_header,
        *tg_problem_lines,
    ]
    if summary.get("oxidized_error"):
        telegram_parts.extend(["", f"<b>Oxidized:</b> {_esc(summary['oxidized_error'])}"])

    email_parts = [
        "📊 Backup Tools — ежедневный compliance-отчёт",
        f"Compliance: {compliance_pct}%",
        f"Устройств (enabled): {total_enabled}",
        "",
        *email_stats,
        "",
        "Проблемные устройства:",
        *email_problem_lines,
    ]
    if summary.get("oxidized_error"):
        email_parts.extend(["", f"Oxidized: {summary['oxidized_error']}"])

    return NotificationBodies(
        telegram=_truncate_telegram("\n".join(telegram_parts)),
        email="\n".join(email_parts),
    )


def _problem_label(node: dict[str, Any]) -> str:
    label = str(node.get("state_label", "") or "")
    tags: list[str] = []
    if node.get("critical"):
        tags.append("critical")
    if node.get("site"):
        tags.append(str(node["site"]))
    if tags:
        label = f"{label} [{', '.join(tags)}]"
    return label


def compliance_report_scoped_prefix(
    bodies: NotificationBodies,
    *,
    active_filters: list[str],
    scope_note: str,
) -> NotificationBodies:
    if not active_filters and not scope_note:
        return bodies

    tg_extra: list[str] = []
    email_extra: list[str] = []
    if active_filters:
        tg_extra.append(f"<b>Фильтры:</b> {_esc(', '.join(active_filters))}")
        email_extra.append(f"Фильтры: {', '.join(active_filters)}")
    if scope_note:
        tg_extra.append(_esc(scope_note))
        email_extra.append(scope_note)

    tg_lines = bodies.telegram.splitlines()
    tg_lines[1:1] = ["", *tg_extra]
    email_lines = bodies.email.splitlines()
    email_lines[1:1] = ["", *email_extra]

    return NotificationBodies(
        telegram=_truncate_telegram("\n".join(tg_lines)),
        email="\n".join(email_lines),
        parse_mode=bodies.parse_mode,
    )
