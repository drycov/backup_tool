"""Автогенерация шаблонов провижионинга из конфигов Oxidized."""

from __future__ import annotations

import difflib
import logging
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections.abc import Callable
from typing import Any

from services.inventory import load_inventory
from services.object_scope import filter_devices
from services.oxidized_client import get_node_config
from services.schemas import Device
from services.sites import site_matches_filter
from services.vendor_catalog import normalize_model

logger = logging.getLogger(__name__)

# Ниже порога — устройство считается «сложным» (outlier)
DEFAULT_COMPLEXITY_THRESHOLD = 0.85
MIN_DEVICES_PER_CLUSTER = 2

_VOLATILE_PATTERNS = (
    r"^\s*/system\s+clock",
    r"^\s*/system\s+resource",
    r"^\s*/system\s+note",
    r"uptime",
    r"last-?changed",
    r"build-?time",
    r"^\s*#\s*by\s+backup",
    r"^\s*!\s*last\s+configuration",
    r"^\s*ntp\s+clock-period",
)

_IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?\b")

_MAC_RE = re.compile(r"\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b", re.I)


def _replace_known_value(body: str, value: str, expression: str) -> str:
    if not value or len(value.strip()) < 2:
        return body
    return re.sub(re.escape(value), expression, body, flags=re.I)


def extract_template_variables(raw: str, device: Device) -> tuple[str, list[dict[str, str]]]:
    """Выделить безопасные device-specific значения из baseline-конфига."""
    body = raw
    variables: list[dict[str, str]] = []
    known = (
        ("name", device.name, "{{ device.name }}"),
        ("ip", device.ip.split("/")[0] if device.ip else "", "{{ device.ip }}"),
        ("site", device.site or "", "{{ site }}"),
        ("group", device.group or "", "{{ group }}"),
        ("role", device.role or "", "{{ role }}"),
    )
    for name, value, expression in known:
        if not value or len(value.strip()) < 2:
            continue
        occurrences = len(re.findall(re.escape(value), body, flags=re.I))
        if occurrences:
            body = _replace_known_value(body, value, expression)
            variables.append({"name": name, "source": "inventory", "expression": expression, "occurrences": str(occurrences)})
    return body, variables



_SEMANTIC_VARIABLE_PATTERNS = (
    ("gateway", re.compile(r"\bgateway=(\d{1,3}(?:\.\d{1,3}){3})\b", re.I)),
    ("vlan_id", re.compile(r"\bvlan-id=(\d{1,4})\b", re.I)),
    ("local_as", re.compile(r"\b(?:local\.as|local-as)=(\d{1,10})\b", re.I)),
    ("remote_as", re.compile(r"\b(?:remote\.as|remote-as)=(\d{1,10})\b", re.I)),
    ("bgp_peer_ip", re.compile(r"\b(?:remote.address|remote-address)=(\d{1,3}(?:\.\d{1,3}){3})\b", re.I)),
    ("dns_servers", re.compile(r"\bservers=([\d., ]+)\b", re.I)),
)

def extract_semantic_variables(raw: str) -> tuple[str, list[dict[str, Any]]]:
    """Найти кандидаты второго уровня без автоматической подстановки."""
    variables: list[dict[str, Any]] = []
    for name, pattern in _SEMANTIC_VARIABLE_PATTERNS:
        matches = list(pattern.finditer(raw))
        if not matches:
            continue
        values = list(dict.fromkeys(m.group(1).strip() for m in matches if m.group(1).strip()))
        if len(values) != 1:
            continue
        variables.append({
            "name": name,
            "source": "semantic_candidate",
            "expression": "{{ " + name + " }}",
            "confidence": "high",
            "occurrences": len(matches),
            "example": values[0],
        })
    return raw, variables


def extract_common_template(samples: list[DeviceConfigSample], baseline: DeviceConfigSample) -> dict[str, Any]:
    """Извлечь устойчивую часть baseline без потери divergent-команд."""
    valid = [s for s in samples if s.raw and not s.error]
    baseline_lines = baseline.raw.splitlines()
    normalized_sets = [set(s.normalized.splitlines()) for s in valid]
    common: list[str] = []
    divergent: list[str] = []
    required_matches = max(1, math.ceil(len(valid) * 0.8))
    for line in baseline_lines:
        normalized = normalize_config_for_compare(line, baseline.device)
        if not normalized:
            continue
        matches = sum(1 for lines in normalized_sets if normalized in lines)
        if matches >= required_matches:
            common.append(line)
        else:
            divergent.append(line)
    rendered, variables = extract_template_variables("\n".join(common), baseline.device)
    semantic_body, semantic_variables = extract_semantic_variables(rendered)
    variables.extend(semantic_variables)
    total = len([x for x in baseline_lines if x.strip()])
    return {
        "common_lines": len(common),
        "divergent_lines": len(divergent),
        "coverage": round(len(common) / max(1, total), 4),
        "variables": variables,
        "review_lines": divergent[:100],
        "body": semantic_body.strip() + "\n" if semantic_body.strip() else "",
    }


@dataclass
class DeviceConfigSample:
    device: Device
    raw: str
    normalized: str
    error: str = ""


@dataclass
class ClusterAnalysis:
    group: str
    site: str
    model: str
    devices: list[DeviceConfigSample] = field(default_factory=list)
    baseline_device: str = ""
    baseline_similarity: float = 0.0
    simple_devices: list[str] = field(default_factory=list)
    complex_devices: list[dict[str, Any]] = field(default_factory=list)
    template_body: str = ""
    extraction: dict[str, Any] = field(default_factory=dict)
    skipped_reason: str = ""

    @property
    def device_count(self) -> int:
        return len([d for d in self.devices if d.raw and not d.error])

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "site": self.site,
            "model": self.model,
            "device_count": self.device_count,
            "baseline_device": self.baseline_device,
            "baseline_similarity": round(self.baseline_similarity, 4),
            "simple_devices": self.simple_devices,
            "complex_devices": self.complex_devices,
            "template_body": self.template_body,
            "extraction": self.extraction,
            "skipped_reason": self.skipped_reason,
            "devices": [
                {
                    "name": d.device.name,
                    "ip": d.device.ip,
                    "has_config": bool(d.raw),
                    "error": d.error,
                }
                for d in self.devices
            ],
        }


def _is_volatile_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    for pattern in _VOLATILE_PATTERNS:
        if re.search(pattern, stripped, re.I):
            return True
    return False


def normalize_config_for_compare(text: str, device: Device) -> str:
    """Нормализация для сравнения: убрать volatile строки и device-specific значения."""
    if not text:
        return ""
    lines_out: list[str] = []
    for raw_line in text.splitlines():
        if _is_volatile_line(raw_line):
            continue
        line = raw_line.strip()
        if device.name:
            line = re.sub(re.escape(device.name), "<NAME>", line, flags=re.I)
        if device.ip:
            line = line.replace(device.ip.split("/")[0], "<IP>")
        line = _IP_RE.sub("<IP>", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines_out.append(line.lower())
    return "\n".join(lines_out)


def similarity_ratio(norm_a: str, norm_b: str) -> float:
    if not norm_a and not norm_b:
        return 1.0
    if not norm_a or not norm_b:
        return 0.0
    return difflib.SequenceMatcher(None, norm_a, norm_b).ratio()


def _load_device_config(device: Device) -> DeviceConfigSample:
    try:
        text, err = get_node_config(device.name)
    except Exception as exc:
        logger.warning("provision | config load failed | %s | %s", device.name, exc)
        return DeviceConfigSample(device=device, raw="", normalized="", error=str(exc)[:200])
    if err:
        return DeviceConfigSample(device=device, raw="", normalized="", error=err)
    if not text or not str(text).strip():
        return DeviceConfigSample(device=device, raw="", normalized="", error="нет конфига")
    raw = str(text)
    return DeviceConfigSample(
        device=device,
        raw=raw,
        normalized=normalize_config_for_compare(raw, device),
    )


def _pick_baseline(samples: list[DeviceConfigSample]) -> tuple[DeviceConfigSample, float]:
    valid = [s for s in samples if s.normalized]
    if not valid:
        raise ValueError("Нет конфигов для сравнения")
    if len(valid) == 1:
        return valid[0], 1.0

    best: DeviceConfigSample | None = None
    best_avg = -1.0
    for candidate in valid:
        scores = [
            similarity_ratio(candidate.normalized, other.normalized)
            for other in valid
            if other.device.name != candidate.device.name
        ]
        avg = sum(scores) / len(scores) if scores else 1.0
        if avg > best_avg:
            best_avg = avg
            best = candidate
    assert best is not None
    return best, best_avg


def _classify_devices(
    samples: list[DeviceConfigSample],
    baseline: DeviceConfigSample,
    *,
    threshold: float,
) -> tuple[list[str], list[dict[str, Any]]]:
    simple: list[str] = []
    complex_list: list[dict[str, Any]] = []
    for sample in samples:
        if not sample.normalized or sample.error:
            complex_list.append(
                {
                    "name": sample.device.name,
                    "similarity": 0.0,
                    "reason": sample.error or "пустой конфиг",
                    "complex": True,
                }
            )
            continue
        sim = similarity_ratio(sample.normalized, baseline.normalized)
        if sample.device.name == baseline.device.name:
            simple.append(sample.device.name)
            continue
        if sim >= threshold:
            simple.append(sample.device.name)
        else:
            complex_list.append(
                {
                    "name": sample.device.name,
                    "similarity": round(sim, 4),
                    "reason": f"отклонение от baseline ({sim:.0%} < {threshold:.0%})",
                    "complex": True,
                }
            )
    return simple, complex_list


def raw_config_to_jinja_template(raw: str, device: Device) -> str:
    """Преобразовать baseline-конфиг в Jinja2 с подстановкой полей устройства."""
    body = raw
    replacements = [
        (device.name, "{{ device.name }}"),
        (device.ip.split("/")[0] if device.ip else "", "{{ device.ip }}"),
        (device.site or "", "{{ site }}"),
        (device.group or "", "{{ group }}"),
        (device.role or "", "{{ role }}"),
    ]
    for old, new in replacements:
        if old and len(old) >= 2:
            body = re.sub(re.escape(old), new, body, flags=re.I)
    # Оставшиеся уникальные IP → переменная
    body = _IP_RE.sub("{{ device.ip }}", body)
    header = (
        f"# Generated baseline from {device.name}\n"
        f"# scope: group={device.group or '*'} site={device.site or '*'}\n"
    )
    return header + body.strip() + "\n"


def _cluster_key(device: Device) -> tuple[str, str, str]:
    return (device.group or "default", device.site or "", (device.model or "routeros").lower())


def _slug_for_cluster(group: str, site: str, model: str) -> str:
    parts = ["gen"]
    for part in (group, site, model):
        slug = re.sub(r"[^a-z0-9]+", "-", part.lower()).strip("-")
        if slug:
            parts.append(slug[:24])
    return "-".join(parts)[:63]


def _resolve_analysis_devices(
    *,
    group: str = "",
    site: str = "",
    model: str = "",
    user=None,
) -> list[Device]:
    inventory = load_inventory()
    devices = [d for d in inventory.devices if d.enabled]
    if user is not None:
        devices = filter_devices(user, devices)
    if group:
        devices = [d for d in devices if d.group == group]
    if site:
        devices = [d for d in devices if site_matches_filter(d.site or "", site)]
    if model:
        want = normalize_model(model)
        devices = [d for d in devices if normalize_model(d.model) == want]
    return devices


def clusters_to_api_payload(
    clusters: list[ClusterAnalysis],
    *,
    filters: dict[str, Any],
) -> dict[str, Any]:
    complex_devices: list[dict[str, Any]] = []
    for cluster in clusters:
        for item in cluster.complex_devices:
            complex_devices.append(
                {
                    "name": item["name"],
                    "group": cluster.group,
                    "site": cluster.site,
                    "model": cluster.model,
                    "similarity": item.get("similarity"),
                    "reason": item.get("reason", ""),
                }
            )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": filters,
        "clusters": [c.to_dict() for c in clusters],
        "complex_devices": complex_devices,
    }


def analyze_clusters(
    *,
    group: str = "",
    site: str = "",
    model: str = "",
    user=None,
    devices: list[Device] | None = None,
    complexity_threshold: float = DEFAULT_COMPLEXITY_THRESHOLD,
    min_devices: int = MIN_DEVICES_PER_CLUSTER,
    log_cb: Callable[[str, str], None] | None = None,
) -> list[ClusterAnalysis]:
    def _log(level: str, text: str) -> None:
        if log_cb:
            log_cb(level, text)

    if devices is None:
        _log("info", "Загрузка инвентаря устройств…")
        devices = _resolve_analysis_devices(group=group, site=site, model=model, user=user)
    else:
        _log("info", f"Устройств в выборке: {len(devices)}")

    buckets: dict[tuple[str, str, str], list[Device]] = defaultdict(list)
    for device in devices:
        buckets[_cluster_key(device)].append(device)

    _log(
        "info",
        f"Фильтры: group={group or '*'} site={site or '*'} model={model or '*'} | "
        f"устройств {len(devices)}, кластеров {len(buckets)}",
    )

    results: list[ClusterAnalysis] = []
    for (grp, st, mdl), cluster_devices in sorted(buckets.items()):
        label = f"{grp} / {st or '—'} / {mdl}"
        _log("info", f"▸ Кластер {label}: {len(cluster_devices)} устройств")
        analysis = ClusterAnalysis(group=grp, site=st, model=mdl)
        samples: list[DeviceConfigSample] = []
        for device in cluster_devices:
            _log("info", f"  загрузка конфига {device.name}…")
            sample = _load_device_config(device)
            if sample.error:
                _log("warn", f"  ✗ {device.name}: {sample.error}")
            elif not sample.raw:
                _log("warn", f"  ✗ {device.name}: пустой конфиг")
            else:
                _log("success", f"  ✓ {device.name}: конфиг загружен")
            samples.append(sample)
        analysis.devices = samples

        valid_count = sum(1 for s in analysis.devices if s.raw and not s.error)
        if valid_count < min_devices:
            analysis.skipped_reason = (
                f"недостаточно конфигов ({valid_count} < {min_devices})"
            )
            _log("warn", f"  пропущен: {analysis.skipped_reason}")
            results.append(analysis)
            continue

        try:
            baseline, avg_sim = _pick_baseline(analysis.devices)
        except ValueError as exc:
            analysis.skipped_reason = str(exc)
            _log("warn", f"  пропущен: {exc}")
            results.append(analysis)
            continue

        analysis.baseline_device = baseline.device.name
        analysis.baseline_similarity = avg_sim
        analysis.simple_devices, analysis.complex_devices = _classify_devices(
            analysis.devices,
            baseline,
            threshold=complexity_threshold,
        )
        analysis.extraction = extract_common_template(analysis.devices, baseline)
        analysis.template_body = analysis.extraction["body"]
        if not analysis.template_body:
            analysis.template_body = raw_config_to_jinja_template(baseline.raw, baseline.device)
        _log(
            "info",
            f"  baseline: {baseline.device.name} ({avg_sim:.0%}), "
            f"простых {len(analysis.simple_devices)}, сложных {len(analysis.complex_devices)}",
        )
        if analysis.template_body:
            _log("success", "  шаблон сформирован")
        results.append(analysis)

    return results


def generate_templates_from_configs(
    *,
    group: str = "",
    site: str = "",
    model: str = "",
    user=None,
    devices=None,
    complexity_threshold: float = DEFAULT_COMPLEXITY_THRESHOLD,
    min_devices: int = MIN_DEVICES_PER_CLUSTER,
    upsert: bool = True,
    log_cb: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    from core.models import ProvisionTemplate
    from services.provisioning import create_template

    def _log(level: str, text: str) -> None:
        if log_cb:
            log_cb(level, text)

    _log("info", "Генерация шаблонов из конфигов Oxidized…")
    clusters = analyze_clusters(
        group=group,
        site=site,
        model=model,
        user=user,
        devices=devices,
        complexity_threshold=complexity_threshold,
        min_devices=min_devices,
        log_cb=log_cb,
    )

    created: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for cluster in clusters:
        label = f"{cluster.group} / {cluster.site or '—'} / {cluster.model}"
        if cluster.skipped_reason or not cluster.template_body:
            skipped.append(cluster.to_dict())
            reason = cluster.skipped_reason or "нет шаблона"
            _log("warn", f"▸ {label} — пропущен: {reason}")
            continue

        slug = _slug_for_cluster(cluster.group, cluster.site, cluster.model)
        meta = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "from_configs",
            "baseline_device": cluster.baseline_device,
            "baseline_similarity": cluster.baseline_similarity,
            "complexity_threshold": complexity_threshold,
            "simple_devices": cluster.simple_devices,
            "complex_devices": cluster.complex_devices,
            "device_count": cluster.device_count,
            "extraction": cluster.extraction,
            "suggested_extra_vars": [
                item["name"] for item in cluster.extraction.get("variables", [])
                if item.get("source") == "semantic_candidate"
            ],
        }
        name = f"Auto: {cluster.group}"
        if cluster.site:
            name += f" / {cluster.site}"
        name += f" ({cluster.model})"
        description = (
            f"Сгенерировано из {cluster.device_count} конфигов. "
            f"Baseline: {cluster.baseline_device}. "
            f"Сложных устройств: {len(cluster.complex_devices)}."
        )

        existing = ProvisionTemplate.objects.filter(slug=slug).first()
        if existing and upsert:
            existing.name = name
            existing.description = description
            existing.model = cluster.model
            existing.body = cluster.template_body
            existing.scope_group = cluster.group
            existing.scope_site = cluster.site
            existing.source = ProvisionTemplate.SOURCE_GENERATED
            existing.meta = meta
            existing.is_active = True
            existing.save()
            updated.append(
                {
                    "slug": slug,
                    "id": existing.id,
                    "group": cluster.group,
                    "site": cluster.site,
                    "complex_devices": cluster.complex_devices,
                    "extraction": cluster.extraction,
                }
            )
            _log("success", f"▸ {label} — обновлён шаблон {slug}")
        elif existing:
            skipped.append({**cluster.to_dict(), "skipped_reason": f"шаблон {slug} уже существует"})
            _log("warn", f"▸ {label} — шаблон {slug} уже существует (upsert=off)")
        else:
            row = create_template(
                slug=slug,
                name=name,
                body=cluster.template_body,
                model=cluster.model,
                description=description,
            )
            tpl = ProvisionTemplate.objects.get(id=row["id"])
            tpl.scope_group = cluster.group
            tpl.scope_site = cluster.site
            tpl.source = ProvisionTemplate.SOURCE_GENERATED
            tpl.meta = meta
            tpl.save(update_fields=["scope_group", "scope_site", "source", "meta"])
            created.append(
                {
                    "slug": slug,
                    "id": row["id"],
                    "group": cluster.group,
                    "site": cluster.site,
                    "complex_devices": cluster.complex_devices,
                }
            )
            _log("success", f"▸ {label} — создан шаблон {slug}")

    logger.info(
        "provision | generate | created=%d updated=%d skipped=%d",
        len(created),
        len(updated),
        len(skipped),
    )
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "clusters": [c.to_dict() for c in clusters],
    }
