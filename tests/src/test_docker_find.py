"""Tests for src/docker/find.py — recursive stack walk and filtering."""

from pathlib import Path
from typing import Any

import pytest

from models.input_conf.yaml_root import YamlRoot
import importlib

docker_find = importlib.import_module("src.docker.find")


@pytest.fixture
def model(valid_config_dict: dict[str, Any]) -> YamlRoot:
    return YamlRoot.model_validate(valid_config_dict)


def test_find_all_builds_nested_path(model: YamlRoot) -> None:
    results = docker_find.findAll(model)
    assert len(results) == 1
    assert results[0].stack.name == "app"
    assert results[0].path == ["prox", "vm1"]
    assert str(results[0].target_ip) == "10.0.0.3"


def test_find_all_resolves_default_creds(model: YamlRoot) -> None:
    # vm1 has no creds of its own → falls back to settings.default_creds.
    result = docker_find.findAll(model)[0]
    assert result.creds is model.settings.default_creds


def test_find_by_stack_name(model: YamlRoot) -> None:
    results = docker_find.find(model, stack_name="app")
    assert [r.stack.name for r in results] == ["app"]


def test_find_by_node_name(model: YamlRoot) -> None:
    results = docker_find.find(model, node_name="vm1")
    assert len(results) == 1


def test_find_missing_stack_raises(model: YamlRoot) -> None:
    with pytest.raises(KeyError, match="Stack 'nope' was not found"):
        docker_find.find(model, stack_name="nope")


def test_find_missing_node_raises(model: YamlRoot) -> None:
    with pytest.raises(KeyError, match="did not match"):
        docker_find.find(model, node_name="nope")


def _two_stacks_same_name(key_dir: Path) -> dict[str, Any]:
    """Two hosts each carrying a docker stack named 'app' (different proxy/port)."""

    def stack(proxy: str, port: int) -> dict[str, Any]:
        return {
            "root_path": "/srv",
            "stacks": {
                "app": {
                    "config_path": str(key_dir),
                    "web_services": [{"port": port, "proxy_name": proxy}],
                },
            },
        }

    return {
        "settings": {
            "default_creds": {"username": "u", "passwd": "p"},
            "proxy": {
                "proxy_suffix": ".example.test",
                "proxy_location": "10.0.0.80",
                "access_lists": {"local": {"default": True, "accept": ["10.0.0.0/24"]}},
            },
        },
        "hosts": {
            "h1": {"os": "debian", "ip": "10.0.0.10", "docker": stack("a1", 81)},
            "h2": {"os": "debian", "ip": "10.0.0.11", "docker": stack("a2", 82)},
        },
    }


def test_ambiguous_stack_without_node_raises(tmp_docker_dir: Path) -> None:
    model = YamlRoot.model_validate(_two_stacks_same_name(tmp_docker_dir))
    with pytest.raises(KeyError, match="multiple locations"):
        docker_find.find(model, stack_name="app")


def test_ambiguous_stack_disambiguated_by_node(tmp_docker_dir: Path) -> None:
    model = YamlRoot.model_validate(_two_stacks_same_name(tmp_docker_dir))
    results = docker_find.find(model, stack_name="app", node_name="h2")
    assert len(results) == 1
    assert results[0].path == ["h2"]
