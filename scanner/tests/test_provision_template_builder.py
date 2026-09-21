"""Тесты автогенерации шаблонов провижионинга из конфигов."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.models import Device as DeviceModel, ProvisionTemplate
from services.provision_template_builder import (
    analyze_clusters,
    generate_templates_from_configs,
    normalize_config_for_compare,
    raw_config_to_jinja_template,
    similarity_ratio,
    extract_common_template,
)
from services.schemas import Device


def test_normalize_config_strips_volatile_and_ips():
    device = Device(name="r1", ip="10.0.0.1", model="routeros", group="hex", site="dc1")
    raw = """
/system clock
/system identity set name=r1
/ip address add address=10.0.0.1/24 interface=ether1
"""
    norm = normalize_config_for_compare(raw, device)
    assert "clock" not in norm
    assert "10.0.0.1" not in norm
    assert "<name>" in norm
    assert "<ip>" in norm


def test_similarity_ratio_identical():
    assert similarity_ratio("a\nb", "a\nb") == 1.0


def test_raw_config_to_jinja_replaces_device_fields():
    device = Device(name="router-a", ip="192.168.1.1", model="routeros", group="hex", site="dc1")
    raw = "/system identity set name=router-a\n/ip address add address=192.168.1.1/24\n"
    body = raw_config_to_jinja_template(raw, device)
    assert "{{ device.name }}" in body
    assert "{{ device.ip }}" in body
    assert "router-a" not in body.split("\n", 1)[-1]


@pytest.mark.django_db
def test_analyze_clusters_groups_by_site_and_model():
    DeviceModel.objects.create(name="r1", ip="10.0.0.1", model="routeros", group="hex", site="dc1")
    DeviceModel.objects.create(name="r2", ip="10.0.0.2", model="routeros", group="hex", site="dc1")
    DeviceModel.objects.create(name="r3", ip="10.0.0.3", model="routeros", group="hex", site="dc2")

    cfg_similar = "/system identity set name=DEV\n/ip address add address=IP/24\n"
    cfg_outlier = "/system identity set name=DEV\n/interface bridge add name=br0\n"

    def fake_config(name):
        if name == "r3":
            return cfg_similar.replace("DEV", name).replace("IP", "10.0.0.3"), ""
        if name == "r2":
            return cfg_outlier.replace("DEV", name).replace("IP", "10.0.0.2"), ""
        return cfg_similar.replace("DEV", name).replace("IP", "10.0.0.1"), ""

    with patch("services.provision_template_builder.get_node_config", side_effect=lambda n: fake_config(n)):
        clusters = analyze_clusters(group="hex", complexity_threshold=0.85, min_devices=2)

    dc1 = next(c for c in clusters if c.site == "dc1")
    assert dc1.baseline_device in ("r1", "r2")
    assert len(dc1.simple_devices) + len(dc1.complex_devices) == 2
    assert any(d["name"] == "r2" for d in dc1.complex_devices) or any(
        d["name"] == "r1" for d in dc1.complex_devices
    )


@pytest.mark.django_db
def test_analyze_clusters_handles_missing_oxidized_node():
    DeviceModel.objects.create(name="r1", ip="10.0.0.1", model="routeros", group="hex", site="dc1")
    DeviceModel.objects.create(name="r2", ip="10.0.0.2", model="routeros", group="hex", site="dc1")

    def fake_config(name):
        return None, f"Узел '{name}' не найден в Oxidized"

    with patch("services.provision_template_builder.get_node_config", side_effect=lambda n: fake_config(n)):
        clusters = analyze_clusters(group="hex", site="dc1", min_devices=2)

    assert len(clusters) == 1
    assert clusters[0].skipped_reason
    assert not clusters[0].template_body


@pytest.mark.django_db
def test_generate_templates_creates_and_upserts():
    DeviceModel.objects.create(name="r1", ip="10.0.0.1", model="routeros", group="hex", site="dc1")
    DeviceModel.objects.create(name="r2", ip="10.0.0.2", model="routeros", group="hex", site="dc1")
    cfg = "/system identity set name=DEV\n"

    with patch(
        "services.provision_template_builder.get_node_config",
        side_effect=lambda n: (cfg.replace("DEV", n), ""),
    ):
        result = generate_templates_from_configs(group="hex", site="dc1", min_devices=2)

    assert len(result["created"]) == 1
    tpl = ProvisionTemplate.objects.get(slug=result["created"][0]["slug"])
    assert tpl.source == ProvisionTemplate.SOURCE_GENERATED
    assert tpl.scope_group == "hex"
    assert tpl.scope_site == "dc1"
    assert "{{ device.name }}" in tpl.body

    with patch(
        "services.provision_template_builder.get_node_config",
        side_effect=lambda n: (cfg.replace("DEV", n), ""),
    ):
        result2 = generate_templates_from_configs(group="hex", site="dc1", min_devices=2, upsert=True)

    assert len(result2["updated"]) == 1
    assert ProvisionTemplate.objects.filter(source=ProvisionTemplate.SOURCE_GENERATED).count() == 1


def test_extract_common_template_reports_coverage_and_inventory_variables():
    device = Device(name="router-a", ip="10.0.0.1", model="routeros", group="hex", site="dc1", role="core")
    sample = type("Sample", (), {})()
    sample.device = device
    sample.raw = "/system identity set name=router-a\n/ip address add address=10.0.0.1/24\n/interface bridge add name=br-core\n"
    sample.error = ""
    sample.normalized = normalize_config_for_compare(sample.raw, device)

    result = extract_common_template([sample], sample)

    assert result["coverage"] > 0
    assert "{{ device.name }}" in result["body"]
    assert "{{ device.ip }}" in result["body"]
    assert result["variables"]
