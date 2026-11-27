"""Classify Git changes without exposing configuration contents."""
import re

_RULES = (
    ("firewall", "critical", r"firewall|access-list|acl|security policy"),
    ("aaa", "high", r"radius|tacacs|aaa|/user|username|authentication"),
    ("routing", "high", r"bgp|ospf|is-is|isis|mpls|/ip route|routing-options"),
    ("segmentation", "high", r"vlan|vrf|bridge|switchport"),
    ("vpn", "high", r"wireguard|ipsec|tunnel|l2tp|pppoe"),
    ("management", "medium", r"snmp|ssh|ntp|logging|syslog"),
)
_PATTERNS = [(category, severity, re.compile(pattern, re.I)) for category, severity, pattern in _RULES]
_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def classify_patch(patch):
    categories = set()
    severity = "none"
    added = removed = 0
    context = ""
    for line in patch.splitlines():
        if line.startswith(("diff --git ", "@@")):
            context = line
            continue
        if line.startswith(("+++ ", "--- ")):
            continue
        if line.startswith(" "):
            if line[1:].startswith("/") or line[1:].startswith("["):
                context = line[1:]
            continue
        if not line.startswith(("+", "-")):
            continue
        added += int(line.startswith("+"))
        removed += int(line.startswith("-"))
        text = line[1:]
        if text.startswith("/"):
            context = text
        matches = [(category, risk) for category, risk, pattern in _PATTERNS if pattern.search(context + " " + text)]
        for category, risk in matches or [("other", "low")]:
            categories.add(category)
            if _RANK[risk] > _RANK[severity]:
                severity = risk
    return {"severity": severity, "categories": sorted(categories), "added": added, "removed": removed}
