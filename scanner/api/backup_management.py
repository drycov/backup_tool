"""Administrative policy overrides and device-scoped change history."""
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from api.helpers import ApiError, error_response, json_response, parse_json_body, require_permission
from core.models import BackupPolicyOverride, ConfigChangeEvent, Device, Site
from services import auth
from services.object_scope import filter_devices
from services.policy_engine import validate_override


@csrf_exempt
@require_http_methods(["GET", "PUT"])
@require_permission(auth.PERMISSION_OXIDIZED_READ)
def policy_override(request):
    if request.api_user.role != "admin":
        return error_response("Administrator required", status=403)
    scope = request.GET.get("scope", "")
    target = request.GET.get("target", "")
    if scope not in ("site", "device") or not target:
        return error_response("Invalid policy target", status=400)
    exists = (Site.objects.filter(slug=target).exists() or Device.objects.filter(site=target).exists()) if scope == "site" else Device.objects.filter(name=target).exists()
    if not exists:
        return error_response("Target unavailable", status=404)
    if request.method == "PUT":
        if not auth.user_has_permission(request.api_user, auth.PERMISSION_OXIDIZED_WRITE):
            return error_response("Backup write required", status=403)
        try:
            values = validate_override(parse_json_body(request))
        except (ValueError, ApiError) as exc:
            return error_response(str(exc), status=400)
        if values:
            BackupPolicyOverride.objects.update_or_create(scope=scope, target=target, defaults={"values": values})
        else:
            BackupPolicyOverride.objects.filter(scope=scope, target=target).delete()
        from services.audit import log_audit_user

        log_audit_user(request.api_user, "backup.policy.update", target=scope + ":" + target, request=request)
    row = BackupPolicyOverride.objects.filter(scope=scope, target=target).first()
    return json_response({"scope": scope, "target": target, "values": row.values if row else {}})


@require_http_methods(["GET"])
@require_permission(auth.PERMISSION_OXIDIZED_READ)
def change_events(request):
    qs = ConfigChangeEvent.objects.filter(device_id__in=[d.pk for d in filter_devices(request.api_user, Device.objects.all())])
    name = request.GET.get("device", "")
    if name:
        qs = qs.filter(device__name=name)
    severity = request.GET.get("severity", "")
    if severity:
        if severity not in ("none", "low", "medium", "high", "critical"):
            return error_response("Invalid severity", status=400)
        qs = qs.filter(severity=severity)
    try:
        limit = int(request.GET.get("limit", "30"))
        before = int(request.GET.get("before", "0"))
        if not 1 <= limit <= 100 or before < 0:
            raise ValueError
    except ValueError:
        return error_response("Invalid pagination", status=400)
    if before:
        qs = qs.filter(pk__lt=before)
    rows = list(qs.order_by("-pk").values("id", "device__name", "commit_oid", "severity", "categories", "added", "removed", "created_at")[:limit+1])
    return json_response({"items": rows[:limit], "next_before": rows[limit-1]["id"] if len(rows)>limit else None})
