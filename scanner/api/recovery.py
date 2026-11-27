from django.views.decorators.http import require_http_methods
from api.helpers import error_response, json_response, require_permission
from services import auth
from services.recovery import preflight
from services.mikrotik_backup import MikrotikBackupError


@require_http_methods(["GET"])
@require_permission(auth.PERMISSION_OXIDIZED_WRITE)
def restore_preflight(request, name):
    if request.api_user.role != "admin" or not request.api_user.pk:
        return error_response("Administrator required", status=403)
    try:
        return json_response(preflight(name, request.GET.get("type", ""), request.GET.get("file", ""), request.api_user.pk))
    except (MikrotikBackupError, OSError):
        return error_response("Restore preflight failed: verify device and registered artifact", status=409)
