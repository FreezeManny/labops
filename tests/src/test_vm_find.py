"""Tests for src/vm/find.py — VM lookup across host boundaries."""

from typing import Any

import pytest

from models.input_conf.yaml_root import YamlRoot
import importlib

vm_find = importlib.import_module("src.vm.find")


@pytest.fixture
def model(valid_config_dict: dict[str, Any]) -> YamlRoot:
    return YamlRoot.model_validate(valid_config_dict)


def test_find_all_collects_vms_from_all_hosts(model: YamlRoot) -> None:
    names = {vm.name for vm in vm_find.findAll(model)}
    assert names == {"vm1"}


def test_find_by_name(model: YamlRoot) -> None:
    result = vm_find.find(model, ["vm1"])
    assert [vm.name for vm in result] == ["vm1"]


def test_find_by_ip(model: YamlRoot) -> None:
    result = vm_find.find(model, ["10.0.0.3"])
    assert [vm.name for vm in result] == ["vm1"]


def test_find_unknown_raises(model: YamlRoot) -> None:
    with pytest.raises(KeyError, match="ghost"):
        vm_find.find(model, ["ghost"])
