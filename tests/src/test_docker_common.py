"""Tests for src/docker/common.py — _build_multi_inventory inventory builder.

Exercises the pure dict-building logic without running Ansible.
"""

from ipaddress import IPv4Address
from pathlib import Path
from typing import Any

import pytest

from models.docker.stack_result import StackResult
from models.input_conf.creds import Creds
from models.input_conf.docker import StackEntry
from src.docker.common import _build_multi_inventory


def _key_creds(tmp_ssh_key: Path) -> Creds:
    return Creds.model_validate(
        {"username": "ansible", "ssh_key_path": str(tmp_ssh_key)}
    )


def _pass_creds() -> Creds:
    return Creds.model_validate({"username": "ansible", "password": "secret"})


def _stack(tmp_docker_dir: Path, name: str = "app") -> StackEntry:
    s = StackEntry.model_validate({"config_path": str(tmp_docker_dir)})
    s.name = name
    return s


def _result(
    tmp_docker_dir: Path,
    creds: Creds,
    *,
    stack_name: str = "app",
    ip: str = "10.0.0.5",
    docker_root: str = "/srv/docker",
) -> StackResult:
    return StackResult(
        path=["host"],
        target_ip=IPv4Address(ip),
        docker_root=docker_root,
        stack=_stack(tmp_docker_dir, stack_name),
        creds=creds,
    )


# ── Credential mapping ────────────────────────────────────────────────────────


def test_ssh_key_creds_set_key_file_not_password(
    tmp_ssh_key: Path, tmp_docker_dir: Path
) -> None:
    creds = _key_creds(tmp_ssh_key)
    inv = _build_multi_inventory([_result(tmp_docker_dir, creds)], creds)
    h = inv["all"]["hosts"]["app_10.0.0.5"]
    assert h["ansible_ssh_private_key_file"] == str(tmp_ssh_key)
    assert "ansible_password" not in h
    assert "ansible_become_password" not in h


def test_password_creds_set_password_not_key_file(tmp_docker_dir: Path) -> None:
    creds = _pass_creds()
    inv = _build_multi_inventory([_result(tmp_docker_dir, creds)], creds)
    h = inv["all"]["hosts"]["app_10.0.0.5"]
    assert h["ansible_password"] == "secret"
    assert h["ansible_become_password"] == "secret"
    assert "ansible_ssh_private_key_file" not in h


def test_ansible_user_comes_from_creds(tmp_docker_dir: Path) -> None:
    creds = _pass_creds()
    inv = _build_multi_inventory([_result(tmp_docker_dir, creds)], creds)
    assert inv["all"]["hosts"]["app_10.0.0.5"]["ansible_user"] == "ansible"


# ── Alias and host vars ───────────────────────────────────────────────────────


def test_alias_is_stack_name_and_ip(tmp_docker_dir: Path) -> None:
    creds = _pass_creds()
    inv = _build_multi_inventory(
        [_result(tmp_docker_dir, creds, stack_name="grafana", ip="192.168.1.10")], creds
    )
    assert "grafana_192.168.1.10" in inv["all"]["hosts"]


def test_ansible_host_is_target_ip(tmp_docker_dir: Path) -> None:
    creds = _pass_creds()
    inv = _build_multi_inventory([_result(tmp_docker_dir, creds, ip="10.1.2.3")], creds)
    assert inv["all"]["hosts"]["app_10.1.2.3"]["ansible_host"] == "10.1.2.3"


def test_compose_dest_strips_trailing_slash(tmp_docker_dir: Path) -> None:
    creds = _pass_creds()
    inv = _build_multi_inventory(
        [_result(tmp_docker_dir, creds, stack_name="myapp", docker_root="/data/")],
        creds,
    )
    assert inv["all"]["hosts"]["myapp_10.0.0.5"]["compose_dest"] == "/data/myapp"


def test_compose_src_is_stack_config_path(tmp_docker_dir: Path) -> None:
    creds = _pass_creds()
    inv = _build_multi_inventory([_result(tmp_docker_dir, creds)], creds)
    assert inv["all"]["hosts"]["app_10.0.0.5"]["compose_src"] == str(
        tmp_docker_dir.resolve()
    )


def test_stack_name_var_is_set(tmp_docker_dir: Path) -> None:
    creds = _pass_creds()
    inv = _build_multi_inventory(
        [_result(tmp_docker_dir, creds, stack_name="prometheus")], creds
    )
    assert inv["all"]["hosts"]["prometheus_10.0.0.5"]["stack_name"] == "prometheus"


# ── Multiple stacks ───────────────────────────────────────────────────────────


def test_multiple_stacks_produce_distinct_aliases(tmp_docker_dir: Path) -> None:
    creds = _pass_creds()
    results = [
        _result(tmp_docker_dir, creds, stack_name="a", ip="10.0.0.1"),
        _result(tmp_docker_dir, creds, stack_name="b", ip="10.0.0.2"),
    ]
    inv = _build_multi_inventory(results, creds)
    assert set(inv["all"]["hosts"]) == {"a_10.0.0.1", "b_10.0.0.2"}


def test_empty_results_produces_empty_hosts(tmp_docker_dir: Path) -> None:
    creds = _pass_creds()
    inv = _build_multi_inventory([], creds)
    assert inv["all"]["hosts"] == {}
