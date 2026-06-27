"""Tests for models/input_conf/host.py — proxmox gating, vmid + name handling."""

from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.host import Host


def _base_host(**extra: object) -> dict[str, Any]:
    base: dict[str, Any] = {"type": "proxmox", "os": "debian", "ip": "10.0.0.1"}
    base.update(extra)
    return base


def test_lxc_on_non_proxmox_rejected() -> None:
    data = _base_host(
        type="bare-metal",
        lxc={"ct1": {"os": "alpine", "ip": "10.0.0.2", "vmid": 101}},
    )
    with pytest.raises(ValidationError, match="only allowed when type is 'proxmox'"):
        Host.model_validate(data)


def test_vm_on_non_proxmox_rejected() -> None:
    data = _base_host(
        type="bare-metal",
        vm={"vm1": {"os": "debian", "ip": "10.0.0.3", "vmid": 201}},
    )
    with pytest.raises(ValidationError, match="only allowed when type is 'proxmox'"):
        Host.model_validate(data)


def test_lxc_and_vm_allowed_on_proxmox() -> None:
    data = _base_host(
        lxc={"ct1": {"os": "alpine", "ip": "10.0.0.2", "vmid": 101}},
        vm={"vm1": {"os": "debian", "ip": "10.0.0.3", "vmid": 201}},
    )
    host = Host.model_validate(data)
    assert host.lxc is not None and host.vm is not None


def test_duplicate_vmid_across_lxc_and_vm_rejected() -> None:
    data = _base_host(
        lxc={"ct1": {"os": "alpine", "ip": "10.0.0.2", "vmid": 100}},
        vm={"vm1": {"os": "debian", "ip": "10.0.0.3", "vmid": 100}},
    )
    with pytest.raises(ValidationError, match="Duplicate vmid found: 100"):
        Host.model_validate(data)


def test_propagate_lxc_and_vm_names() -> None:
    data = _base_host(
        lxc={"ct1": {"os": "alpine", "ip": "10.0.0.2", "vmid": 101}},
        vm={"vm1": {"os": "debian", "ip": "10.0.0.3", "vmid": 201}},
    )
    host = Host.model_validate(data)
    assert host.lxc is not None and host.lxc["ct1"].name == "ct1"
    assert host.vm is not None and host.vm["vm1"].name == "vm1"


# ── Unmanaged OS ──────────────────────────────────────────────────────────────
# (the forbid-management-fields behaviour is covered in test_managed.py)


def test_unmanaged_os_host_is_valid() -> None:
    # `os: unmanaged` is the catch-all for appliances (HAOS) / boxes you don't
    # manage. It still keeps ip + web_services; only update/setup skip it.
    host = Host.model_validate(
        {
            "os": "unmanaged",
            "ip": "10.0.0.1",
            "web_services": [{"port": 8123, "proxy_name": "home"}],
        }
    )
    assert host.os == "unmanaged"
    assert host.web_services is not None


def test_os_is_required() -> None:
    # Regression guard: `os` stays mandatory for every host.
    with pytest.raises(ValidationError):
        Host.model_validate({"type": "bare-metal", "ip": "10.0.0.1"})
