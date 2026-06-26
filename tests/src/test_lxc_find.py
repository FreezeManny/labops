"""Tests for src/lxc/find.py — LXC lookup by name, IP, or vmid (proxmox only)."""

from typing import Any

import pytest

from models.input_conf.yaml_root import YamlRoot
import importlib

lxc_find = importlib.import_module("src.lxc.find")


@pytest.fixture
def model(valid_config_dict: dict[str, Any]) -> YamlRoot:
    return YamlRoot.model_validate(valid_config_dict)


def test_find_all_returns_host_lxc_pairs(model: YamlRoot) -> None:
    pairs = lxc_find.findAll(model)
    assert len(pairs) == 1
    host, lxc = pairs[0]
    assert host.name == "prox"
    assert lxc.name == "ct1"


def test_find_by_name(model: YamlRoot) -> None:
    [(host, lxc)] = lxc_find.find(model, ["ct1"])
    assert host.name == "prox" and lxc.name == "ct1"


def test_find_by_ip(model: YamlRoot) -> None:
    [(_, lxc)] = lxc_find.find(model, ["10.0.0.2"])
    assert lxc.name == "ct1"


def test_find_by_vmid(model: YamlRoot) -> None:
    [(_, lxc)] = lxc_find.find(model, ["101"])
    assert lxc.vmid == 101


def test_find_unknown_raises(model: YamlRoot) -> None:
    with pytest.raises(KeyError, match="missing"):
        lxc_find.find(model, ["missing"])


def test_non_proxmox_hosts_ignored(valid_config_dict: dict[str, Any]) -> None:
    # edge is bare-metal with no lxc; only prox contributes.
    model = YamlRoot.model_validate(valid_config_dict)
    pairs = lxc_find.findAll(model)
    assert {host.name for host, _ in pairs} == {"prox"}
