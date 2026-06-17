import os
import re
import logging

from contextlib import asynccontextmanager

from typing import Any, Optional



from fastapi import Depends, FastAPI, HTTPException, Request

from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from fastapi.staticfiles import StaticFiles



from .log_config import setup_logging

from .models import (
    Device,
    DeviceCreate,
    CredentialProfileUpdate,
    Inventory,
    ScanSummary,
    ScanStartResponse,
    ScanJobStatus,
    HealthResponse,
    LoginRequest,
    AuthUserResponse,
    UserPublic,
    UserCreate,
    UserUpdate,
)
from .inventory import (
    load_inventory,
    save_inventory,
    add_device,
    remove_device,
    update_credential_profile,
    reimport_network_inventory,
    update_oxidized_credentials,
    init_db,
    devices_for_oxidized_source,
    mask_inventory_for_role,
    OXIDIZED_SOURCE_URL,
)
from .auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    AUTH_COOKIE_NAME,
    authenticate_user,
    create_access_token,
    create_user,
    delete_user,
    get_current_user,
    list_users,
    permissions_for_role,
    require_permission,
    update_user,
    PERMISSION_EDIT_CREDENTIALS,
    PERMISSION_EDIT_DEVICES,
    PERMISSION_EDIT_INVENTORY,
    PERMISSION_MANAGE_USERS,
    PERMISSION_OXIDIZED_READ,
    PERMISSION_OXIDIZED_WRITE,
    PERMISSION_RUN_SCAN,
    PERMISSION_VIEW_INVENTORY,
)
from .db import User, get_session

from . import scan_job

import httpx

from .oxidized_client import (

    check_health,

    get_nodes,

    get_node_config,

    fetch_node,

    OXIDIZED_PUBLIC_URL,

    OXIDIZED_URL,

)



logger = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)
_EMBED_BLOCK_HEADERS = frozenset(
    {
        "x-frame-options",
        "content-security-policy",
        "content-security-policy-report-only",
    }
)

OXIDIZED_PROXY_PREFIX = "/oxidized-proxy"
_ROOT_ATTR_RE = re.compile(
    r"(?P<attr>href|src|action)\s*=\s*(?P<q>['\"])/(?P<rest>[^'\"]*)"
)
_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)/")


def _rewrite_proxy_location(location: str) -> str:
    location = location.strip()
    for base in (OXIDIZED_URL, OXIDIZED_PUBLIC_URL):
        if location.startswith(base):
            suffix = location[len(base):] or "/"
            if not suffix.startswith("/"):
                suffix = f"/{suffix}"
            return f"{OXIDIZED_PROXY_PREFIX}{suffix}"
    if location.startswith("/") and not location.startswith(OXIDIZED_PROXY_PREFIX):
        return f"{OXIDIZED_PROXY_PREFIX}{location}"
    return location


def _rewrite_proxy_body(content: bytes, content_type: str) -> bytes:
    if not content:
        return content
    ct = (content_type or "").lower()
    if not any(token in ct for token in ("html", "css", "javascript", "json")):
        return content
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    text = text.replace(f"{OXIDIZED_URL}/", f"{OXIDIZED_PROXY_PREFIX}/")
    text = text.replace(f"{OXIDIZED_PUBLIC_URL}/", f"{OXIDIZED_PROXY_PREFIX}/")
    if "html" in ct or "javascript" in ct:
        text = _ROOT_ATTR_RE.sub(
            lambda m: (
                f"{m.group('attr')}={m.group('q')}"
                f"{OXIDIZED_PROXY_PREFIX}/{m.group('rest')}"
            ),
            text,
        )
    if "css" in ct:
        text = _CSS_URL_RE.sub(f"url(\\1{OXIDIZED_PROXY_PREFIX}/", text)
    return text.encode("utf-8")



@asynccontextmanager

async def lifespan(app: FastAPI):

    setup_logging()
    logger.info("scanner | startup")

    init_db()

    inventory = load_inventory()

    update_oxidized_credentials(inventory)

    yield





app = FastAPI(

    title="Oxidized Inventory Scanner",

    description="Сканирование сети по инвентарю и синхронизация с Oxidized",

    version="1.0.0",

    lifespan=lifespan,

)



app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")





@app.get("/ui")

async def ui_page():

    return FileResponse(os.path.join(STATIC_DIR, "index.html"))





@app.get("/")

async def root():

    return RedirectResponse(url="/ui")





@app.get("/api/ui/config")

async def ui_config():

    return {

        "oxidized_public_url": OXIDIZED_PUBLIC_URL,

        "oxidized_proxy_url": "/oxidized-proxy/nodes",

        "scanner_version": "1.0.0",

        "auth_required": True,

    }


@app.post("/api/auth/login")
async def login(body: LoginRequest):
    with get_session() as session:
        user = authenticate_user(session, body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    token = create_access_token(user.id, user.username, user.role)
    payload = {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "permissions": permissions_for_role(user.role),
        },
    }
    response = JSONResponse(payload)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    return response


@app.post("/api/auth/logout")
async def logout():
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")
    return response


@app.get("/api/auth/me", response_model=AuthUserResponse)
async def auth_me(user: User = Depends(get_current_user)):
    return AuthUserResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        permissions=permissions_for_role(user.role),
    )


@app.get("/api/auth/users", response_model=list[UserPublic])
async def auth_users_list(
    user: User = Depends(require_permission(PERMISSION_MANAGE_USERS)),
):
    return [
        UserPublic(
            id=u.id,
            username=u.username,
            role=u.role,
            is_active=u.is_active,
        )
        for u in list_users()
    ]


@app.post("/api/auth/users", response_model=UserPublic)
async def auth_users_create(
    body: UserCreate,
    user: User = Depends(require_permission(PERMISSION_MANAGE_USERS)),
):
    try:
        created = create_user(body.username, body.password, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return UserPublic(
        id=created.id,
        username=created.username,
        role=created.role,
        is_active=created.is_active,
    )


@app.put("/api/auth/users/{user_id}", response_model=UserPublic)
async def auth_users_update(
    user_id: int,
    body: UserUpdate,
    user: User = Depends(require_permission(PERMISSION_MANAGE_USERS)),
):
    try:
        updated = update_user(
            user_id,
            role=body.role,
            is_active=body.is_active,
            password=body.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return UserPublic(
        id=updated.id,
        username=updated.username,
        role=updated.role,
        is_active=updated.is_active,
    )


@app.delete("/api/auth/users/{user_id}")
async def auth_users_delete(
    user_id: int,
    user: User = Depends(require_permission(PERMISSION_MANAGE_USERS)),
):
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить текущего пользователя")
    try:
        delete_user(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "ok"}



@app.get("/api/oxidized/health")

async def oxidized_health(
    user: User = Depends(require_permission(PERMISSION_OXIDIZED_READ)),
):

    return await check_health()


@app.get("/api/oxidized/source")
async def oxidized_source(request: Request):
    """HTTP source для Oxidized (формат LibreNMS oxidized API)."""
    from .inventory import OXIDIZED_SOURCE_TOKEN

    if OXIDIZED_SOURCE_TOKEN:
        token = request.headers.get("X-Auth-Token", "")
        if token != OXIDIZED_SOURCE_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid X-Auth-Token")

    return devices_for_oxidized_source()


@app.api_route(
    "/oxidized-proxy",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
@app.api_route(
    "/oxidized-proxy/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def oxidized_proxy(
    request: Request,
    path: str = "",
    user: User = Depends(require_permission(PERMISSION_OXIDIZED_READ)),
):
    """Proxy Oxidized Web UI for same-origin iframe (strips X-Frame-Options)."""
    target = f"/{path}" if path else "/"
    if request.url.query:
        target = f"{target}?{request.url.query}"

    forward_headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in ("host", "connection", "content-length")
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            upstream = await client.request(
                request.method,
                f"{OXIDIZED_URL}{target}",
                headers=forward_headers,
                content=await request.body(),
            )
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Oxidized недоступен")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Таймаут Oxidized")

    content_type = upstream.headers.get("content-type", "")
    body = _rewrite_proxy_body(upstream.content, content_type)

    out_headers: dict[str, str] = {}
    for key, value in upstream.headers.items():
        lower = key.lower()
        if lower in _HOP_HEADERS or lower in _EMBED_BLOCK_HEADERS:
            continue
        if lower == "content-length":
            continue
        if lower == "location":
            value = _rewrite_proxy_location(value)
        out_headers[key] = value

    return Response(
        content=body,
        status_code=upstream.status_code,
        headers=out_headers,
        media_type=content_type or None,
    )





@app.get("/api/oxidized/nodes")

async def oxidized_nodes(
    user: User = Depends(require_permission(PERMISSION_OXIDIZED_READ)),
):

    nodes, err = await get_nodes()

    if err:

        raise HTTPException(status_code=503, detail=err)

    return nodes





@app.get("/api/oxidized/nodes/{name}")

async def oxidized_node_show(
    name: str,
    user: User = Depends(require_permission(PERMISSION_OXIDIZED_READ)),
):

    data, err = await get_node_config(name)

    if err:

        raise HTTPException(status_code=503, detail=err)

    if data is None:

        raise HTTPException(status_code=404, detail=f"Node '{name}' not found")

    return data





@app.post("/api/oxidized/nodes/{name}/fetch")

async def oxidized_node_fetch(
    name: str,
    user: User = Depends(require_permission(PERMISSION_OXIDIZED_WRITE)),
):

    data, err = await fetch_node(name)

    if err:

        raise HTTPException(status_code=503, detail=err)

    return {"status": "ok", "name": name, "result": data}





@app.get("/health", response_model=HealthResponse)

async def health():

    inventory = load_inventory()

    return HealthResponse(

        status="ok",

        inventory_devices=len(inventory.devices),

        networks=len(inventory.networks),

        last_scan=scan_job.get_last_scan()[1],

    )





@app.get("/inventory", response_model=Inventory)

async def get_inventory(
    user: User = Depends(require_permission(PERMISSION_VIEW_INVENTORY)),
):

    return mask_inventory_for_role(load_inventory(), user.role)





@app.put("/inventory", response_model=Inventory)

async def put_inventory(
    inventory: Inventory,
    user: User = Depends(require_permission(PERMISSION_EDIT_INVENTORY)),
):

    save_inventory(inventory)

    update_oxidized_credentials(inventory)

    return mask_inventory_for_role(inventory, user.role)





@app.post("/inventory/devices", response_model=Inventory)

async def create_device(
    device: DeviceCreate,
    user: User = Depends(require_permission(PERMISSION_EDIT_DEVICES)),
):

    inventory = add_device(Device(**device.model_dump()))
    return mask_inventory_for_role(inventory, user.role)





@app.delete("/inventory/devices/{name}", response_model=Inventory)

async def delete_device(
    name: str,
    user: User = Depends(require_permission(PERMISSION_EDIT_DEVICES)),
):

    inventory = load_inventory()

    if not any(d.name == name for d in inventory.devices):

        raise HTTPException(status_code=404, detail=f"Device '{name}' not found")

    inventory = remove_device(name)
    return mask_inventory_for_role(inventory, user.role)





@app.put("/inventory/credentials/{name}", response_model=Inventory)
async def set_credential_profile(
    name: str,
    credentials: CredentialProfileUpdate,
    user: User = Depends(require_permission(PERMISSION_EDIT_CREDENTIALS)),
):
    try:
        inventory = update_credential_profile(name, credentials)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    update_oxidized_credentials(inventory)
    return mask_inventory_for_role(inventory, user.role)


@app.post("/inventory/import-network", response_model=Inventory)
async def import_network_inventory_endpoint(
    user: User = Depends(require_permission(PERMISSION_EDIT_INVENTORY)),
):
    try:
        inventory = reimport_network_inventory()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    update_oxidized_credentials(inventory)
    return mask_inventory_for_role(inventory, user.role)





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
    )


@app.post("/scan", response_model=ScanStartResponse, status_code=202)
async def scan_inventory(
    discover: bool = False,
    user: User = Depends(require_permission(PERMISSION_RUN_SCAN)),
):
    logger.info("api | scan request | discover=%s", discover)
    job = await scan_job.start_scan(discover=discover)
    return ScanStartResponse(
        job_id=job.id,
        status=job.status,
        discover=job.discover,
    )


@app.get("/scan/status", response_model=ScanJobStatus)
async def scan_status(
    user: User = Depends(require_permission(PERMISSION_VIEW_INVENTORY)),
):
    return _job_to_status(scan_job.get_current_job())


@app.get("/scan/latest", response_model=Optional[ScanSummary])
async def get_latest_scan(
    user: User = Depends(require_permission(PERMISSION_VIEW_INVENTORY)),
):
    summary, _ = scan_job.get_last_scan()
    return summary


@app.post("/oxidized/sync")

async def sync_oxidized(
    user: User = Depends(require_permission(PERMISSION_OXIDIZED_WRITE)),
):

    inventory = load_inventory()

    update_oxidized_credentials(inventory)

    return {

        "status": "ok",

        "source": "http",

        "source_url": OXIDIZED_SOURCE_URL,

        "devices_count": len(inventory.devices),

        "enabled_count": sum(1 for d in inventory.devices if d.enabled),

    }


