from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from api.helpers import require_permission, parse_json_body, error_response, json_response, ApiError
from services import auth
from services.backup_jobs import create_job, query_jobs, public_job, cancel_job, effective_policy

@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_permission(auth.PERMISSION_OXIDIZED_READ)
def backup_jobs(request):
    user = request.api_user
    try:
        if request.method == "GET":
            try:
                limit = int(request.GET.get("limit","50"))
                before = int(request.GET["before"]) if "before" in request.GET else None
                if not 1 <= limit <= 100 or (before is not None and before < 1):
                    raise ValueError("Invalid pagination")
                result = query_jobs(user,name=request.GET.get("device",""),status=request.GET.get("status",""),kind=request.GET.get("kind",""),source=request.GET.get("source",""),before=before,limit=limit)
            except ValueError as exc:
                return error_response(str(exc),status=400)
            return json_response(result)
        if not auth.user_has_permission(user, auth.PERMISSION_OXIDIZED_WRITE):
            return error_response("Недостаточно прав", status=403)
        body = parse_json_body(request)
        if not isinstance(body, dict) or not isinstance(body.get("device"),str) or not isinstance(body.get("kind"),str):
            return error_response("Invalid payload", status=400)
        task = create_job(user, body["device"], body["kind"])
        from services.audit import log_audit_user, ACTION_OXIDIZED_FETCH
        log_audit_user(user, ACTION_OXIDIZED_FETCH, target=body["device"], detail=f"queued backup job={task.pk}", request=request)
        return json_response(public_job(task),status=202)
    except ApiError as exc:
        return error_response(exc.detail, status=exc.status)
    except PermissionError as exc:
        return error_response(str(exc),status=403)
    except ValueError as exc:
        return error_response(str(exc),status=409)
    except RuntimeError:
        return error_response("Task queue unavailable",status=503)

@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_OXIDIZED_WRITE)
def backup_job_cancel(request, job_id):
    try:
        task = cancel_job(request.api_user,job_id)
        from services.audit import log_audit_user, ACTION_OXIDIZED_FETCH
        log_audit_user(request.api_user,ACTION_OXIDIZED_FETCH,target=task.payload["device"],detail=f"cancelled backup job={task.pk}",request=request)
        return json_response(public_job(task))
    except PermissionError as exc:
        return error_response(str(exc),status=403)
    except ValueError as exc:
        return error_response(str(exc),status=409)

@require_http_methods(["GET"])
@require_permission(auth.PERMISSION_OXIDIZED_READ)
def backup_effective_policy(request):
    try:
        return json_response(effective_policy(request.api_user,request.GET.get("device","")))
    except PermissionError as exc:
        return error_response(str(exc),status=403)
