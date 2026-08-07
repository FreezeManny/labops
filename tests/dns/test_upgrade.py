"""Tests for src/dns/upgrade.py — running Pi-hole's own updater over SSH.

Ansible is never invoked: ``run_playbook`` is monkeypatched to capture the inventory
and extravars it would have received. Mirrors tests/src/test_proxy_deploy.py, since
both resolve a named config node to a connection the same way
(src/utils/target.py).

The target is ``settings.dns.pihole_location`` — the same field the API uses. It may
be a bare IP of something outside the config, which is fine for records but has
nothing to SSH into, so the interesting cases here are the ones that refuse to run.

In ``valid_config_dict``: proxmox host ``prox`` (10.0.0.1) holds lxc ``ct1``
(10.0.0.2, vmid 101) and vm ``vm1`` (10.0.0.3); bare-metal ``edge`` is 10.0.0.4 and
``nas`` is 10.0.0.5 with ``os: unmanaged``.
"""

import importlib
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from models.input_conf.yaml_root import YamlRoot
from src.dns import upgrade_pihole
from src.utils.inventory import PCT_CONNECTION

_module: ModuleType = importlib.import_module("src.dns.upgrade")


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    record: dict[str, Any] = {"called": False}

    def _stub(**kwargs: object) -> SimpleNamespace:
        record["called"] = True
        record["playbook"] = kwargs.get("playbook")
        record["inventory"] = kwargs.get("inventory")
        record["extravars"] = kwargs.get("extravars")
        record["dry_run"] = kwargs.get("dry_run")
        record["verbose"] = kwargs.get("verbose")
        return SimpleNamespace(rc=0)

    monkeypatch.setattr(_module, "run_playbook", _stub)
    return record


def _config(cfg: dict[str, Any], location: str, **dns: object) -> YamlRoot:
    cfg["settings"]["dns"]["pihole_location"] = location
    cfg["settings"]["dns"].update(dns)
    return YamlRoot.model_validate(cfg)


def _host_vars(record: dict[str, Any]) -> dict[str, Any]:
    hosts = record["inventory"]["all"]["hosts"]
    assert len(hosts) == 1
    return next(iter(hosts.values()))


# ── Playbook and payload ──────────────────────────────────────────────────────


def test_uses_the_upgrade_playbook(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    upgrade_pihole(_config(dns_config_dict, "edge"))
    assert captured["playbook"] == "dns/upgrade.yml"


def test_default_command_is_the_pihole_updater(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    upgrade_pihole(_config(dns_config_dict, "edge"))
    assert captured["extravars"]["pihole_upgrade_command"] == "pihole -up"


def test_command_override_is_passed(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    upgrade_pihole(
        _config(dns_config_dict, "edge", upgrade_command="pihole -up --check-only")
    )
    assert (
        captured["extravars"]["pihole_upgrade_command"] == "pihole -up --check-only"
    )


def test_dry_run_and_verbose_are_forwarded(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    # --dry-run passes --check, under which ansible.builtin.command skips rather
    # than upgrading — so a dry run genuinely cannot upgrade anything.
    upgrade_pihole(_config(dns_config_dict, "edge"), dry_run=True, verbose=True)
    assert captured["dry_run"] is True
    assert captured["verbose"] is True


# ── Target resolution ─────────────────────────────────────────────────────────


def test_lxc_location_uses_pct_via_its_node(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    # The common real shape: Pi-hole in a container, reached through the Proxmox
    # node with no sshd inside it.
    upgrade_pihole(_config(dns_config_dict, "ct1"))
    host_vars = _host_vars(captured)
    assert host_vars["ansible_connection"] == PCT_CONNECTION
    assert host_vars["ansible_host"] == "10.0.0.1"  # the *node*, not the container
    assert host_vars["proxmox_vmid"] == 101


def test_bare_metal_location_uses_direct_ssh(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    upgrade_pihole(_config(dns_config_dict, "edge"))
    host_vars = _host_vars(captured)
    assert "ansible_connection" not in host_vars
    assert host_vars["ansible_host"] == "10.0.0.4"


def test_vm_location_uses_direct_ssh(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    upgrade_pihole(_config(dns_config_dict, "vm1"))
    assert _host_vars(captured)["ansible_host"] == "10.0.0.3"


def test_location_given_as_an_in_config_ip_resolves(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    # The same field works either way round — an IP that happens to name a node
    # still finds the node, so upgrading works without renaming anything.
    upgrade_pihole(_config(dns_config_dict, "10.0.0.2"))
    host_vars = _host_vars(captured)
    assert host_vars["ansible_connection"] == PCT_CONNECTION
    assert host_vars["proxmox_vmid"] == 101


def test_inventory_is_keyed_by_the_node_name(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    # So a failure names the Pi-hole rather than an opaque address.
    upgrade_pihole(_config(dns_config_dict, "10.0.0.2"))
    assert set(captured["inventory"]["all"]["hosts"]) == {"pihole_ct1"}


# ── Refusals ──────────────────────────────────────────────────────────────────


def test_off_config_ip_cannot_be_upgraded(dns_config_dict: dict[str, Any]) -> None:
    # A bare IP is a fine API endpoint, but there is no node behind it and so no
    # credentials to connect with. Records still work; only upgrading refuses.
    with pytest.raises(ValueError, match="is an address, not a node"):
        upgrade_pihole(_config(dns_config_dict, "10.0.0.53"))


def test_docker_stack_cannot_be_upgraded(dns_config_dict: dict[str, Any]) -> None:
    # `app` is the stack on vm1. Naming it is the user saying Pi-hole runs in a
    # container, so `pihole -up` is the wrong tool and labops says which is right.
    with pytest.raises(ValueError, match="is a docker stack"):
        upgrade_pihole(_config(dns_config_dict, "app"))


def test_docker_stack_refusal_points_at_the_right_command(
    dns_config_dict: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="docker stack --stack app update"):
        upgrade_pihole(_config(dns_config_dict, "app"))


def test_unmanaged_node_is_refused(dns_config_dict: dict[str, Any]) -> None:
    # `nas` is os: unmanaged — labops does not run commands on a box it is told it
    # does not manage, and failing here beats an SSH error halfway through.
    with pytest.raises(ValueError, match="os: unmanaged"):
        upgrade_pihole(_config(dns_config_dict, "nas"))


def test_unmanaged_refusal_says_how_to_fix_it(
    dns_config_dict: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="debian, alpine, redhat"):
        upgrade_pihole(_config(dns_config_dict, "nas"))


def test_unknown_location_raises(dns_config_dict: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="matches no host, VM, LXC or docker stack"):
        upgrade_pihole(_config(dns_config_dict, "nope"))


def test_missing_dns_block_raises(valid_config_dict: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="settings.dns is not configured"):
        upgrade_pihole(YamlRoot.model_validate(valid_config_dict))


def test_nothing_runs_when_a_refusal_fires(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    # The checks happen while the inventory is built, before the playbook is
    # invoked — so a refusal cannot half-run anything.
    with pytest.raises(ValueError):
        upgrade_pihole(_config(dns_config_dict, "nas"))
    assert captured["called"] is False


def test_nothing_runs_for_a_docker_stack(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        upgrade_pihole(_config(dns_config_dict, "app"))
    assert captured["called"] is False
