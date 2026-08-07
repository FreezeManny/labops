"""Tests for the node-level DNS fields and the YamlRoot DNS validators.

Both YamlRoot checks are gated on ``settings.dns`` being configured — without it
nothing is published, so an illegal node name is inert. Most tests here use the
``dns_config_dict`` fixture; a few assert the gate itself.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.host import Host
from models.input_conf.yaml_root import YamlRoot

# ─── Field shape ──────────────────────────────────────────────────────────────


def test_dns_defaults_to_published() -> None:
    host = Host.model_validate({"os": "debian", "ip": "10.0.0.5"})
    assert host.dns is True
    assert host.dns_name is None


def test_dns_name_string_is_coerced_to_list() -> None:
    host = Host.model_validate({"os": "debian", "ip": "10.0.0.5", "dns_name": "nas"})
    assert host.dns_name == ["nas"]


def test_dns_name_accepts_multiple_labels() -> None:
    host = Host.model_validate(
        {"os": "debian", "ip": "10.0.0.5", "dns_name": ["hass", "ha"]}
    )
    assert host.dns_name == ["hass", "ha"]


@pytest.mark.parametrize(
    "name", ["has space", "has.dot", "-leading", "trailing-", "under_score", ""]
)
def test_invalid_dns_name_rejected(name: str) -> None:
    with pytest.raises(ValidationError, match="not a valid hostname label"):
        Host.model_validate({"os": "debian", "ip": "10.0.0.5", "dns_name": name})


def test_overlong_dns_name_rejected() -> None:
    with pytest.raises(ValidationError, match="longer than 63 characters"):
        Host.model_validate({"os": "debian", "ip": "10.0.0.5", "dns_name": "x" * 64})


def test_empty_dns_name_list_rejected() -> None:
    # An empty list looks like it publishes something; `dns: false` is the way to
    # say "no record".
    with pytest.raises(ValidationError, match="at least one label"):
        Host.model_validate({"os": "debian", "ip": "10.0.0.5", "dns_name": []})


def test_dns_name_rejects_internal_duplicate() -> None:
    with pytest.raises(ValidationError, match="more than once"):
        Host.model_validate({"os": "debian", "ip": "10.0.0.5", "dns_name": ["a", "a"]})


# ─── Node names as DNS labels ─────────────────────────────────────────────────


def test_illegal_node_name_rejected_when_dns_configured(
    dns_config_dict: dict[str, Any],
) -> None:
    dns_config_dict["hosts"]["bad_name"] = {"os": "debian", "ip": "10.0.0.90"}
    with pytest.raises(ValidationError, match="node name 'bad_name'"):
        YamlRoot.model_validate(dns_config_dict)


def test_illegal_node_name_allowed_when_dns_not_configured(
    valid_config_dict: dict[str, Any],
) -> None:
    # No settings.dns -> no records derived -> the name is never a hostname.
    valid_config_dict["hosts"]["bad_name"] = {"os": "debian", "ip": "10.0.0.90"}
    assert YamlRoot.model_validate(valid_config_dict) is not None


def test_illegal_node_name_excused_by_dns_name(dns_config_dict: dict[str, Any]) -> None:
    dns_config_dict["hosts"]["bad_name"] = {
        "os": "debian",
        "ip": "10.0.0.90",
        "dns_name": "good-name",
    }
    assert YamlRoot.model_validate(dns_config_dict) is not None


def test_illegal_node_name_excused_by_opting_out(
    dns_config_dict: dict[str, Any],
) -> None:
    dns_config_dict["hosts"]["bad_name"] = {
        "os": "debian",
        "ip": "10.0.0.90",
        "dns": False,
    }
    assert YamlRoot.model_validate(dns_config_dict) is not None


def test_nested_node_name_is_checked(dns_config_dict: dict[str, Any]) -> None:
    # The check walks the whole tree, not just top-level hosts.
    dns_config_dict["hosts"]["prox"]["lxc"]["bad_ct"] = {
        "os": "alpine",
        "ip": "10.0.0.91",
        "vmid": 150,
    }
    with pytest.raises(ValidationError, match="node name 'bad_ct'"):
        YamlRoot.model_validate(dns_config_dict)


# ─── Uniqueness ───────────────────────────────────────────────────────────────


def test_duplicate_dns_name_across_nodes_rejected(
    dns_config_dict: dict[str, Any],
) -> None:
    dns_config_dict["hosts"]["edge"]["dns_name"] = "shared"
    dns_config_dict["hosts"]["nas"]["dns_name"] = "shared"
    with pytest.raises(ValidationError, match="Duplicate DNS name 'shared'"):
        YamlRoot.model_validate(dns_config_dict)


def test_dns_name_colliding_with_another_node_name_rejected(
    dns_config_dict: dict[str, Any],
) -> None:
    # `edge` claims the label `nas`, which the `nas` host already publishes.
    dns_config_dict["hosts"]["edge"]["dns_name"] = "nas"
    with pytest.raises(ValidationError, match="Duplicate DNS name 'nas'"):
        YamlRoot.model_validate(dns_config_dict)


def test_duplicate_dns_name_ignored_without_dns_settings(
    valid_config_dict: dict[str, Any],
) -> None:
    valid_config_dict["hosts"]["edge"]["dns_name"] = "shared"
    valid_config_dict["hosts"]["nas"]["dns_name"] = "shared"
    assert YamlRoot.model_validate(valid_config_dict) is not None


def test_opted_out_node_does_not_reserve_its_name(
    dns_config_dict: dict[str, Any],
) -> None:
    # `edge` publishes nothing, so another node may take the label `edge`.
    dns_config_dict["hosts"]["edge"]["dns"] = False
    dns_config_dict["hosts"]["nas"]["dns_name"] = "edge"
    assert YamlRoot.model_validate(dns_config_dict) is not None
