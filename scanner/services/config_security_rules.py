"""Правила анализа конфигураций на misconfiguration и риски безопасности."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SecurityRule:
    id: str
    title: str
    severity: str
    category: str
    remediation: str
    pattern: re.Pattern[str]
    models: frozenset[str] = frozenset()
    match_full_text: bool = False
    require_absence: bool = False


SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")

CATEGORY_LABELS = {
    "hardening": "Hardening",
    "access": "Доступ",
    "crypto": "Криптография",
    "snmp": "SNMP",
    "secrets": "Секреты",
    "services": "Сервисы",
}


def _rule(
    rule_id: str,
    title: str,
    severity: str,
    pattern: str,
    *,
    category: str = "hardening",
    remediation: str = "",
    models: tuple[str, ...] = (),
    flags: int = re.IGNORECASE | re.MULTILINE,
    match_full_text: bool = False,
    require_absence: bool = False,
) -> SecurityRule:
    return SecurityRule(
        id=rule_id,
        title=title,
        severity=severity,
        category=category,
        remediation=remediation,
        pattern=re.compile(pattern, flags),
        models=frozenset(models),
        match_full_text=match_full_text,
        require_absence=require_absence,
    )


SECURITY_RULES: tuple[SecurityRule, ...] = (
    # RouterOS / MikroTik
    _rule(
        "ros-telnet-enabled",
        "Включён Telnet",
        "high",
        r"^\s*(add\s+)?name=telnet\b[^\n]*disabled=no|^/ip\s+service\s+enable\s+telnet",
        models=("routeros",),
        category="services",
        remediation="Отключите Telnet: /ip service disable telnet",
        match_full_text=True,
    ),
    _rule(
        "ros-ftp-enabled",
        "Включён FTP",
        "high",
        r"^/ip\s+service\s+enable\s+ftp|^\s*(add\s+)?name=ftp\b.*disabled=no",
        models=("routeros",),
        category="services",
        remediation="Отключите FTP: /ip service disable ftp",
        match_full_text=True,
    ),
    _rule(
        "ros-www-http",
        "Включён HTTP (без HTTPS)",
        "medium",
        r"^/ip\s+service\s+enable\s+www\b|^\s*(add\s+)?name=www\b.*disabled=no",
        models=("routeros",),
        category="services",
        remediation="Отключите www, используйте www-ssl",
        match_full_text=True,
    ),
    _rule(
        "ros-api-insecure",
        "API без SSL",
        "high",
        r"^\s*(add\s+)?name=api\b[^\n]*disabled=no",
        models=("routeros",),
        category="access",
        remediation="Отключите api или включите api-ssl, ограничьте доступ по firewall",
        match_full_text=True,
    ),
    _rule(
        "ros-snmp-public",
        "SNMP community public/default",
        "high",
        r"community.*name=(\"?)(public|\"\"|)\1|^snmp-community.*public",
        models=("routeros",),
        category="snmp",
        remediation="Замените SNMP community, ограничьте доступ ACL",
        match_full_text=True,
    ),
    _rule(
        "ros-password-in-config",
        "Пароль в открытом виде в конфиге",
        "critical",
        r"password=\S+",
        models=("routeros",),
        category="secrets",
        remediation="Используйте secret/hash; не храните plaintext в экспорте",
        match_full_text=True,
    ),
    _rule(
        "ros-no-firewall",
        "Нет правил firewall filter",
        "medium",
        r"/ip\s+firewall\s+filter",
        models=("routeros",),
        category="hardening",
        remediation="Настройте /ip firewall filter для ограничения доступа",
        match_full_text=True,
        require_absence=True,
    ),
    # Cisco IOS / IOS-XE
    _rule(
        "ios-telnet",
        "Разрешён Telnet (transport input telnet)",
        "high",
        r"transport\s+input\s+.*telnet|line\s+vty.*telnet",
        models=("ios", "iosxe", "iosxr"),
        category="access",
        remediation="Используйте только SSH: transport input ssh",
        match_full_text=True,
    ),
    _rule(
        "ios-snmp-public",
        "SNMP community public",
        "high",
        r"snmp-server\s+community\s+public\b",
        models=("ios", "iosxe", "iosxr"),
        category="snmp",
        remediation="Смените SNMP community, настройте ACL",
    ),
    _rule(
        "ios-http-server",
        "Включён HTTP server",
        "medium",
        r"^ip\s+http\s+server\b",
        models=("ios", "iosxe"),
        category="services",
        remediation="Отключите: no ip http server; используйте ip http secure-server",
    ),
    _rule(
        "ios-no-enable-secret",
        "Нет enable secret",
        "high",
        r"^enable\s+secret\b",
        models=("ios", "iosxe"),
        category="access",
        remediation="Настройте enable secret с надёжным паролем",
        match_full_text=True,
        require_absence=True,
    ),
    _rule(
        "ios-ssh-v1",
        "SSH version 1",
        "high",
        r"ip\s+ssh\s+version\s+1\b",
        models=("ios", "iosxe"),
        category="crypto",
        remediation="Используйте ip ssh version 2",
    ),
    # Juniper JunOS
    _rule(
        "junos-telnet",
        "Включён Telnet",
        "high",
        r"telnet\b",
        models=("junos",),
        category="services",
        remediation="Отключите Telnet в system services",
        match_full_text=True,
    ),
    _rule(
        "junos-snmp-public",
        "SNMP community public",
        "high",
        r"community\s+public\b",
        models=("junos",),
        category="snmp",
        remediation="Замените SNMP community",
    ),
    # Generic
    _rule(
        "gen-private-key",
        "Приватный ключ в конфигурации",
        "critical",
        r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
        category="secrets",
        remediation="Удалите ключ из конфига, храните в защищённом хранилище",
        match_full_text=True,
    ),
    _rule(
        "gen-cleartext-password",
        "Пароль в открытом виде",
        "critical",
        r"(password|secret)\s+0\s+|password\s+\d+\s+\S+",
        category="secrets",
        remediation="Используйте type 5/8/9 (hash) вместо cleartext",
        match_full_text=True,
    ),
)


def rules_for_model(model: str) -> list[SecurityRule]:
    model_key = (model or "").strip().lower()
    aliases = {
        "routeros": "routeros",
        "ros": "routeros",
        "mikrotik": "routeros",
        "ios": "ios",
        "iosxe": "iosxe",
        "ios-xe": "iosxe",
        "iosxr": "iosxr",
        "ios-xr": "iosxr",
        "junos": "junos",
        "juniper": "junos",
    }
    normalized = aliases.get(model_key, model_key)
    result: list[SecurityRule] = []
    for rule in SECURITY_RULES:
        if rule.models and normalized not in rule.models:
            if not any(normalized.startswith(m) for m in rule.models):
                continue
        result.append(rule)
    return result
