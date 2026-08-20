"""Tests for src/dns/upgrade.py and src/dns/pihole/upgrade.py.

Ansible is never invoked: ``run_playbook`` is monkeypatched to capture the
inventory it would have received. Mirrors tests/src/test_proxy_deploy.py, since
both resolve a named config node to a connection the same way
(src/utils/inventory.py).

Upgrading is a dispatch rather than part of ``DnsBackend``: not every server can
upgrade itself, and where one can the mechanism is entirely its own. So the two
halves tested here are the dispatch (which server, or a clear refusal) and
Pi-hole's own half (which node, or a clear refusal).

A target that names nothing is *not* here — that fails when the config loads, in
tests/models/test_yaml_root.py. What is left at run time are the two refusals that
depend on more than the name resolving: a container, and a node labops is told not
to manage.

In ``valid_config_dict``: proxmox host ``prox`` (10.0.0.1) holds lxc ``ct1``
(10.0.0.2, vmid 101) and vm ``vm1`` (10.0.0.3, running the docker stack ``app``);
bare-metal ``edge`` is 10.0.0.4 and ``nas`` is 10.0.0.5 with ``os: unmanaged``.
"""

import importlib
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from models.input_conf.yaml_root import YamlRoot
from src.dns import upgrade_dns
from src.utils.inventory import PCT_CONNECTION

_module: ModuleType = importlib.import_module("src.dns.pihole.upgrade")


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


def _config(cfg: dict[str, Any], **pihole: object) -> YamlRoot:
    cfg["settings"]["dns"]["pihole"] = pihole
    return YamlRoot.model_validate(cfg)


def _host_vars(record: dict[str, Any]) -> dict[str, Any]:
    hosts = record["inventory"]["all"]["hosts"]
    assert len(hosts) == 1
    return next(iter(hosts.values()))


# ── Playbook and payload ──────────────────────────────────────────────────────


def test_uses_the_upgrade_playbook(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    upgrade_dns(_config(dns_config_dict, target="edge"))
    assert captured["playbook"] == "dns/upgrade.yml"


def test_the_command_is_not_passed_in(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    """`pihole -up` lives in the playbook, beside the probe that assumes it.

    There is exactly one correct invocation — the playbook already checks that
    Pi-hole's own installer put `pihole` on PATH — so nothing configures it.
    """
    upgrade_dns(_config(dns_config_dict, target="edge"))
    assert not captured["extravars"]


def test_dry_run_and_verbose_are_forwarded(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    """--dry-run passes --check, under which ansible.builtin.command skips rather
    than upgrading — so a dry run genuinely cannot upgrade anything."""
    upgrade_dns(_config(dns_config_dict, target="edge"), dry_run=True, verbose=True)
    assert captured["dry_run"] is True
    assert captured["verbose"] is True


# ── Target resolution ─────────────────────────────────────────────────────────


def test_an_lxc_target_is_reached_with_pct_via_its_node(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    """The common real shape: Pi-hole in a container with no sshd inside it."""
    upgrade_dns(_config(dns_config_dict, target="ct1"))
    host_vars = _host_vars(captured)
    assert host_vars["ansible_connection"] == PCT_CONNECTION
    assert host_vars["ansible_host"] == "10.0.0.1"  # the *node*, not the container
    assert host_vars["proxmox_vmid"] == 101


def test_a_bare_metal_target_is_reached_over_ssh(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    upgrade_dns(_config(dns_config_dict, target="edge"))
    host_vars = _host_vars(captured)
    assert "ansible_connection" not in host_vars
    assert host_vars["ansible_host"] == "10.0.0.4"


def test_a_vm_target_is_reached_over_ssh(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    upgrade_dns(_config(dns_config_dict, target="vm1"))
    assert _host_vars(captured)["ansible_host"] == "10.0.0.3"


def test_a_target_given_as_an_ip_resolves_to_the_same_node(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    upgrade_dns(_config(dns_config_dict, target="10.0.0.2"))
    host_vars = _host_vars(captured)
    assert host_vars["ansible_connection"] == PCT_CONNECTION
    assert host_vars["proxmox_vmid"] == 101


def test_the_inventory_is_keyed_by_the_node_name(
    captured: dict[str, Any], dns_config_dict: dict[str, Any]
) -> None:
    """So a failure names the Pi-hole rather than an opaque address."""
    upgrade_dns(_config(dns_config_dict, target="10.0.0.2"))
    assert set(captured["inventory"]["all"]["hosts"]) == {"pihole_ct1"}


# ── Refusals ──────────────────────────────────────────────────────────────────


def test_a_containerised_pihole_is_refused(dns_config_dict: dict[str, Any]) -> None:
    """Writing `docker_stack:` is the user saying Pi-hole is containerised, so the
    refusal is something they declared rather than something labops guessed."""
    with pytest.raises(ValueError, match="is a docker stack"):
        upgrade_dns(_config(dns_config_dict, docker_stack="app"))


def test_the_container_refusal_points_at_the_right_command(
    dns_config_dict: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="docker stack --stack app update"):
        upgrade_dns(_config(dns_config_dict, docker_stack="app"))


def test_an_unmanaged_node_is_refused(dns_config_dict: dict[str, Any]) -> None:
    """labops does not run commands on a box it is told it does not manage, and
    refusing here beats an SSH failure halfway through that reads like a fault."""
    with pytest.raises(ValueError, match="os: unmanaged"):
        upgrade_dns(_config(dns_config_dict, target="nas"))


def test_the_unmanaged_refusal_says_how_to_fix_it(
    dns_config_dict: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="debian, alpine, redhat"):
        upgrade_dns(_config(dns_config_dict, target="nas"))


def test_no_dns_block_at_all(valid_config_dict: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="settings.dns is not configured"):
        upgrade_dns(YamlRoot.model_validate(valid_config_dict))


def test_a_suffix_with_no_server_has_nothing_to_upgrade(
    valid_config_dict: dict[str, Any],
) -> None:
    valid_config_dict["settings"]["dns"] = {"suffix": ".lab"}
    with pytest.raises(ValueError, match="names no DNS server"):
        upgrade_dns(YamlRoot.model_validate(valid_config_dict))


@pytest.mark.parametrize(
    "pihole", [{"target": "nas"}, {"docker_stack": "app"}], ids=["unmanaged", "stack"]
)
def test_nothing_runs_when_a_refusal_fires(
    captured: dict[str, Any], dns_config_dict: dict[str, Any], pihole: dict[str, str]
) -> None:
    """The checks happen while the inventory is built, before the playbook is
    invoked — so a refusal cannot half-run anything."""
    with pytest.raises(ValueError):
        upgrade_dns(_config(dns_config_dict, **pihole))
    assert captured["called"] is False
