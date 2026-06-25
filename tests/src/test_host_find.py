"""Tests for src/host/find.py — host lookup by name and IP."""

from typing import Any

import pytest

from models.input_conf.yaml_root import YamlRoot
import importlib

host_find = importlib.import_module("src.host.find")


@pytest.fixture
def model(valid_config_dict: dict[str, Any]) -> YamlRoot:
    return YamlRoot.model_validate(valid_config_dict)


def test_find_all_returns_every_host(model: YamlRoot) -> None:
    names = {h.name for h in host_find.findAll(model)}
    assert names == {"prox", "edge"}


def test_find_by_name(model: YamlRoot) -> None:
    result = host_find.find(model, ["edge"])
    assert [h.name for h in result] == ["edge"]


def test_find_by_ip(model: YamlRoot) -> None:
    result = host_find.find(model, ["10.0.0.1"])
    assert [h.name for h in result] == ["prox"]


def test_find_unknown_raises(model: YamlRoot) -> None:
    with pytest.raises(KeyError, match="nope"):
        host_find.find(model, ["nope"])
