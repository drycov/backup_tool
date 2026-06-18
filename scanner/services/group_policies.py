"""Политики бэкапа per-group — интервал, модель, MikroTik."""

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


def _row_to_data(row: GroupPolicy) -> GroupPolicyData:
    return GroupPolicyData(
        group_name=row.group_name,
        backup_interval_sec=row.backup_interval_sec or 0,
        model=row.model or "",
        mk_binary_enabled=row.mk_binary_enabled,
        mk_export_enabled=row.mk_export_enabled,
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


def save_policy(payload: dict[str, Any]) -> GroupPolicyData:
    group_name = str(payload.get("group_name", "")).strip()
    if not group_name:
        raise ValueError("group_name обязателен")

    interval = int(payload.get("backup_interval_sec", 0))
    if interval != 0 and (interval < 60 or interval > 604800):
        raise ValueError("backup_interval_sec: 0 (глобальный) или 60–604800")

    mk_binary = payload.get("mk_binary_enabled")
    if mk_binary in ("inherit", "null", ""):
        mk_binary = None
    elif mk_binary is not None:
        mk_binary = bool(mk_binary)

    mk_export = payload.get("mk_export_enabled")
    if mk_export in ("inherit", "null", ""):
        mk_export = None
    elif mk_export is not None:
        mk_export = bool(mk_export)

    row, _ = GroupPolicy.objects.update_or_create(
        group_name=group_name,
        defaults={
            "backup_interval_sec": interval,
            "model": str(payload.get("model", "")).strip(),
            "mk_binary_enabled": mk_binary,
            "mk_export_enabled": mk_export,
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
    }
