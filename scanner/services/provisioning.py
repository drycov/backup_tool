"""Провижионинг: шаблоны Jinja2 и применение конфигурации на устройства."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from core.models import ProvisionRun, ProvisionTemplate
from django.db import transaction
from jinja2 import BaseLoader, Environment, StrictUndefined, TemplateSyntaxError, UndefinedError

from services.database import is_database_available, require_database
from services.inventory import load_inventory
from services.object_scope import device_in_scope
from services.schemas import Device

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{1,62}$")
_jinja = Environment(loader=BaseLoader(), undefined=StrictUndefined, autoescape=False)


class ProvisioningError(Exception):
    pass


def _template_row_public(row: ProvisionTemplate) -> dict[str, Any]:
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "description": row.description or "",
        "model": row.model,
        "body": row.body,
        "is_active": row.is_active,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _run_row_public(row: ProvisionRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "template_id": row.template_id,
        "template_slug": row.template_slug,
        "device_name": row.device_name,
        "device_ip": row.device_ip,
        "device_model": row.device_model,
        "status": row.status,
        "dry_run": row.dry_run,
        "rendered_config": row.rendered_config,
        "output": row.output,
        "error": row.error,
        "triggered_by": row.triggered_by,
        "correlation_id": row.correlation_id,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "created_at": row.created_at,
    }


def list_templates(*, active_only: bool = False) -> list[dict[str, Any]]:
    if not is_database_available():
        return []
    qs = ProvisionTemplate.objects.all()
    if active_only:
        qs = qs.filter(is_active=True)
    return [_template_row_public(r) for r in qs]


def get_template(template_id: int | None = None, *, slug: str = "") -> ProvisionTemplate:
    require_database("Provisioning требует базу данных")
    if template_id:
        row = ProvisionTemplate.objects.filter(id=template_id).first()
    elif slug:
        row = ProvisionTemplate.objects.filter(slug=slug.strip()).first()
    else:
        raise ProvisioningError("Укажите template id или slug")
    if not row:
        raise ProvisioningError("Шаблон не найден")
    return row


def create_template(
    *,
    slug: str,
    name: str,
    body: str,
    model: str = "routeros",
    description: str = "",
) -> dict[str, Any]:
    require_database("Provisioning требует базу данных")
    slug = slug.strip().lower()
    if not _SLUG_RE.match(slug):
        raise ProvisioningError("slug: латиница, 2–63 символа")
    if not (body or "").strip():
        raise ProvisioningError("Тело шаблона не может быть пустым")
    validate_template_syntax(body)
    if ProvisionTemplate.objects.filter(slug=slug).exists():
        raise ProvisioningError(f"Шаблон '{slug}' уже существует")
    row = ProvisionTemplate.objects.create(
        slug=slug,
        name=name.strip() or slug,
        description=(description or "").strip(),
        model=(model or "routeros").strip().lower(),
        body=body,
    )
    logger.info("provision | template created | slug=%s model=%s", slug, row.model)
    return _template_row_public(row)


def update_template(
    template_id: int,
    *,
    name: str | None = None,
    body: str | None = None,
    model: str | None = None,
    description: str | None = None,
    is_active: bool | None = None,
) -> dict[str, Any]:
    row = get_template(template_id)
    if name is not None:
        row.name = name.strip() or row.slug
    if description is not None:
        row.description = description.strip()
    if model is not None:
        row.model = model.strip().lower() or row.model
    if body is not None:
        if not body.strip():
            raise ProvisioningError("Тело шаблона не может быть пустым")
        validate_template_syntax(body)
        row.body = body
    if is_active is not None:
        row.is_active = is_active
    row.save()
    return _template_row_public(row)


def delete_template(template_id: int) -> None:
    row = get_template(template_id)
    row.delete()
    logger.info("provision | template deleted | slug=%s", row.slug)


def validate_template_syntax(body: str) -> None:
    try:
        _jinja.from_string(body)
    except TemplateSyntaxError as exc:
        raise ProvisioningError(f"Синтаксис Jinja2: {exc}") from exc


def _resolve_device(device_name: str, user=None) -> Device:
    inventory = load_inventory()
    device = next((d for d in inventory.devices if d.name == device_name), None)
    if not device:
        raise ProvisioningError(f"Устройство '{device_name}' не найдено")
    if user is not None and not device_in_scope(user, device):
        raise ProvisioningError("Устройство вне вашего object scope")
    return device


def build_render_context(device: Device, extra_vars: dict[str, Any] | None = None) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "device": {
            "name": device.name,
            "ip": device.ip,
            "model": device.model,
            "group": device.group,
            "site": device.site or "",
            "role": device.role or "",
            "tags": list(device.tags or []),
            "critical": bool(device.critical),
        },
        "name": device.name,
        "ip": device.ip,
        "group": device.group,
        "site": device.site or "",
        "role": device.role or "",
    }
    if extra_vars:
        ctx.update(extra_vars)
    return ctx


def render_template_body(body: str, context: dict[str, Any]) -> str:
    try:
        template = _jinja.from_string(body)
        return template.render(**context).strip() + "\n"
    except UndefinedError as exc:
        raise ProvisioningError(f"Не задана переменная шаблона: {exc}") from exc
    except TemplateSyntaxError as exc:
        raise ProvisioningError(f"Синтаксис Jinja2: {exc}") from exc


def preview_provision(
    *,
    template_id: int | None = None,
    template_slug: str = "",
    device_name: str,
    extra_vars: dict[str, Any] | None = None,
    user=None,
) -> dict[str, Any]:
    template = get_template(template_id, slug=template_slug)
    if not template.is_active:
        raise ProvisioningError("Шаблон отключён")
    device = _resolve_device(device_name, user)
    if template.model != "*" and device.model != template.model:
        raise ProvisioningError(
            f"Модель устройства ({device.model}) не совпадает с шаблоном ({template.model})"
        )
    context = build_render_context(device, extra_vars)
    rendered = render_template_body(template.body, context)
    return {
        "template_slug": template.slug,
        "device_name": device.name,
        "device_model": device.model,
        "rendered_config": rendered,
        "context": context,
    }


def list_runs(*, limit: int = 50, device: str = "") -> list[dict[str, Any]]:
    if not is_database_available():
        return []
    limit = max(1, min(limit, 200))
    qs = ProvisionRun.objects.select_related("template").order_by("-created_at")
    if device:
        qs = qs.filter(device_name=device)
    return [_run_row_public(r) for r in qs[:limit]]


@transaction.atomic
def run_provision(
    *,
    template_id: int | None = None,
    template_slug: str = "",
    device_name: str,
    extra_vars: dict[str, Any] | None = None,
    dry_run: bool = False,
    triggered_by: str = "",
    correlation_id: str = "",
    user=None,
) -> dict[str, Any]:
    preview = preview_provision(
        template_id=template_id,
        template_slug=template_slug,
        device_name=device_name,
        extra_vars=extra_vars,
        user=user,
    )
    template = get_template(template_id, slug=template_slug)
    device = _resolve_device(device_name, user)
    now = datetime.now(timezone.utc)

    run = ProvisionRun.objects.create(
        template=template,
        template_slug=template.slug,
        device_name=device.name,
        device_ip=device.ip,
        device_model=device.model,
        status=ProvisionRun.STATUS_DRY_RUN if dry_run else ProvisionRun.STATUS_RUNNING,
        dry_run=dry_run,
        rendered_config=preview["rendered_config"],
        triggered_by=triggered_by[:64],
        correlation_id=correlation_id[:64],
        started_at=now,
    )

    if dry_run:
        run.finished_at = now
        run.save(update_fields=["status", "finished_at"])
        logger.info("provision | dry-run | %s | %s", template.slug, device.name)
        return _run_row_public(run)

    from services.provisioning_apply import apply_config_to_device

    try:
        result = apply_config_to_device(device, preview["rendered_config"])
        run.status = ProvisionRun.STATUS_COMPLETED
        run.output = (result.get("output") or "")[:8000]
        run.finished_at = datetime.now(timezone.utc)
        run.save(update_fields=["status", "output", "finished_at"])
        logger.info("provision | applied | %s | %s", template.slug, device.name)
    except Exception as exc:
        run.status = ProvisionRun.STATUS_FAILED
        run.error = str(exc)[:2000]
        run.finished_at = datetime.now(timezone.utc)
        run.save(update_fields=["status", "error", "finished_at"])
        logger.warning("provision | failed | %s | %s | %s", template.slug, device.name, exc)
        raise ProvisioningError(str(exc)) from exc

    return _run_row_public(run)


def seed_default_templates() -> None:
    if not is_database_available():
        return
    if ProvisionTemplate.objects.exists():
        return
    ProvisionTemplate.objects.create(
        slug="routeros-identity",
        name="RouterOS: system identity",
        description="Пример: задать identity по имени из инвентаря",
        model="routeros",
        body="/system identity set name={{ device.name }}\n",
    )
    logger.info("provision | seeded default templates")
