"""Resolve the existing group policy without duplicating its persistence."""
from services.group_policies import get_policy


def resolve_policy(group, interval, *, binary=True, export=True, telegram=False, email=False):
    policy = get_policy(group)
    values = {
        "interval_sec": max(60, int(interval)),
        "binary_enabled": binary,
        "export_enabled": export,
        "notify_telegram": telegram,
        "notify_email": email,
        "maintenance_override": None,
        "sla_hours": None,
    }
    sources = dict.fromkeys(values, "global")
    fields = {
        "interval_sec": "backup_interval_sec",
        "binary_enabled": "mk_binary_enabled",
        "export_enabled": "mk_export_enabled",
        "notify_telegram": "notify_telegram",
        "notify_email": "notify_email",
        "maintenance_override": "maintenance_override",
        "sla_hours": "compliance_sla_hours",
    }
    if policy:
        for key, field in fields.items():
            value = getattr(policy, field)
            if value is None or (key == "interval_sec" and value < 60) or (key == "sla_hours" and value < 1):
                continue
            values[key] = value
            sources[key] = "group"
    return {**values, "sources": sources}
