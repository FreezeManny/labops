"""Tests for src/proxy/deploy.py — pushing the Caddyfile to the Caddy target.

Ansible is never invoked: ``run_playbook`` is monkeypatched to capture the
inventory and extravars it would have received. The deploy target is resolved
against the config, so a host/VM gets direct SSH and an LXC gets the pct
connection.
"""

import importlib
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from models.input_conf.yaml_root import YamlRoot
from src.proxy.deploy import deploy_proxy, sync_proxy, reload_proxy

_module: ModuleType = importlib.import_module("src.proxy.deploy")


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    record: dict[str, Any] = {"called": False}

    def _stub(**kwargs: object) -> SimpleNamespace:
        record["called"] = True
        record["playbook"] = kwargs.get("playbook")
        record["inventory"] = kwargs.get("inventory")
        record["extravars"] = kwargs.get("extravars")
        return SimpleNamespace(rc=0)

    monkeypatch.setattr(_module, "run_playbook", _stub)
    return record


def _config(deploy: dict[str, Any], base: dict[str, Any]) -> YamlRoot:
    base["settings"]["proxy"]["deploy"] = deploy
    return YamlRoot.model_validate(base)


def _host_vars(record: dict[str, Any]) -> dict[str, Any]:
    hosts = record["inventory"]["all"]["hosts"]
    assert len(hosts) == 1
    return next(iter(hosts.values()))


# In valid_config_dict: proxmox host `prox` (10.0.0.1) holds lxc `ct1`
# (10.0.0.2, vmid 101) and vm `vm1` (10.0.0.3); bare-metal `edge` is 10.0.0.4.


def test_host_target_uses_direct_ssh(
    captured: dict[str, Any], valid_config_dict: dict[str, Any]
) -> None:
    cfg = _config(
        {
            "target": "edge",
            "caddyfile_dest": "/srv/caddy/Caddyfile",
            "docker": {"container": "caddy"},
        },
        valid_config_dict,
    )
    deploy_proxy(cfg)

    assert captured["playbook"] == "proxy/deploy.yml"
    hv = _host_vars(captured)
    assert hv["ansible_host"] == "10.0.0.4"
    assert hv["ansible_user"] == "ansible"
    assert "ansible_connection" not in hv  # direct SSH, not pct
    assert hv["caddyfile_dest"] == "/srv/caddy/Caddyfile"

    ev = captured["extravars"]
    assert ev["caddy_mode"] == "docker"
    assert ev["caddy_container"] == "caddy"
    assert ev["caddy_container_config"] == "/etc/caddy/Caddyfile"
    assert "reverse_proxy" in ev["caddyfile_content"]


def test_vm_target_uses_direct_ssh(
    captured: dict[str, Any], valid_config_dict: dict[str, Any]
) -> None:
    cfg = _config(
        {"target": "vm1", "caddyfile_dest": "/etc/caddy/Caddyfile"},
        valid_config_dict,
    )
    deploy_proxy(cfg)
    hv = _host_vars(captured)
    assert hv["ansible_host"] == "10.0.0.3"
    assert "ansible_connection" not in hv


def test_lxc_target_uses_pct_via_node(
    captured: dict[str, Any], valid_config_dict: dict[str, Any]
) -> None:
    cfg = _config(
        {
            "target": "ct1",
            "caddyfile_dest": "/srv/caddy/Caddyfile",
            "docker": {"container": "caddy"},
        },
        valid_config_dict,
    )
    deploy_proxy(cfg)

    hv = _host_vars(captured)
    assert hv["ansible_connection"] == "community.proxmox.proxmox_pct_remote"
    assert hv["ansible_host"] == "10.0.0.1"  # the Proxmox node, not the container
    assert hv["proxmox_vmid"] == 101
    # No sudo password for pct — the container is entered as root.
    assert "ansible_become_password" not in hv


def test_lxc_target_matches_by_vmid(
    captured: dict[str, Any], valid_config_dict: dict[str, Any]
) -> None:
    cfg = _config(
        {
            "target": "101",  # ct1's vmid
            "caddyfile_dest": "/srv/caddy/Caddyfile",
            "docker": {"container": "caddy"},
        },
        valid_config_dict,
    )
    deploy_proxy(cfg)
    hv = _host_vars(captured)
    assert hv["proxmox_vmid"] == 101
    assert hv["ansible_connection"] == "community.proxmox.proxmox_pct_remote"


def test_host_mode_omits_container_vars(
    captured: dict[str, Any], valid_config_dict: dict[str, Any]
) -> None:
    cfg = _config(
        {"target": "edge", "caddyfile_dest": "/etc/caddy/Caddyfile"},
        valid_config_dict,
    )
    deploy_proxy(cfg)
    ev = captured["extravars"]
    assert ev["caddy_mode"] == "host"
    assert "caddy_container" not in ev
    assert "caddy_container_config" not in ev


def test_reload_command_override_passed_as_extravar(
    captured: dict[str, Any], valid_config_dict: dict[str, Any]
) -> None:
    cfg = _config(
        {
            "target": "edge",
            "caddyfile_dest": "/srv/caddy/Caddyfile",
            "docker": {},  # docker mode, but no container — the override reloads
            "reload_command": "docker compose exec caddy caddy reload",
        },
        valid_config_dict,
    )
    deploy_proxy(cfg)
    ev = captured["extravars"]
    assert ev["caddy_reload_command"] == "docker compose exec caddy caddy reload"
    assert "caddy_container" not in ev  # no container given; default not built


def test_no_reload_command_omits_extravar(
    captured: dict[str, Any], valid_config_dict: dict[str, Any]
) -> None:
    cfg = _config(
        {"target": "edge", "caddyfile_dest": "/etc/caddy/Caddyfile"},
        valid_config_dict,
    )
    deploy_proxy(cfg)
    assert "caddy_reload_command" not in captured["extravars"]


def test_sync_uses_sync_playbook(
    captured: dict[str, Any], valid_config_dict: dict[str, Any]
) -> None:
    cfg = _config(
        {
            "target": "edge",
            "caddyfile_dest": "/srv/caddy/Caddyfile",
            "docker": {"container": "caddy"},
        },
        valid_config_dict,
    )
    sync_proxy(cfg)
    assert captured["playbook"] == "proxy/sync.yml"


def test_reload_uses_reload_playbook_without_caddyfile(
    captured: dict[str, Any], valid_config_dict: dict[str, Any]
) -> None:
    cfg = _config(
        {
            "target": "edge",
            "caddyfile_dest": "/srv/caddy/Caddyfile",
            "docker": {"container": "caddy"},
        },
        valid_config_dict,
    )
    reload_proxy(cfg)

    assert captured["playbook"] == "proxy/reload.yml"
    ev = captured["extravars"]
    # Reload reuses the on-disk config — no Caddyfile is rendered or shipped.
    assert "caddyfile_content" not in ev
    assert ev["caddy_mode"] == "docker"
    assert ev["caddy_container"] == "caddy"


def test_unknown_target_raises(
    captured: dict[str, Any], valid_config_dict: dict[str, Any]
) -> None:
    cfg = _config(
        {"target": "nope", "caddyfile_dest": "/etc/caddy/Caddyfile"},
        valid_config_dict,
    )
    with pytest.raises(ValueError, match="matches no host, VM or LXC"):
        deploy_proxy(cfg)
    assert captured["called"] is False


def test_deploy_without_deploy_block_raises(
    captured: dict[str, Any], valid_config_dict: dict[str, Any]
) -> None:
    cfg = YamlRoot.model_validate(valid_config_dict)  # no deploy block
    with pytest.raises(ValueError, match="settings.proxy.deploy is not configured"):
        deploy_proxy(cfg)
    assert captured["called"] is False
