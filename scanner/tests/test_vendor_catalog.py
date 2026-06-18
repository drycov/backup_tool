"""Vendor catalog — multi-vendor model metadata."""

from services.vendor_catalog import (
    audit_profile_for_model,
    catalog_public,
    default_ports_for_model,
    discovery_probe_plans,
    fallback_discovery_plans,
    is_routeros_family,
    model_label,
    normalize_model,
    supports_mikrotik_binary,
)


def test_normalize_model_aliases():
    assert normalize_model("mikrotik") == "routeros"
    assert normalize_model("IOS-XE") == "iosxe"
    assert normalize_model("arista") == "eos"
    assert normalize_model("juniper") == "junos"


def test_default_ports_by_vendor():
    assert default_ports_for_model("routeros") == [44333, 22]
    assert default_ports_for_model("ios") == [22]
    assert default_ports_for_model("junos") == [22]


def test_mikrotik_binary_only_routeros():
    assert supports_mikrotik_binary("routeros") is True
    assert supports_mikrotik_binary("ios") is False
    assert is_routeros_family("mikrotik") is True
    assert is_routeros_family("eos") is False


def test_audit_profiles():
    assert audit_profile_for_model("iosxe") == "ios"
    assert audit_profile_for_model("nxos") == "ios"
    assert audit_profile_for_model("eos") == "eos"


def test_discovery_plans():
    plans = discovery_probe_plans("routeros", ssh_port_override=2222)
    assert (2222, "routeros") in plans
    assert any(port == 44333 for port, _ in plans)

    fallback = fallback_discovery_plans()
    assert any(model == "ios" for _, model in fallback)
    assert any(model == "routeros" for _, model in fallback)


def test_catalog_public():
    cat = catalog_public()
    assert "routeros" in cat
    assert cat["eos"]["vendor"] == "Arista"
    assert model_label("eos") == "Arista EOS"
