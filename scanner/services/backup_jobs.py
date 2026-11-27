"""Persistent manual backup jobs using the existing BackgroundTask worker."""
from django.db import transaction
from django.conf import settings
from core.models import BackgroundTask, Device, User
from services import auth
from services.object_scope import device_in_scope
from services.task_queue import enqueue

TASK = "backup.manual"

def permitted_device(user, name, kind):
    if not user or not user.is_active or not auth.user_has_permission(user, auth.PERMISSION_OXIDIZED_WRITE):
        raise PermissionError("Backup permission required")
    device = Device.objects.filter(name=name, enabled=True).first()
    if not device or not device_in_scope(user, device):
        raise PermissionError("Device unavailable")
    if device.maintenance:
        raise ValueError("Device in maintenance")
    if kind not in ("config", "mikrotik"):
        raise ValueError("Invalid backup type")
    if getattr(settings, "OXIDIZED_ENGINE", "python").lower() != "python":
        raise ValueError("Persistent backup jobs require Python engine")
    if kind == "mikrotik" and device.model != "routeros":
        raise ValueError("RouterOS required")
    return device

@transaction.atomic
def create_job(user, name, kind):
    if getattr(user, "auth_source", "") == "api_key" or not user.pk or user.pk < 1:
        raise PermissionError("Interactive user required")
    device = permitted_device(user, name, kind)
    Device.objects.select_for_update().get(pk=device.pk)
    device = permitted_device(user, name, kind)
    existing = BackgroundTask.objects.filter(task_type=TASK, status__in=["pending","running"], payload__device_id=device.pk).first()
    if existing:
        raise ValueError("Backup job already active for device")
    task = enqueue(TASK, payload={"device_id":device.pk,"device":device.name,"kind":kind,"user_id":user.pk}, dedupe=False, max_attempts=1)
    if not task:
        raise RuntimeError("Task queue unavailable")
    return task

def execute(payload):
    user = User.objects.filter(pk=payload["user_id"], is_active=True).first()
    device = permitted_device(user, payload["device"], payload["kind"])
    if device.pk != payload["device_id"]:
        raise PermissionError("Device identity changed")
    if payload["kind"] == "mikrotik":
        from services.mikrotik_backup import run_mikrotik_backup_by_name
        run_mikrotik_backup_by_name(device.name)
    else:
        from services.oxidized_client import fetch_node
        result, error = fetch_node(device.name)
        if error or not isinstance(result, dict) or result.get("status") != "success":
            raise RuntimeError("Configuration collection failed")
    return {"status":"success"}

def public_job(task):
    p = task.payload
    return {"id":task.pk,"device":p["device"],"kind":p["kind"],"status":task.status,
            "created_at":task.created_at,"started_at":task.started_at,"finished_at":task.finished_at,
            "attempts":task.attempts,"error":"Backup failed; consult server logs" if task.last_error else ""}

def list_jobs(user, name):
    device = Device.objects.filter(name=name).first()
    if not device or not device_in_scope(user, device):
        raise PermissionError("Device unavailable")
    return [public_job(t) for t in BackgroundTask.objects.filter(task_type=TASK,payload__device_id=device.pk).order_by("-id")[:50]]
