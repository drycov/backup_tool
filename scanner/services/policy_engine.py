"""Resolve the existing group policy without duplicating its persistence."""
from services.group_policies import get_policy


def resolve_policy(group, interval, *, binary=True, export=True, telegram=False, email=False, site="", device=""):
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
    if site or device:
        from core.models import BackupPolicyOverride
        from django.db.models import Q

        rows = BackupPolicyOverride.objects.filter(Q(scope="site", target=site) | Q(scope="device", target=device))
        overrides = {(row.scope, row.target): row.values for row in rows}
        # Precedence: global < site < group < device.
        for key, value in overrides.get(("site", site), {}).items():
            if key in values and value is not None and sources[key] == "global":
                values[key], sources[key] = value, "site"
        for key, value in overrides.get(("device", device), {}).items():
            if key in values and value is not None:
                values[key], sources[key] = value, "device"
    return {**values, "sources": sources}


def resolve_device_policy(name, group, interval, **kwargs):
    from core.models import Device

    row = Device.objects.filter(name=name).values("group", "site").first()
    if row:
        return resolve_policy(row["group"], interval, site=row["site"], device=name, **kwargs)
    return resolve_policy(group, interval, **kwargs)


def validate_override(values):
    if not isinstance(values, dict):
        raise ValueError("Expected policy object")
    clean = {}
    for key, value in values.items():
        if key in ("interval_sec", "sla_hours"):
            upper, lower = (604800, 60) if key == "interval_sec" else (8760, 1)
            if value is not None and (type(value) is not int or not lower <= value <= upper):
                raise ValueError("Invalid " + key)
        elif key in ("binary_enabled", "export_enabled", "notify_telegram", "notify_email", "maintenance_override"):
            if value is not None and type(value) is not bool:
                raise ValueError("Invalid " + key)
        else:
            raise ValueError("Unknown policy field: " + key)
        if value is not None:
            clean[key] = value
    return clean

