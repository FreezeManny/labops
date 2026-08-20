"""Tests for src/wake/run.py — the two Ansible-driven wake paths.

Ansible is never invoked: ``run_playbook`` is monkeypatched to capture the
playbook, inventory and extravars it would have received. Mirrors
tests/dns/test_upgrade.py.

Both paths run against exactly one host, and in both the host is *not* the node
being woken — it is the relay (``--via``) or the Proxmox parent. That
indirection is what these assert on: getting it wrong would broadcast from, or
run ``qm start`` on, the wrong machine.

In ``wake_config_dict``: proxmox host ``prox`` (10.0.0.1) holds lxc ``ct1``
(10.0.0.2, vmid 101) and vm ``vm1`` (10.0.0.3, vmid 201); bare-metal ``edge`` is
10.0.0.4 and ``nas`` is 10.0.0.5.
"""

import importlib
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from models.input_conf.yaml_root import YamlRoot
from models.nodes import NodeRef
from src.utils.inventory import PCT_CONNECTION
from src.wake import DEFAULT_BROADCAST, DEFAULT_PORT, guest_cli, send_via, start_guest
from src.wake.find import resolve_wake_target

_module: ModuleType = importlib.import_module("src.wake.run")

MAC = "aa:bb:cc:dd:ee:01"


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    record: dict[str, Any] = {"called": False}

    def _stub(**kwargs: object) -> SimpleNamespace:
        record["called"] = True
        record.update(kwargs)
        return SimpleNamespace(rc=0)

    monkeypatch.setattr(_module, "run_playbook", _stub)
    return record


def _the_only_host(record: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The single inventory entry, as (alias, host_vars)."""
    hosts: dict[str, Any] = record["inventory"]["all"]["hosts"]
    assert len(hosts) == 1
    return next(iter(hosts.items()))


# ── guest_cli ─────────────────────────────────────────────────────────────────


def test_an_lxc_is_started_with_pct(wake_config: YamlRoot) -> None:
    assert guest_cli(resolve_wake_target(wake_config, "ct1")) == "pct"


def test_a_vm_is_started_with_qm(wake_config: YamlRoot) -> None:
    assert guest_cli(resolve_wake_target(wake_config, "vm1")) == "qm"


# ── send_via ──────────────────────────────────────────────────────────────────


def test_via_runs_the_packet_playbook(
    wake_config: YamlRoot, captured: dict[str, Any]
) -> None:
    send_via(wake_config, MAC, "edge")
    assert captured["playbook"] == "wake/packet.yml"


def test_via_targets_the_relay_not_the_woken_node(
    wake_config: YamlRoot, captured: dict[str, Any]
) -> None:
    """nas is the one being woken; edge is the machine that broadcasts for it."""
    send_via(wake_config, MAC, "edge")

    alias, host_vars = _the_only_host(captured)
    assert alias == "wake_relay_edge"
    assert host_vars["ansible_host"] == "10.0.0.4"


def test_via_passes_the_mac_broadcast_and_port(
    wake_config: YamlRoot, captured: dict[str, Any]
) -> None:
    send_via(wake_config, MAC, "edge", "10.0.0.255", 7)
    assert captured["extravars"] == {
        "wake_mac": MAC,
        "wake_broadcast": "10.0.0.255",
        "wake_port": 7,
    }


def test_via_defaults_match_the_local_packet_path(
    wake_config: YamlRoot, captured: dict[str, Any]
) -> None:
    """Relaying must not quietly change where the packet goes."""
    send_via(wake_config, MAC, "edge")
    assert captured["extravars"]["wake_broadcast"] == DEFAULT_BROADCAST
    assert captured["extravars"]["wake_port"] == DEFAULT_PORT


def test_via_an_lxc_relays_through_its_proxmox_node(
    wake_config: YamlRoot, captured: dict[str, Any]
) -> None:
    """A container needs no sshd: pct exec from the parent reaches it."""
    send_via(wake_config, MAC, "ct1")

    alias, host_vars = _the_only_host(captured)
    assert alias == "wake_relay_ct1"
    assert host_vars["ansible_connection"] == PCT_CONNECTION
    assert host_vars["ansible_host"] == "10.0.0.1"  # prox, not the container
    assert host_vars["proxmox_vmid"] == 101


def test_via_uses_the_relays_credentials(
    wake_config_dict: dict[str, Any], captured: dict[str, Any], tmp_ssh_key: Path
) -> None:
    wake_config_dict["hosts"]["edge"]["creds"] = {
        "username": "relayuser",
        "ssh_key_path": str(tmp_ssh_key),
    }
    config = YamlRoot.model_validate(wake_config_dict)

    send_via(config, MAC, "edge")
    assert _the_only_host(captured)[1]["ansible_user"] == "relayuser"


def test_via_falls_back_to_the_default_credentials(
    wake_config: YamlRoot, captured: dict[str, Any]
) -> None:
    send_via(wake_config, MAC, "edge")
    assert _the_only_host(captured)[1]["ansible_user"] == "ansible"


def test_an_unknown_via_raises_naming_the_setting(
    wake_config: YamlRoot, captured: dict[str, Any]
) -> None:
    with pytest.raises(ValueError) as excinfo:
        send_via(wake_config, MAC, "nope")

    assert "--via" in str(excinfo.value)
    assert not captured["called"]


def test_via_passes_dry_run_and_verbose_through(
    wake_config: YamlRoot, captured: dict[str, Any]
) -> None:
    """--dry-run must reach ansible as --check, as it does everywhere else."""
    send_via(wake_config, MAC, "edge", dry_run=True, verbose=True)
    assert captured["dry_run"] is True
    assert captured["verbose"] is True


# ── start_guest ───────────────────────────────────────────────────────────────


def test_starting_an_lxc_runs_pct_on_its_parent(
    wake_config: YamlRoot, captured: dict[str, Any]
) -> None:
    ref: NodeRef = resolve_wake_target(wake_config, "ct1")
    start_guest(wake_config, ref)

    alias, host_vars = _the_only_host(captured)
    assert captured["playbook"] == "wake/guest.yml"
    assert alias == "wake_parent_prox"
    assert host_vars["ansible_host"] == "10.0.0.1"
    assert captured["extravars"] == {"wake_cli": "pct", "wake_vmid": 101}


def test_starting_a_vm_runs_qm_on_its_parent(
    wake_config: YamlRoot, captured: dict[str, Any]
) -> None:
    ref: NodeRef = resolve_wake_target(wake_config, "vm1")
    start_guest(wake_config, ref)

    assert captured["extravars"] == {"wake_cli": "qm", "wake_vmid": 201}


def test_the_parent_is_reached_over_plain_ssh(
    wake_config: YamlRoot, captured: dict[str, Any]
) -> None:
    """Not the pct connection: qm/pct run *on* the node, not inside the guest."""
    ref: NodeRef = resolve_wake_target(wake_config, "ct1")
    start_guest(wake_config, ref)

    assert "ansible_connection" not in _the_only_host(captured)[1]


def test_starting_a_guest_uses_the_parents_credentials(
    wake_config_dict: dict[str, Any], captured: dict[str, Any]
) -> None:
    """The parent's, not the guest's — the guest is never connected to."""
    wake_config_dict["hosts"]["prox"]["creds"] = {
        "username": "root",
        "password": "s3cret",
    }
    config = YamlRoot.model_validate(wake_config_dict)

    start_guest(config, resolve_wake_target(config, "ct1"))

    host_vars: dict[str, Any] = _the_only_host(captured)[1]
    assert host_vars["ansible_user"] == "root"
    # guest.yml runs both tasks with become.
    assert host_vars["ansible_become_password"] == "s3cret"


def test_starting_a_guest_falls_back_to_the_default_credentials(
    wake_config: YamlRoot, captured: dict[str, Any]
) -> None:
    start_guest(wake_config, resolve_wake_target(wake_config, "ct1"))
    assert _the_only_host(captured)[1]["ansible_user"] == "ansible"


def test_a_bare_metal_host_cannot_be_started_as_a_guest(
    wake_config: YamlRoot, captured: dict[str, Any]
) -> None:
    """The CLI never routes a host here, but the error names the way out anyway."""
    ref: NodeRef = resolve_wake_target(wake_config, "nas")

    with pytest.raises(ValueError) as excinfo:
        start_guest(wake_config, ref)

    assert "not a Proxmox guest" in str(excinfo.value)
    assert "mac" in str(excinfo.value)
    assert not captured["called"]


def test_starting_a_guest_passes_dry_run_and_verbose_through(
    wake_config: YamlRoot, captured: dict[str, Any]
) -> None:
    ref: NodeRef = resolve_wake_target(wake_config, "ct1")
    start_guest(wake_config, ref, dry_run=True, verbose=True)

    assert captured["dry_run"] is True
    assert captured["verbose"] is True
