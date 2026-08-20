"""Tests for src/dns/find.py — deriving local DNS records from the config tree."""

from typing import Any

import pytest

from models.dns.record import DnsRecord
from models.input_conf.yaml_root import YamlRoot
from src.dns import find_records


def _records(cfg: dict[str, Any]) -> dict[str, str]:
    """hostname -> ip, which is what all of these actually assert about."""
    found: list[DnsRecord] = find_records(YamlRoot.model_validate(cfg))
    return {record.hostname: str(record.ip) for record in found}


def test_derives_a_record_for_every_node(dns_config_dict: dict[str, Any]) -> None:
    # Nodes at every depth, whether or not they serve anything: a record is about
    # where a machine is, not what it runs.
    assert _records(dns_config_dict) == {
        "prox.lab": "10.0.0.1",
        "ct1.lab": "10.0.0.2",
        "vm1.lab": "10.0.0.3",
        "edge.lab": "10.0.0.4",
        "nas.lab": "10.0.0.5",
    }


def test_suffix_leading_dot_is_optional(dns_config_dict: dict[str, Any]) -> None:
    dns_config_dict["settings"]["dns"]["suffix"] = "lab"
    assert "nas.lab" in _records(dns_config_dict)


def test_multi_level_suffix(dns_config_dict: dict[str, Any]) -> None:
    dns_config_dict["settings"]["dns"]["suffix"] = "home.local"
    assert _records(dns_config_dict)["nas.home.local"] == "10.0.0.5"


def test_dns_name_replaces_the_node_name(dns_config_dict: dict[str, Any]) -> None:
    dns_config_dict["hosts"]["nas"]["dns_name"] = "storage"
    records = _records(dns_config_dict)
    assert records["storage.lab"] == "10.0.0.5"
    assert "nas.lab" not in records


def test_multiple_dns_names_share_one_address(
    dns_config_dict: dict[str, Any],
) -> None:
    dns_config_dict["hosts"]["nas"]["dns_name"] = ["storage", "files"]
    records = _records(dns_config_dict)
    assert records["storage.lab"] == "10.0.0.5"
    assert records["files.lab"] == "10.0.0.5"
    assert "nas.lab" not in records


def test_dns_false_excludes_a_node(dns_config_dict: dict[str, Any]) -> None:
    dns_config_dict["hosts"]["nas"]["dns"] = False
    assert "nas.lab" not in _records(dns_config_dict)


def test_nested_nodes_carry_their_path(dns_config_dict: dict[str, Any]) -> None:
    records = find_records(YamlRoot.model_validate(dns_config_dict))
    by_host = {record.hostname: record for record in records}
    assert by_host["ct1.lab"].path == ["prox", "ct1"]


def test_missing_dns_settings_raises(valid_config_dict: dict[str, Any]) -> None:
    # A ValueError, which the CLI renders as a one-line message.
    with pytest.raises(ValueError, match="settings.dns is not configured"):
        find_records(YamlRoot.model_validate(valid_config_dict))
