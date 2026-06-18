"""Политики бэкапа per-group — интервал, модель, MikroTik, notify, SLA."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from core.models import GroupPolicy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GroupPolicyData:
    group_name: str
    backup_interval_sec: int
    model: str
    mk_binary_enabled: bool | None
    mk_export_enabled: bool | None
    notify_telegram: bool | None
    notify_email: bool | None
    maintenance_override: bool | None
    compliance_sla_hours: int | None


def _row_to_data(row: GroupPolicy) -> GroupPolicyData:
    return GroupPolicyData(
        group_name=row.group_name,
        backup_interval_sec=row.backup_interval_sec or 0,
        model=row.model or "",
        mk_binary_enabled=row.mk_binary_enabled,
        mk_export_enabled=row.mk_export_enabled,
        notify_telegram=row.notify_telegram,
        notify_email=row.notify_email,
        maintenance_override=row.maintenance_override,
        compliance_sla_hours=row.compliance_sla_hours,
    )


def list_policies() -> list[GroupPolicyData]:
    return [_row_to_data(row) for row in GroupPolicy.objects.order_by("group_name")]


def get_policy(group_name: str) -> GroupPolicyData | None:
    row = GroupPolicy.objects.filter(group_name=group_name).first()
    return _row_to_data(row) if row else None


def effective_interval(group_name: str, global_interval: int) -> int:
    policy = get_policy(group_name)
    if policy and policy.backup_interval_sec >= 60:
        return policy.backup_interval_sec
    return max(60, global_interval)


def effective_mk_flags(
    group_name: str,
    global_binary: bool,
    global_export: bool,
) -> tuple[bool, bool]:
    policy = get_policy(group_name)
    if not policy:
        return global_binary, global_export
    binary = global_binary if policy.mk_binary_enabled is None else policy.mk_binary_enabled
    export = global_export if policy.mk_export_enabled is None else policy.mk_export_enabled
    return binary, export


def effective_notify_flags(
    group_name: str,
    global_telegram: bool,
    global_email: bool,
) -> tuple[bool, bool]:
    policy = get_policy(group_name)
    if not policy:
        return global_telegram, global_email
    tg = global_telegram if policy.notify_telegram is None else policy.notify_telegram
    em = global_email if policy.notify_email is None else policy.notify_email
    return tg, em


def effective_maintenance_override(group_name: str) -> bool | None:
    policy = get_policy(group_name)
    if not policy:
        return None
    return policy.maintenance_override


def effective_compliance_sla_hours(group_name: str) -> int | None:
    policy = get_policy(group_name)
    if not policy or not policy.compliance_sla_hours:
        return None
    return max(1, policy.compliance_sla_hours)


def _nullable_bool(value: Any) -> bool | None:
    if value in ("inherit", "null", "", None):
        return None
    return bool(value)


def save_policy(payload: dict[str, Any]) -> GroupPolicyData:
    group_name = str(payload.get("group_name", "")).strip()
    if not group_name:
        raise ValueError("group_name обязателен")

    interval = int(payload.get("backup_interval_sec", 0))
    if interval != 0 and (interval < 60 or interval > 604800):
        raise ValueError("backup_interval_sec: 0 (глобальный) или 60–604800")

    sla = payload.get("compliance_sla_hours")
    if sla in ("inherit", "null", "", None):
        sla_val = None
    else:
        sla_val = int(sla)
        if sla_val < 1 or sla_val > 8760:
            raise ValueError("compliance_sla_hours: 1–8760 или inherit")

    row, _ = GroupPolicy.objects.update_or_create(
        group_name=group_name,
        defaults={
            "backup_interval_sec": interval,
            "model": str(payload.get("model", "")).strip(),
            "mk_binary_enabled": _nullable_bool(payload.get("mk_binary_enabled")),
            "mk_export_enabled": _nullable_bool(payload.get("mk_export_enabled")),
            "notify_telegram": _nullable_bool(payload.get("notify_telegram")),
            "notify_email": _nullable_bool(payload.get("notify_email")),
            "maintenance_override": _nullable_bool(payload.get("maintenance_override")),
            "compliance_sla_hours": sla_val,
        },
    )

    if row.model:
        from services.oxidized_settings import set_group_model

        set_group_model(group_name, row.model)

    logger.info("group_policy | saved | %s interval=%s", group_name, interval)
    return _row_to_data(row)


def delete_policy(group_name: str) -> bool:
    deleted, _ = GroupPolicy.objects.filter(group_name=group_name).delete()
    return deleted > 0


def policy_to_public(data: GroupPolicyData) -> dict[str, Any]:
    return {
        "group_name": data.group_name,
        "backup_interval_sec": data.backup_interval_sec,
        "model": data.model,
        "mk_binary_enabled": data.mk_binary_enabled,
        "mk_export_enabled": data.mk_export_enabled,
        "mk_binary_inherit": data.mk_binary_enabled is None,
        "mk_export_inherit": data.mk_export_enabled is None,
        "notify_telegram": data.notify_telegram,
        "notify_email": data.notify_email,
        "notify_telegram_inherit": data.notify_telegram is None,
        "notify_email_inherit": data.notify_email is None,
        "maintenance_override": data.maintenance_override,
        "compliance_sla_hours": data.compliance_sla_hours,
    }
