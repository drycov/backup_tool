"""Безопасный read-only просмотр runtime ENV для UI настроек.

Показываем только известные переменные приложения. Секреты никогда не
возвращаются в открытом виде и не включаются в экспорт.
"""
from __future__ import annotations

import os
from collections import OrderedDict
from typing import Any


ENV_GROUPS: "OrderedDict[str, tuple[str, ...]]" = OrderedDict(
    [
        ("Инфраструктура", (
            "STACK_PATH", "DATABASE_URL", "SCANNER_PORT", "SCANNER_IMAGE_TAG",
            "LOG_LEVEL", "DEBUG", "ALLOWED_HOSTS",
            "INVENTORY_PATH", "NETWORK_INVENTORY_PATH", "ROUTER_DB_PATH",
            "OXIDIZED_HOME", "OXIDIZED_CONFIG_PATH", "OXIDIZED_LOG_PATH",
            "OXIDIZED_PYTHON_LOG_PATH",
        )),
        ("Scan / Discovery / Scheduler / AI", (
            "SCAN_CONCURRENCY", "DISCOVER_MAX_HOSTS", "DISCOVER_PING_WORKERS",
            "SCHEDULER_TICK_SEC", "AI_ENABLED", "AI_DISCOVERY_ENABLED",
            "AI_OLLAMA_URL", "AI_MODEL", "AI_TIMEOUT_SEC", "OLLAMA_PORT",
        )),
        ("Авторизация", (
            "JWT_SECRET", "ACCESS_TOKEN_EXPIRE_MINUTES", "ADMIN_USERNAME",
            "ADMIN_PASSWORD", "AUTH_COOKIE_NAME",
        )),
        ("LDAP", (
            "LDAP_ENABLED", "LDAP_AD", "LDAP_SERVER", "LDAP_USE_SSL",
            "LDAP_START_TLS", "LDAP_BIND_DN", "LDAP_BIND_PASSWORD",
            "LDAP_USER_BASE", "LDAP_USER_FILTER", "LDAP_USER_DN_TEMPLATE",
            "LDAP_USER_UPN_SUFFIX", "LDAP_ADMIN_GROUPS", "LDAP_OPERATOR_GROUPS",
            "LDAP_DEFAULT_ROLE", "LDAP_FALLBACK_LOCAL", "LDAP_CONNECT_TIMEOUT",
        )),
        ("RADIUS", (
            "RADIUS_ENABLED", "RADIUS_SERVER", "RADIUS_PORT", "RADIUS_SECRET",
            "RADIUS_TIMEOUT", "RADIUS_RETRIES", "RADIUS_NAS_IDENTIFIER",
            "RADIUS_ROLE_ATTRIBUTE", "RADIUS_ADMIN_VALUES",
            "RADIUS_OPERATOR_VALUES", "RADIUS_DEFAULT_ROLE", "RADIUS_FALLBACK_LOCAL",
        )),
        ("Credentials / SSH", (
            "OVN_USER", "OVN_PASS", "US_USER", "US_PASS", "ROUTEROS_SSH_PORT",
        )),
        ("Oxidized", (
            "OXIDIZED_ENGINE", "OXIDIZED_INTERVAL", "OXIDIZED_THREADS",
            "OXIDIZED_TIMEOUT", "OXIDIZED_RETRIES", "OXIDIZED_GIT_REPO",
            "OXIDIZED_RESOLVE_DNS", "OXIDIZED_DEFAULT_MODEL", "OXIDIZED_SOURCE_URL",
            "OXIDIZED_SOURCE_TOKEN", "OXIDIZED_URL", "OXIDIZED_PORT",
            "CONFIG_RELOAD_INTERVAL", "OXIDIZED_SSH_PASSPHRASE", "OXIDIZED_PUBLIC_URL",
        )),
        ("Git", (
            "GIT_REMOTE_URL", "GITEA_TOKEN", "GITEA_HTTP_USER", "GIT_COMMIT_USER",
            "GIT_COMMIT_EMAIL", "GIT_BRANCH", "GIT_SSH_PRIVATE_KEY",
            "GIT_SSH_PUBLIC_KEY",
        )),
        ("MikroTik backup", (
            "MK_BACKUP_BINARY", "MK_BACKUP_EXPORT", "MK_BACKUP_HIDE_SENSITIVE",
            "MK_BACKUP_ENCRYPT_PASSWORD", "MK_BACKUP_BIN_DIR", "MK_BACKUP_RSC_DIR",
            "MK_BACKUP_TIMEOUT", "MK_BACKUP_GIT_PUSH", "PURGE_OLD_BACKUP",
            "PURGE_N_PIECE",
        )),
        ("Уведомления", (
            "ERROR_NOTIFICATION_TELEGRAM", "ERROR_NOTIFICATION_EMAIL",
            "DEGRADE_NOTIFICATION_TELEGRAM", "DEGRADE_NOTIFICATION_EMAIL",
            "STALE_DAYS_THRESHOLD", "ALERT_COOLDOWN_HOURS", "DEGRADE_CHECK_INTERVAL_SEC",
            "REPORT_SEND_TELEGRAM", "REPORT_SEND_EMAIL", "TELEGRAM_ACCESS_TOKEN",
            "TELEGRAM_CHATID_NOTIFY", "TELEGRAM_CHATID_REPORT", "SMTP_SERVER",
            "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_SSL", "SMTP_FROM_MAIL",
            "SMTP_TO_MAIL_NOTIFY", "SMTP_TO_MAIL_REPORT", "COMPLIANCE_REPORT_TELEGRAM",
            "COMPLIANCE_REPORT_EMAIL", "COMPLIANCE_REPORT_HOUR_UTC",
            "DEGRADE_WEBHOOK_ENABLED", "DEGRADE_WEBHOOK_URL",
        )),
        ("Zabbix / Platform", (
            "ZABBIX_AUTH_KEY", "ZABBIX_MONITORING_ENABLED", "BACKUP_DATA_DIR",
            "MAINTENANCE_WINDOW_ENABLED", "MAINTENANCE_START_HOUR_UTC",
            "MAINTENANCE_END_HOUR_UTC",
        )),
        ("PostgreSQL", (
            "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
        )),
    ]
)

SECRET_NAMES = {
    name
    for names in ENV_GROUPS.values()
    for name in names
    if any(token in name for token in (
        "PASSWORD", "PASS", "SECRET", "TOKEN", "AUTH_KEY", "PRIVATE_KEY",
    ))
}
SECRET_NAMES.update({"DATABASE_URL", "RADIUS_SECRET", "TELEGRAM_ACCESS_TOKEN"})


def _mask(value: str) -> str:
    if not value:
        return ""
    return "••••••••"


def get_env_public() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for group, names in ENV_GROUPS.items():
        for name in names:
            raw = os.environ.get(name)
            is_set = raw is not None and raw != ""
            secret = name in SECRET_NAMES
            items.append({
                "name": name,
                "group": group,
                "value": _mask(raw or "") if secret else (raw or ""),
                "set": is_set,
                "secret": secret,
            })
    return {
        "source": "process environment",
        "groups": list(ENV_GROUPS.keys()),
        "items": items,
    }


def get_env_export() -> str:
    """Безопасный .env snapshot: секреты заменяются на пустое значение."""
    lines = [
        "# Backup Tools — безопасный snapshot runtime ENV",
        "# Секреты намеренно не выгружаются.",
        "",
    ]
    for group, names in ENV_GROUPS.items():
        lines.append(f"# ── {group} ──")
        for name in names:
            raw = os.environ.get(name)
            value = "" if name in SECRET_NAMES else (raw or "")
            safe = value.replace("\\", "\\\\").replace("\n", "\\n")
            lines.append(f"{name}={safe}")
        lines.append("")
    return "\n".join(lines)
