
import httpx
from django.conf import settings
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from pydantic import ValidationError

from api.helpers import (
    ApiError,
    error_response,
    get_current_user,
    json_response,
    parse_json_body,
    require_permission,
)
from core.models import User
from services import auth, ldap_settings, scan_job
from services.audit import (
    ACTION_AUTH_LOGIN,
    ACTION_AUTH_LOGIN_FAILED,
    ACTION_AUTH_LOGIN_LDAP,
    ACTION_COMPLIANCE_EXPORT,
    ACTION_COMPLIANCE_REPORT_SEND,
    ACTION_CREDENTIAL_CREATE,
    ACTION_CREDENTIAL_DELETE,
    ACTION_CREDENTIAL_UPDATE,
    ACTION_MIKROTIK_RESTORE,
    ACTION_OXIDIZED_BACKUP_ALL,
    ACTION_OXIDIZED_FETCH,
    ACTION_SCAN_DISCOVER,
    ACTION_SCAN_RUN,
    ACTION_SETTINGS_UPDATE,
    ACTION_USER_SCOPE_UPDATE,
    audit_events_to_csv,
    list_audit_events,
    log_audit,
    log_audit_user,
)
from services.compliance import (
    compliance_to_csv,
    compliance_to_pdf,
    compute_compliance_by_site,
    compute_compliance_summary,
)
from services.inventory import (
    OXIDIZED_SOURCE_URL,
    add_credential_profile,
    add_device,
    bulk_update_devices,
    cleanup_discovered_devices,
    delete_credential_profile,
    devices_for_oxidized_source,
    load_inventory,
    mask_inventory_for_role,
    reimport_network_inventory,
    remove_device,
    save_inventory,
    update_credential_profile,
    update_oxidized_credentials,
)
from services.ldap_auth import auth_methods
from services.oxidized_client import (
    build_diff_proxy_path,
    build_version_view_proxy_path,
    build_versions_proxy_path,
    check_health,
    fetch_node,
    get_node_config,
    get_node_versions,
    get_nodes,
)
from services.oxidized_proxy import (
    embed_block_headers,
    hop_headers,
    oxidized_base_url,
    rewrite_proxy_body,
    rewrite_proxy_location,
    upstream_target,
)
from services.scan_history import get_scan_history, get_scan_trends
from services.schemas import (
    BackupNotifyTestRequest,
    BackupSettingsUpdate,
    BulkDeviceUpdate,
    ChangePasswordRequest,
    CredentialProfile,
    CredentialProfileCreate,
    CredentialProfileUpdate,
    Device,
    DeviceCreate,
    GitSettingsUpdate,
    GroupPolicyUpdate,
    Inventory,
    LdapConfigUpdate,
    LdapTestRequest,
    OxidizedSettingsUpdate,
    ScanJobStatus,
    ScanLogEntry,
    ScanSettingsUpdate,
    ScanStartResponse,
    MikrotikRestoreRequest,
    MikrotikBackupCompareRequest,
)

_HOP_HEADERS = hop_headers()
_EMBED_BLOCK_HEADERS = embed_block_headers()


def _node_access_denied(user: User, name: str):
    from services.object_scope import require_device_access

    try:
        require_device_access(user, name)
    except PermissionError as exc:
        return error_response(str(exc), status=403)
    return None


def _job_to_status(job: scan_job.ScanJob | None) -> ScanJobStatus:
    if not job:
        return ScanJobStatus(status="idle", phase="idle")
    return ScanJobStatus(
        job_id=job.id,
        status=job.status,
        phase=job.phase.value,
        message=job.message,
        discover=job.discover,
        progress_current=job.progress_current,
        progress_total=job.progress_total,
        progress_pct=job.progress_pct,
        started_at=job.started_at,
        finished_at=job.finished_at,
        summary=job.summary,
        error=job.error,
        logs=[
            ScanLogEntry(ts=e.ts, level=e.level, message=e.message) for e in job.logs
        ],
    )


def ui_page(request: HttpRequest) -> FileResponse:
    index_path = settings.BASE_DIR / "static" / "index.html"
    return FileResponse(index_path.open("rb"), content_type="text/html")


def ui_config(request: HttpRequest) -> JsonResponse:
    from services.database import is_database_available
    from services.git_settings import public_url

    engine = getattr(settings, "OXIDIZED_ENGINE", "python")
    return json_response(
        {
            "oxidized_public_url": public_url(),
            "oxidized_proxy_url": "/oxidized-proxy/nodes",
            "oxidized_engine": engine,
            "oxidized_engine_title": (
                "Python Oxidized" if engine == "python" else "Ruby Oxidized"
            ),
            "scanner_version": "1.0.0",
            "auth_required": True,
            "auth": auth_methods(),
            "database": "connected" if is_database_available() else "env-fallback",
            "database_url": settings.DATABASE_URL_DISPLAY,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def login_view(request: HttpRequest) -> JsonResponse:
    try:
        body = parse_json_body(request)
    except ApiError as exc:
        return error_response(exc.detail, exc.status)
    user = auth.authenticate_user(body.get("username", ""), body.get("password", ""))
    if not user:
        log_audit(
            str(body.get("username", "")).strip()[:64],
            ACTION_AUTH_LOGIN_FAILED,
            request=request,
        )
        return error_response("Неверный логин или пароль", status=401)

    login_action = ACTION_AUTH_LOGIN_LDAP if (user.auth_source or "") == "ldap" else ACTION_AUTH_LOGIN
    log_audit_user(user, login_action, request=request)

    token = auth.create_access_token(user.id, user.username, user.role)
    response = json_response(
        {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "permissions": auth.permissions_for_role(user.role),
                "must_change_password": bool(getattr(user, "must_change_password", False)),
            },
        }
    )
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="Lax",
        secure=getattr(settings, "BEHIND_HTTPS_PROXY", False),
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    return response


@csrf_exempt
@require_http_methods(["POST"])
def change_password_view(request: HttpRequest) -> JsonResponse:
    try:
        user = get_current_user(request)
    except ApiError as exc:
        return error_response(exc.detail, exc.status)
    try:
        body = parse_json_body(request)
        payload = ChangePasswordRequest.model_validate(body)
        auth.change_password(user, payload.current_password, payload.new_password)
    except ApiError as exc:
        return error_response(exc.detail, exc.status)
    except ValidationError as exc:
        return error_response(str(exc))
    except ValueError as exc:
        return error_response(str(exc), status=400)
    return json_response({"ok": True, "must_change_password": False})


@csrf_exempt
@require_http_methods(["POST"])
def logout_view(request: HttpRequest) -> JsonResponse:
    response = json_response({"status": "ok"})
    response.delete_cookie(key=settings.AUTH_COOKIE_NAME, path="/")
    return response


@require_permission(auth.PERMISSION_VIEW_INVENTORY)
def auth_me(request: HttpRequest) -> JsonResponse:
    user: User = request.api_user
    from services.object_scope import scope_public

    return json_response(
        {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "permissions": auth.permissions_for_role(user.role),
            "auth_source": user.auth_source or "local",
            "role_locked": bool(getattr(user, "role_locked", False)),
            "must_change_password": bool(getattr(user, "must_change_password", False)),
            **scope_public(user),
        }
    )


@require_permission(auth.PERMISSION_VIEW_INVENTORY)
def rbac_matrix_view(request: HttpRequest) -> JsonResponse:
    from services.rbac import rbac_matrix

    return json_response(rbac_matrix())


def _auth_users_list(request: HttpRequest) -> JsonResponse:
    from services.object_scope import scope_public

    users = [
        {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "is_active": u.is_active,
            "auth_source": u.auth_source or "local",
            "role_locked": bool(getattr(u, "role_locked", False)),
            **scope_public(u),
        }
        for u in auth.list_users()
    ]
    return json_response(users)


@csrf_exempt
@require_permission(auth.PERMISSION_MANAGE_USERS)
def auth_users_dispatch(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return _auth_users_list(request)
    if request.method == "POST":
        body = parse_json_body(request)
        try:
            created = auth.create_user(
                body.get("username", ""),
                body.get("password", ""),
                body.get("role", "viewer"),
            )
        except ValueError as exc:
            return error_response(str(exc))
        return json_response(
            {
                "id": created.id,
                "username": created.username,
                "role": created.role,
                "is_active": created.is_active,
                "auth_source": created.auth_source or "local",
            }
        )
    return error_response("Method not allowed", status=405)


@csrf_exempt
@require_permission(auth.PERMISSION_MANAGE_USERS)
def auth_user_detail(request: HttpRequest, user_id: int) -> JsonResponse:
    if request.method == "PUT":
        body = parse_json_body(request)
        try:
            updated = auth.update_user(
                user_id,
                role=body.get("role"),
                is_active=body.get("is_active"),
                password=body.get("password"),
                role_locked=body.get("role_locked"),
                allowed_groups=body.get("allowed_groups"),
                allowed_sites=body.get("allowed_sites"),
            )
        except ValueError as exc:
            return error_response(
                str(exc), status=404 if "не найден" in str(exc) else 400
            )
        if "allowed_groups" in body or "allowed_sites" in body:
            from services.object_scope import scope_public as _scope_public

            sp = _scope_public(updated)
            log_audit_user(
                request.api_user,
                ACTION_USER_SCOPE_UPDATE,
                target=updated.username,
                detail=(
                    f"groups={sp.get('allowed_groups') or 'all'}, "
                    f"sites={sp.get('allowed_sites') or 'all'}"
                ),
                request=request,
            )
        from services.object_scope import scope_public

        return json_response(
            {
                "id": updated.id,
                "username": updated.username,
                "role": updated.role,
                "is_active": updated.is_active,
                "auth_source": updated.auth_source or "local",
                "role_locked": bool(getattr(updated, "role_locked", False)),
                **scope_public(updated),
            }
        )
    if request.method == "DELETE":
        user: User = request.api_user
        if user_id == user.id:
            return error_response("Нельзя удалить текущего пользователя")
        try:
            auth.delete_user(user_id)
        except ValueError as exc:
            return error_response(str(exc), status=404)
        return json_response({"status": "ok"})
    return error_response("Method not allowed", status=405)



@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_logs(request: HttpRequest) -> JsonResponse:
    try:
        max_lines = int(request.GET.get("lines", "500"))
    except ValueError:
        max_lines = 500
    search = request.GET.get("q", "")
    from services.oxidized_logs import tail_oxidized_log

    return json_response(tail_oxidized_log(max_lines=max_lines, search=search))


@require_permission(auth.PERMISSION_VIEW_INVENTORY)
def oxidized_models(request: HttpRequest) -> JsonResponse:
    from services.oxidized_config_loader import list_available_models

    return json_response({"models": list_available_models()})


@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_health(request: HttpRequest) -> JsonResponse:
    return json_response(check_health())


def oxidized_source(request: HttpRequest) -> JsonResponse:
    from services.git_settings import source_token

    token_expected = source_token()
    if token_expected:
        token = request.headers.get("X-Auth-Token", "")
        if token != token_expected:
            return error_response("Invalid X-Auth-Token", status=401)
    return json_response(devices_for_oxidized_source())


@csrf_exempt
@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_proxy(request: HttpRequest, path: str = "") -> HttpResponse:
    if getattr(settings, "OXIDIZED_ENGINE", "python").lower() == "python":
        from services.oxidized_web_ui import handle_python_ui

        return handle_python_ui(request, path)

    target = upstream_target(path, request.META.get("QUERY_STRING", ""))

    forward_headers = {
        key.replace("HTTP_", "").replace("_", "-").title(): value
        for key, value in request.META.items()
        if key.startswith("HTTP_") and key.lower() not in ("http_host", "http_connection")
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            upstream = client.request(
                request.method,
                f"{oxidized_base_url()}{target}",
                headers=forward_headers,
                content=request.body,
            )
    except httpx.ConnectError:
        return error_response("Oxidized недоступен", status=503)
    except httpx.TimeoutException:
        return error_response("Таймаут Oxidized", status=504)

    content_type = upstream.headers.get("content-type", "")
    body = rewrite_proxy_body(upstream.content, content_type)

    response = HttpResponse(body, status=upstream.status_code)
    for key, value in upstream.headers.items():
        lower = key.lower()
        if lower in _HOP_HEADERS or lower in _EMBED_BLOCK_HEADERS:
            continue
        if lower == "content-length":
            continue
        if lower == "location":
            value = rewrite_proxy_location(value)
        response[key] = value
    if content_type:
        response["Content-Type"] = content_type
    return response


@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_nodes(request: HttpRequest) -> JsonResponse:
    from services.object_scope import filter_node_dicts

    user: User = request.api_user
    nodes, err = get_nodes()
    if err:
        return error_response(err, status=503)
    return json_response(filter_node_dicts(user, nodes or []))


@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_node_show(request: HttpRequest, name: str) -> JsonResponse:
    denied = _node_access_denied(request.api_user, name)
    if denied:
        return denied
    data, err = get_node_config(name)
    if err:
        return error_response(err, status=503)
    if data is None:
        return error_response(f"Node '{name}' not found", status=404)
    return json_response(data)


def _parse_version_epoch(raw_time) -> int:
    if raw_time is None:
        return 0
    if isinstance(raw_time, (int, float)):
        return int(raw_time)
    text = str(raw_time).strip()
    if not text:
        return 0
    from datetime import datetime

    normalized = text.replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(normalized).timestamp())
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%d %H:%M:%S",
        "%a, %d %b %Y %H:%M:%S %z",
    ):
        try:
            return int(datetime.strptime(text, fmt).timestamp())
        except ValueError:
            continue
    return 0


def _browser_prefers_html(request: HttpRequest) -> bool:
    accept = request.headers.get("Accept", "")
    if not accept:
        return False
    parts = [p.strip().split(";")[0] for p in accept.split(",") if p.strip()]
    if parts and parts[0] == "*/*":
        return False
    if parts and parts[0] == "application/json":
        return False
    return "text/html" in parts


@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_node_versions(request: HttpRequest, name: str) -> HttpResponse:
    denied = _node_access_denied(request.api_user, name)
    if denied:
        return denied
    data, err = get_node_versions(name)
    if err:
        status = 404 if "не найден" in err.lower() else 503
        return error_response(err, status=status)
    if _browser_prefers_html(request):
        from django.shortcuts import redirect

        return redirect(
            build_versions_proxy_path(data["node"], data.get("group") or "")
        )
    versions = data.get("versions") or []
    enriched = []
    total = len(versions)
    for idx, item in enumerate(versions):
        num = total - idx
        raw_time = item.get("time")
        epoch = _parse_version_epoch(raw_time)
        enriched.append(
            {
                "oid": item.get("oid"),
                "time": raw_time,
                "epoch": epoch,
                "num": num,
                "view_url": build_version_view_proxy_path(
                    data["node"], data.get("group") or "", item.get("oid", ""), epoch, num
                ),
                "diff_url": build_diff_proxy_path(
                    data["node"], data.get("group") or "", item.get("oid", ""), epoch, num
                )
                if idx < total - 1
                else None,
            }
        )
    return json_response(
        {
            "node": data["node"],
            "group": data.get("group") or "",
            "node_full": data.get("node_full"),
            "versions_proxy_url": build_versions_proxy_path(
                data["node"], data.get("group") or ""
            ),
            "versions": enriched,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_OXIDIZED_WRITE)
def oxidized_node_fetch(request: HttpRequest, name: str) -> JsonResponse:
    denied = _node_access_denied(request.api_user, name)
    if denied:
        return denied
    data, err = fetch_node(name)
    if err:
        return error_response(err, status=503)
    log_audit_user(request.api_user, ACTION_OXIDIZED_FETCH, target=name, request=request)
    return json_response({"status": "ok", "name": name, "result": data})


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_OXIDIZED_WRITE)
def oxidized_backup_all(request: HttpRequest) -> JsonResponse:
    if getattr(settings, "OXIDIZED_ENGINE", "python").lower() != "python":
        return error_response("Доступно только для python engine", status=501)
    from services.object_scope import filter_node_dicts, has_object_scope
    from services.oxidized_engine import get_manager

    user: User = request.api_user
    manager = get_manager()
    only_names = None
    if has_object_scope(user):
        allowed = filter_node_dicts(user, manager.list_nodes())
        only_names = {n.get("name") for n in allowed if n.get("name")}
    result = manager.backup_all(only_names=only_names)
    log_audit_user(
        request.api_user,
        ACTION_OXIDIZED_BACKUP_ALL,
        detail=f"queued={result.get('queued', 0)}",
        request=request,
    )
    return json_response({"status": "ok", **result})


@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_node_backups(request: HttpRequest, name: str) -> JsonResponse:
    denied = _node_access_denied(request.api_user, name)
    if denied:
        return denied
    from services.mikrotik_backup import MikrotikBackup, MikrotikBackupError, device_file_prefix

    try:
        files = MikrotikBackup().list_files(name)
    except MikrotikBackupError as exc:
        return error_response(str(exc), status=400)
    return json_response(
        {
            "name": name,
            "backups": files,
            "prefix": device_file_prefix(name),
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_OXIDIZED_WRITE)
def oxidized_node_backups_run(request: HttpRequest, name: str) -> JsonResponse:
    denied = _node_access_denied(request.api_user, name)
    if denied:
        return denied
    from services.audit import ACTION_OXIDIZED_FETCH, log_audit_user
    from services.mikrotik_backup import MikrotikBackupError, run_mikrotik_backup_by_name

    try:
        files = run_mikrotik_backup_by_name(name)
    except MikrotikBackupError as exc:
        return error_response(str(exc), status=400)
    log_audit_user(
        request.api_user,
        ACTION_OXIDIZED_FETCH,
        target=name,
        detail="mikrotik_backup",
        request=request,
    )
    return json_response({"status": "ok", "name": name, "backups": files})


@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_node_backup_download(request: HttpRequest, name: str) -> HttpResponse:
    denied = _node_access_denied(request.api_user, name)
    if denied:
        return denied
    from services.mikrotik_backup import MikrotikBackup, MikrotikBackupError

    backup_type = (request.GET.get("type") or "bin").lower()
    filename = request.GET.get("file", "")
    if backup_type not in ("bin", "rsc"):
        return error_response("type must be bin or rsc", status=400)
    if not filename:
        return error_response("file required", status=400)
    try:
        path = MikrotikBackup().resolve_download(name, backup_type, filename)
    except MikrotikBackupError as exc:
        return error_response(str(exc), status=404)
    content_type = "application/octet-stream"
    if filename.endswith(".rsc"):
        content_type = "text/plain; charset=utf-8"
    return FileResponse(path.open("rb"), as_attachment=True, filename=path.name, content_type=content_type)


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_OXIDIZED_WRITE)
def oxidized_node_backups_restore(request: HttpRequest, name: str) -> JsonResponse:
    denied = _node_access_denied(request.api_user, name)
    if denied:
        return denied
    from services.mikrotik_backup import MikrotikBackupError
    from services.mikrotik_restore import restore_mikrotik_backup

    try:
        body = parse_json_body(request)
        payload = MikrotikRestoreRequest.model_validate(body)
        result = restore_mikrotik_backup(name, payload.type, payload.file)
    except ValidationError as exc:
        return error_response(str(exc))
    except MikrotikBackupError as exc:
        return error_response(str(exc), status=400)
    except Exception as exc:
        from services.oxidized_engine.exceptions import NodeNotFound

        if isinstance(exc, NodeNotFound):
            return error_response(str(exc), status=404)
        raise
    log_audit_user(
        request.api_user,
        ACTION_MIKROTIK_RESTORE,
        target=name,
        detail=f"{payload.type}:{payload.file}",
        request=request,
    )
    return json_response(result)


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_node_backups_compare(request: HttpRequest, name: str) -> JsonResponse:
    denied = _node_access_denied(request.api_user, name)
    if denied:
        return denied
    from services.mikrotik_backup import MikrotikBackupError
    from services.mikrotik_restore import compare_backup_files

    try:
        body = parse_json_body(request)
        payload = MikrotikBackupCompareRequest.model_validate(body)
        result = compare_backup_files(name, payload.file_a, payload.file_b, payload.type)
    except ValidationError as exc:
        return error_response(str(exc))
    except MikrotikBackupError as exc:
        return error_response(str(exc), status=400)
    return json_response(result)


@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_node_version_view(request: HttpRequest, name: str, oid: str) -> HttpResponse:
    denied = _node_access_denied(request.api_user, name)
    if denied:
        return denied
    if getattr(settings, "OXIDIZED_ENGINE", "python").lower() != "python":
        return error_response("Доступно только для python engine", status=501)
    from services.oxidized_engine import get_manager
    from services.oxidized_engine.exceptions import NodeNotFound

    try:
        text = get_manager().get_version(name, oid)
    except NodeNotFound:
        return error_response(f"Node '{name}' not found", status=404)
    if text == "version not found":
        return error_response("version not found", status=404)
    return HttpResponse(text, content_type="text/plain; charset=utf-8")


@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_node_diff(request: HttpRequest, name: str) -> HttpResponse:
    denied = _node_access_denied(request.api_user, name)
    if denied:
        return denied
    if getattr(settings, "OXIDIZED_ENGINE", "python").lower() != "python":
        return error_response("Доступно только для python engine", status=501)
    from services.git_diff_html import render_git_diff_html, render_side_by_side_html
    from services.oxidized_engine import get_manager
    from services.oxidized_engine.exceptions import NodeNotFound

    oid = request.GET.get("oid", "")
    oid2 = request.GET.get("oid2") or None
    if not oid:
        return error_response("oid required", status=400)
    try:
        diff = get_manager().get_diff(name, oid, oid2)
    except NodeNotFound:
        return error_response(f"Node '{name}' not found", status=404)

    fmt = (request.GET.get("format") or "html").lower()
    patch = str(diff.get("patch") or "")
    if fmt == "json":
        return json_response(diff)
    if fmt == "text":
        return HttpResponse(patch, content_type="text/plain; charset=utf-8")
    if fmt == "side_by_side":
        if not oid2:
            return error_response("oid2 required for side_by_side", status=400)
        try:
            mgr = get_manager()
            old_text = mgr.get_version(name, oid2)
            new_text = mgr.get_version(name, oid)
        except NodeNotFound:
            return error_response(f"Node '{name}' not found", status=404)
        if old_text == "version not found" or new_text == "version not found":
            return error_response("version not found", status=404)
        html_body = render_side_by_side_html(old_text, new_text, title=f"Diff {name}")
        return HttpResponse(html_body, content_type="text/html; charset=utf-8")
    html_body = render_git_diff_html(
        patch,
        title=f"Diff {name}",
        stat=diff.get("stat"),
    )
    return HttpResponse(html_body, content_type="text/html; charset=utf-8")


def health(request: HttpRequest) -> JsonResponse:
    from services.database import is_database_available

    inventory = load_inventory()
    summary, last_scan_at = scan_job.get_last_scan()
    if summary is None:
        from services.scan_history import get_last_scan_from_db

        summary, last_scan_at = get_last_scan_from_db()
    payload = {
        "status": "ok",
        "database": "connected" if is_database_available() else "env-fallback",
        "inventory_devices": len(inventory.devices),
        "networks": len(inventory.networks),
        "last_scan": last_scan_at,
    }
    if summary:
        payload["scan_online"] = summary.online
        payload["scan_offline"] = summary.offline
        payload["scan_partial"] = summary.partial
    return json_response(payload)


def health_ready(request: HttpRequest) -> JsonResponse:
    from services.database import is_database_available

    checks: dict[str, object] = {"database": False, "oxidized_worker": False}
    try:
        checks["database"] = is_database_available()
    except Exception as exc:
        checks["database_error"] = str(exc)

    try:
        ox = check_health()
        checks["oxidized_worker"] = bool(ox.get("reachable"))
        checks["oxidized_engine"] = ox.get("engine")
        checks["oxidized_nodes"] = ox.get("nodes_count", 0)
        if not ox.get("reachable"):
            checks["oxidized_error"] = ox.get("error")
    except Exception as exc:
        checks["oxidized_error"] = str(exc)

    ready = bool(checks["database"]) and bool(checks["oxidized_worker"])
    status_code = 200 if ready else 503
    return json_response({"status": "ready" if ready else "not_ready", "checks": checks}, status=status_code)


def metrics_view(request: HttpRequest) -> HttpResponse:
    if not getattr(settings, "METRICS_ENABLED", True):
        return HttpResponse("metrics disabled", status=404)
    from services.metrics import metrics_response, refresh_all_gauges

    refresh_all_gauges()
    body, content_type = metrics_response()
    return HttpResponse(body, content_type=content_type)


@csrf_exempt
def inventory_dispatch(request: HttpRequest) -> JsonResponse:
    try:
        user = get_current_user(request)
    except ApiError as exc:
        return error_response(exc.detail, exc.status)

    if request.method == "GET":
        if not auth.user_has_permission(user, auth.PERMISSION_VIEW_INVENTORY):
            return error_response("Недостаточно прав", status=403)
        return json_response(mask_inventory_for_role(load_inventory(), user.role, user=user))
    if request.method == "PUT":
        if not auth.user_has_permission(user, auth.PERMISSION_EDIT_INVENTORY):
            return error_response("Недостаточно прав", status=403)
        body = parse_json_body(request)
        inventory = Inventory.model_validate(body)
        save_inventory(inventory)
        update_oxidized_credentials(inventory)
        return json_response(mask_inventory_for_role(inventory, user.role, user=user))
    return error_response("Method not allowed", status=405)


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_EDIT_DEVICES)
def bulk_update_devices_view(request: HttpRequest) -> JsonResponse:
    user: User = request.api_user
    try:
        body = parse_json_body(request)
        payload = BulkDeviceUpdate.model_validate(body)
    except ApiError as exc:
        return error_response(exc.detail, exc.status)
    except ValidationError as exc:
        return error_response(str(exc))

    from services.object_scope import device_in_scope

    inventory = load_inventory()
    device_map = {d.name: d for d in inventory.devices}
    for name in payload.names:
        device = device_map.get(name)
        if not device:
            return error_response(f"Device '{name}' not found", status=404)
        if not device_in_scope(user, device):
            return error_response(f"Нет доступа к устройству {name}", status=403)

    try:
        updated = bulk_update_devices(
            payload.names,
            enabled=payload.enabled,
            maintenance=payload.maintenance,
            group=payload.group,
        )
    except ValueError as exc:
        return error_response(str(exc), status=400)
    return json_response(mask_inventory_for_role(updated, user.role, user=user))


@csrf_exempt
@require_permission(auth.PERMISSION_EDIT_DEVICES)
def inventory_devices_dispatch(request: HttpRequest) -> JsonResponse:
    user: User = request.api_user
    if request.method == "POST":
        body = parse_json_body(request)
        device = DeviceCreate.model_validate(body)
        inventory = add_device(Device(**device.model_dump()))
        return json_response(mask_inventory_for_role(inventory, user.role, user=user))
    return error_response("Method not allowed", status=405)


@csrf_exempt
@require_http_methods(["DELETE"])
@require_permission(auth.PERMISSION_EDIT_DEVICES)
def delete_device_view(request: HttpRequest, name: str) -> JsonResponse:
    user: User = request.api_user
    inventory = load_inventory()
    if not any(d.name == name for d in inventory.devices):
        return error_response(f"Device '{name}' not found", status=404)
    inventory = remove_device(name)
    return json_response(mask_inventory_for_role(inventory, user.role, user=user))


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_EDIT_CREDENTIALS)
def create_credential_profile_view(request: HttpRequest) -> JsonResponse:
    user: User = request.api_user
    body = parse_json_body(request)
    profile = CredentialProfileCreate.model_validate(body)
    try:
        inventory = add_credential_profile(
            CredentialProfile(
                name=profile.name,
                group_name=profile.group_name,
                username=profile.username,
                password=profile.password,
            )
        )
        if profile.model:
            from services.oxidized_settings import set_group_model

            set_group_model(profile.group_name, profile.model)
            inventory = load_inventory()
    except ValueError as exc:
        return error_response(str(exc))
    update_oxidized_credentials(inventory)
    log_audit_user(
        request.api_user,
        ACTION_CREDENTIAL_CREATE,
        target=profile.name,
        detail=f"group={profile.group_name}",
        request=request,
    )
    return json_response(mask_inventory_for_role(inventory, user.role, user=user), status=201)


@csrf_exempt
@require_permission(auth.PERMISSION_EDIT_CREDENTIALS)
def credential_profile_detail_view(request: HttpRequest, name: str) -> JsonResponse:
    user: User = request.api_user
    if request.method == "PUT":
        body = parse_json_body(request)
        creds = CredentialProfileUpdate.model_validate(body)
        try:
            inventory = update_credential_profile(name, creds)
        except ValueError as exc:
            return error_response(str(exc), status=404)
        update_oxidized_credentials(inventory)
        log_audit_user(
            request.api_user,
            ACTION_CREDENTIAL_UPDATE,
            target=name,
            request=request,
        )
        return json_response(mask_inventory_for_role(inventory, user.role, user=user))
    if request.method == "DELETE":
        try:
            inventory = delete_credential_profile(name)
        except ValueError as exc:
            status = 404 if "не найден" in str(exc).lower() or "not found" in str(exc).lower() else 400
            return error_response(str(exc), status=status)
        update_oxidized_credentials(inventory)
        log_audit_user(
            request.api_user,
            ACTION_CREDENTIAL_DELETE,
            target=name,
            request=request,
        )
        return json_response(mask_inventory_for_role(inventory, user.role, user=user))
    return error_response("Method not allowed", status=405)


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_EDIT_INVENTORY)
def import_network_inventory_view(request: HttpRequest) -> JsonResponse:
    user: User = request.api_user
    try:
        inventory = reimport_network_inventory()
    except FileNotFoundError as exc:
        return error_response(str(exc), status=404)
    update_oxidized_credentials(inventory)
    return json_response(mask_inventory_for_role(inventory, user.role, user=user))


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_RUN_SCAN)
def scan_inventory_view(request: HttpRequest) -> JsonResponse:
    discover = request.GET.get("discover", "").lower() in ("1", "true", "yes")
    job = scan_job.start_scan(discover=discover)
    log_audit_user(
        request.api_user,
        ACTION_SCAN_DISCOVER if discover else ACTION_SCAN_RUN,
        detail=f"job_id={job.id}",
        request=request,
    )
    return json_response(
        ScanStartResponse(job_id=job.id, status=job.status, discover=job.discover),
        status=202,
    )


@require_permission(auth.PERMISSION_VIEW_INVENTORY)
def scan_status_view(request: HttpRequest) -> JsonResponse:
    return json_response(_job_to_status(scan_job.get_current_job()))


@require_permission(auth.PERMISSION_VIEW_INVENTORY)
def get_latest_scan_view(request: HttpRequest) -> JsonResponse:
    summary, _ = scan_job.get_last_scan()
    if summary is None:
        from services.scan_history import get_last_scan_from_db

        summary, _ = get_last_scan_from_db()
    return json_response(summary)


@require_permission(auth.PERMISSION_COMPLIANCE_READ)
def compliance_summary_view(request: HttpRequest) -> JsonResponse:
    critical = request.GET.get("critical") or None
    if critical == "":
        critical = None
    user: User = request.api_user
    return json_response(
        compute_compliance_summary(
            site=request.GET.get("site", "").strip(),
            role=request.GET.get("role", "").strip(),
            critical=critical,
            group=request.GET.get("group", "").strip(),
            state=request.GET.get("state", "").strip(),
            user=user,
        )
    )


@require_permission(auth.PERMISSION_COMPLIANCE_READ)
def compliance_export_view(request: HttpRequest) -> HttpResponse:
    critical = request.GET.get("critical") or None
    user: User = request.api_user
    summary = compute_compliance_summary(
        site=request.GET.get("site", "").strip(),
        role=request.GET.get("role", "").strip(),
        critical=critical,
        group=request.GET.get("group", "").strip(),
        state=request.GET.get("state", "").strip(),
        user=user,
    )
    fmt = (request.GET.get("format") or "csv").lower()
    stamp = summary["generated_at"].strftime("%Y%m%d-%H%M%S")
    if fmt == "pdf":
        pdf_bytes = bytes(compliance_to_pdf(summary))
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="compliance-{stamp}.pdf"'
    else:
        csv_text = compliance_to_csv(summary)
        response = HttpResponse(csv_text, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="compliance-{stamp}.csv"'
    log_audit_user(
        user,
        ACTION_COMPLIANCE_EXPORT,
        target=fmt,
        detail=f"compliance_pct={summary.get('compliance_pct', 0)}",
        request=request,
    )
    return response


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_VIEW_INVENTORY)
def compliance_report_send_view(request: HttpRequest) -> JsonResponse:
    from services.compliance_report import send_scoped_compliance_report

    user: User = request.api_user
    critical = request.GET.get("critical") or None
    result = send_scoped_compliance_report(
        user,
        site=request.GET.get("site", "").strip(),
        role=request.GET.get("role", "").strip(),
        critical=critical,
        group=request.GET.get("group", "").strip(),
        state=request.GET.get("state", "").strip(),
    )
    log_audit_user(
        user,
        ACTION_COMPLIANCE_REPORT_SEND,
        detail=f"ok={result.get('ok')}",
        request=request,
    )
    status = 200 if result.get("ok") else 400
    return json_response(result, status=status)


@require_permission(auth.PERMISSION_VIEW_INVENTORY)
def scan_history_view(request: HttpRequest) -> JsonResponse:
    try:
        limit = int(request.GET.get("limit", "50"))
    except ValueError:
        limit = 50
    try:
        days = int(request.GET.get("days", "30"))
    except ValueError:
        days = 30
    return json_response(get_scan_history(limit=limit, days=days))


@require_permission(auth.PERMISSION_VIEW_INVENTORY)
def scan_trends_view(request: HttpRequest) -> JsonResponse:
    try:
        days = int(request.GET.get("days", "30"))
    except ValueError:
        days = 30
    return json_response(get_scan_trends(days=days))


@require_permission(auth.PERMISSION_AUDIT_READ)
def audit_events_view(request: HttpRequest) -> JsonResponse:
    try:
        limit = int(request.GET.get("limit", "100"))
    except ValueError:
        limit = 100
    try:
        offset = int(request.GET.get("offset", "0"))
    except ValueError:
        offset = 0
    action = request.GET.get("action", "").strip()
    return json_response(list_audit_events(limit=limit, offset=offset, action=action))


@require_permission(auth.PERMISSION_AUDIT_READ)
def audit_export_view(request: HttpRequest) -> HttpResponse:
    try:
        limit = int(request.GET.get("limit", "10000"))
    except ValueError:
        limit = 10000
    action = request.GET.get("action", "").strip()
    csv_text = audit_events_to_csv(limit=limit, action=action)
    response = HttpResponse(csv_text, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="audit-export.csv"'
    log_audit_user(request.api_user, "audit.export", target=action or "all", request=request)
    return response


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_OXIDIZED_WRITE)
def sync_oxidized_view(request: HttpRequest) -> JsonResponse:
    inventory = load_inventory()
    reload_info = update_oxidized_credentials(inventory)
    from django.conf import settings

    engine = getattr(settings, "OXIDIZED_ENGINE", "python")
    return json_response(
        {
            "status": "ok",
            "engine": engine,
            "engine_title": (
                "Python Oxidized" if engine == "python" else "Ruby Oxidized"
            ),
            "source": "inventory",
            "source_url": OXIDIZED_SOURCE_URL,
            "devices_count": len(inventory.devices),
            "enabled_count": sum(1 for d in inventory.devices if d.enabled),
            **reload_info,
        }
    )


@csrf_exempt
def oxidized_settings_dispatch(request: HttpRequest) -> JsonResponse:
    from services import oxidized_settings

    try:
        user = get_current_user(request)
    except ApiError as exc:
        return error_response(exc.detail, exc.status)

    if request.method == "GET":
        if not auth.user_has_permission(user, auth.PERMISSION_OXIDIZED_READ):
            return error_response("Недостаточно прав", status=403)
        return json_response(oxidized_settings.get_oxidized_settings())
    if request.method == "PUT":
        if not auth.user_has_permission(user, auth.PERMISSION_OXIDIZED_WRITE):
            return error_response("Недостаточно прав", status=403)
        try:
            body = parse_json_body(request)
            payload = OxidizedSettingsUpdate.model_validate(body)
            saved = oxidized_settings.save_oxidized_settings(payload.model_dump())
        except ValidationError as exc:
            return error_response(str(exc))
        except ValueError as exc:
            return error_response(str(exc))
        log_audit_user(user, ACTION_SETTINGS_UPDATE, target="oxidized", request=request)
        return json_response(saved)
    return error_response("Method not allowed", status=405)


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_EDIT_INVENTORY)
def cleanup_discovered_devices_view(request: HttpRequest) -> JsonResponse:
    user: User = request.api_user
    deleted, inventory = cleanup_discovered_devices()
    update_oxidized_credentials(inventory)
    return json_response(
        {
            "status": "ok",
            "deleted": deleted,
            "message": f"Удалено устройств discovery: {deleted}",
            "inventory": mask_inventory_for_role(inventory, user.role, user=user),
        }
    )


@csrf_exempt
def backup_settings_dispatch(request: HttpRequest) -> JsonResponse:
    from services import backup_settings

    try:
        user = get_current_user(request)
    except ApiError as exc:
        return error_response(exc.detail, exc.status)

    if request.method == "GET":
        if not auth.user_has_permission(user, auth.PERMISSION_OXIDIZED_READ):
            return error_response("Недостаточно прав", status=403)
        return json_response(backup_settings.get_config_public())
    if request.method == "PUT":
        if not auth.user_has_permission(user, auth.PERMISSION_OXIDIZED_WRITE):
            return error_response("Недостаточно прав", status=403)
        try:
            body = parse_json_body(request)
            payload = BackupSettingsUpdate.model_validate(body)
            saved = backup_settings.save_config(payload.model_dump())
        except ValidationError as exc:
            return error_response(str(exc))
        except ValueError as exc:
            return error_response(str(exc))
        log_audit_user(user, ACTION_SETTINGS_UPDATE, target="backup", request=request)
        return json_response(saved)
    return error_response("Method not allowed", status=405)


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_SETTINGS_NOTIFY)
def backup_settings_test_notify(request: HttpRequest) -> JsonResponse:
    from services.backup_notifications import send_test_notification
    from services.backup_settings import PASSWORD_MASK

    try:
        body = parse_json_body(request)
        payload = BackupNotifyTestRequest.model_validate(body)
    except ValidationError as exc:
        return error_response(str(exc))
    kind = payload.kind.strip().lower()
    if kind not in ("error", "report", "degrade"):
        return error_response("kind must be error, report or degrade", status=400)

    overrides = payload.model_dump(exclude={"kind"}, exclude_none=True)
    for secret_field in ("telegram_token", "smtp_password"):
        if overrides.get(secret_field) == PASSWORD_MASK:
            overrides.pop(secret_field, None)
    result = send_test_notification(kind, overrides or None)
    return json_response(result)


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_OXIDIZED_WRITE)
def backup_settings_degrade_check(request: HttpRequest) -> JsonResponse:
    from services.degradation_monitor import run_degradation_check

    result = run_degradation_check()
    return json_response({"status": "ok", **result})


@csrf_exempt
@require_permission(auth.PERMISSION_MANAGE_USERS)
def ldap_settings_dispatch(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return json_response(ldap_settings.get_config_public())
    if request.method == "PUT":
        try:
            body = parse_json_body(request)
            payload = LdapConfigUpdate.model_validate(body)
            saved = ldap_settings.save_config(payload.model_dump())
        except ApiError as exc:
            return error_response(exc.detail, exc.status)
        except ValidationError as exc:
            return error_response(str(exc))
        except ValueError as exc:
            return error_response(str(exc))
        log_audit_user(request.api_user, ACTION_SETTINGS_UPDATE, target="ldap", request=request)
        return json_response(saved)
    return error_response("Method not allowed", status=405)


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_MANAGE_USERS)
def ldap_settings_test_view(request: HttpRequest) -> JsonResponse:
    try:
        body = parse_json_body(request)
        payload = LdapTestRequest.model_validate(body)
    except ApiError as exc:
        return error_response(exc.detail, exc.status)
    except ValidationError as exc:
        return error_response(str(exc))

    mode = payload.mode.strip().lower()
    if mode not in ("bind", "auth"):
        return error_response("mode должен быть bind или auth")

    result = ldap_settings.test_connection(
        mode=mode,
        username=payload.username,
        password=payload.password,
    )
    return json_response(result)


@csrf_exempt
def git_settings_dispatch(request: HttpRequest) -> JsonResponse:
    from services import git_settings

    try:
        user = get_current_user(request)
    except ApiError as exc:
        return error_response(exc.detail, exc.status)

    if request.method == "GET":
        if not auth.user_has_permission(user, auth.PERMISSION_OXIDIZED_READ):
            return error_response("Недостаточно прав", status=403)
        return json_response(git_settings.get_config_public())
    if request.method == "PUT":
        if not auth.user_has_permission(user, auth.PERMISSION_OXIDIZED_WRITE):
            return error_response("Недостаточно прав", status=403)
        try:
            body = parse_json_body(request)
            payload = GitSettingsUpdate.model_validate(body)
            saved = git_settings.save_config(payload.model_dump())
        except ValidationError as exc:
            return error_response(str(exc))
        except ValueError as exc:
            return error_response(str(exc))
        log_audit_user(user, ACTION_SETTINGS_UPDATE, target="git", request=request)
        return json_response(saved)
    return error_response("Method not allowed", status=405)


@csrf_exempt
def scan_settings_dispatch(request: HttpRequest) -> JsonResponse:
    from services import scan_settings

    try:
        user = get_current_user(request)
    except ApiError as exc:
        return error_response(exc.detail, exc.status)

    if request.method == "GET":
        if not auth.user_has_permission(user, auth.PERMISSION_VIEW_INVENTORY):
            return error_response("Недостаточно прав", status=403)
        return json_response(scan_settings.get_config_public())
    if request.method == "PUT":
        if not auth.user_has_permission(user, auth.PERMISSION_EDIT_INVENTORY):
            return error_response("Недостаточно прав", status=403)
        try:
            body = parse_json_body(request)
            payload = ScanSettingsUpdate.model_validate(body)
            saved = scan_settings.save_config(payload.model_dump())
        except ValidationError as exc:
            return error_response(str(exc))
        except ValueError as exc:
            return error_response(str(exc))
        log_audit_user(user, ACTION_SETTINGS_UPDATE, target="scan", request=request)
        return json_response(saved)
    return error_response("Method not allowed", status=405)


@csrf_exempt
def group_policies_dispatch(request: HttpRequest) -> JsonResponse:
    from services import group_policies

    try:
        user = get_current_user(request)
    except ApiError as exc:
        return error_response(exc.detail, exc.status)

    if request.method == "GET":
        if not auth.user_has_permission(user, auth.PERMISSION_OXIDIZED_READ):
            return error_response("Недостаточно прав", status=403)
        return json_response(
            {"policies": [group_policies.policy_to_public(p) for p in group_policies.list_policies()]}
        )
    if request.method == "PUT":
        if not auth.user_has_permission(user, auth.PERMISSION_OXIDIZED_WRITE):
            return error_response("Недостаточно прав", status=403)
        try:
            body = parse_json_body(request)
            payload = GroupPolicyUpdate.model_validate(body)
            saved = group_policies.save_policy(payload.model_dump())
        except ValidationError as exc:
            return error_response(str(exc))
        except ValueError as exc:
            return error_response(str(exc))
        return json_response(group_policies.policy_to_public(saved))
    return error_response("Method not allowed", status=405)


@csrf_exempt
@require_http_methods(["DELETE"])
@require_permission(auth.PERMISSION_OXIDIZED_WRITE)
def group_policy_delete(request: HttpRequest, group_name: str) -> JsonResponse:
    from services import group_policies

    if group_policies.delete_policy(group_name):
        return json_response({"status": "ok", "deleted": group_name})
    return error_response("Политика не найдена", status=404)


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_OXIDIZED_WRITE)
def compliance_report_test_view(request: HttpRequest) -> JsonResponse:
    from services.compliance_report import send_compliance_report

    return json_response(send_compliance_report(force=True))


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_MANAGE_USERS)
def backup_data_view(request: HttpRequest) -> JsonResponse:
    from services.backup_data import run_backup_data

    return json_response(run_backup_data())


@require_permission(auth.PERMISSION_COMPLIANCE_READ)
def compliance_by_site_view(request: HttpRequest) -> JsonResponse:
    user: User = request.api_user
    return json_response(compute_compliance_by_site(user=user))


def openapi_json_view(request: HttpRequest) -> JsonResponse:
    from services.openapi_spec import build_openapi_spec

    return json_response(build_openapi_spec())


def api_docs_view(request: HttpRequest) -> HttpResponse:
    html = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8"/>
  <title>Backup Tools API</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css"/>
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
  SwaggerUIBundle({ url: '/api/openapi.json', dom_id: '#swagger-ui' });
</script>
</body>
</html>"""
    return HttpResponse(html, content_type="text/html; charset=utf-8")


@csrf_exempt
@require_permission(auth.PERMISSION_API_KEYS_MANAGE)
def api_keys_dispatch(request: HttpRequest) -> JsonResponse:
    from services import api_keys
    from services.schemas import ApiKeyCreate

    user: User = request.api_user
    if request.method == "GET":
        return json_response({"items": api_keys.list_api_keys()})
    if request.method == "POST":
        try:
            body = parse_json_body(request)
            payload = ApiKeyCreate.model_validate(body)
            row, raw_key = api_keys.create_api_key(
                name=payload.name,
                role=payload.role,
                permissions=payload.permissions,
                allowed_groups=payload.allowed_groups,
                allowed_sites=payload.allowed_sites,
                created_by=user.username,
            )
        except ValidationError as exc:
            return error_response(str(exc))
        except ValueError as exc:
            return error_response(str(exc), status=400)
        result = api_keys._public_row(row)  # noqa: SLF001
        result["key"] = raw_key
        return json_response(result, status=201)
    return error_response("Method not allowed", status=405)


@csrf_exempt
@require_permission(auth.PERMISSION_API_KEYS_MANAGE)
def api_key_detail(request: HttpRequest, key_id: int) -> JsonResponse:
    from services import api_keys

    if request.method == "DELETE":
        try:
            api_keys.delete_api_key(key_id)
        except ValueError as exc:
            return error_response(str(exc), status=404)
        return json_response({"status": "ok"})
    return error_response("Method not allowed", status=405)


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_API_KEYS_MANAGE)
def api_key_revoke(request: HttpRequest, key_id: int) -> JsonResponse:
    from services import api_keys

    try:
        api_keys.revoke_api_key(key_id)
    except ValueError as exc:
        return error_response(str(exc), status=404)
    return json_response({"status": "ok"})

