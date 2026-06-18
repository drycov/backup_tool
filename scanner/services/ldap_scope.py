"""Маппинг LDAP/AD групп на object scope (allowed_groups / allowed_sites)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def normalize_ldap_dn(value: str) -> str:
    return value.strip().lower()


def _group_matches(member_values: list[str], configured: str) -> bool:
    needle = normalize_ldap_dn(configured)
    if not needle:
        return False
    for member in member_values:
        m = normalize_ldap_dn(member)
        if m == needle or needle in m:
            return True
    return False


def resolve_scope_from_ldap_groups(
    member_of: list[str],
    mappings: list[dict[str, Any]] | None,
) -> tuple[list[str], list[str]]:
    """Объединить allowed_groups/sites по всем совпавшим LDAP mappings."""
    if not mappings or not member_of:
        return [], []

    groups: set[str] = set()
    sites: set[str] = set()
    for entry in mappings:
        if not isinstance(entry, dict):
            continue
        ldap_group = str(entry.get("ldap_group") or "").strip()
        if not ldap_group:
            continue
        if not _group_matches(member_of, ldap_group):
            continue
        for g in entry.get("allowed_groups") or []:
            if g:
                groups.add(str(g).strip())
        for s in entry.get("allowed_sites") or []:
            if s:
                sites.add(str(s).strip())

    return sorted(groups), sorted(sites)


def validate_scope_mappings(mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not mappings:
        return []
    cleaned: list[dict[str, Any]] = []
    for entry in mappings:
        if not isinstance(entry, dict):
            continue
        ldap_group = str(entry.get("ldap_group") or "").strip()
        if not ldap_group:
            continue
        allowed_groups = [
            str(g).strip() for g in (entry.get("allowed_groups") or []) if str(g).strip()
        ]
        allowed_sites = [
            str(s).strip() for s in (entry.get("allowed_sites") or []) if str(s).strip()
        ]
        cleaned.append(
            {
                "ldap_group": ldap_group,
                "allowed_groups": allowed_groups,
                "allowed_sites": allowed_sites,
            }
        )
    return cleaned
