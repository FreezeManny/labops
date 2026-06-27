"""Tests for models/input_conf/vm.py — os handling and the unmanaged OS.

A VM running an appliance OS (e.g. HomeAssistant OS) is a real proxmox VM
(keeps its vmid) but can't be apt-updated or SSH-provisioned, so it carries
``os: unmanaged`` and must not declare management-only fields.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.vm import VM


def _base_vm(**extra: object) -> dict[str, Any]:
    base: dict[str, Any] = {"os": "debian", "ip": "10.0.0.3", "vmid": 201}
    base.update(extra)
    return base


# ── Managed VMs ───────────────────────────────────────────────────────────────


def test_managed_vm_is_valid() -> None:
    vm = VM.model_validate(_base_vm())
    assert vm.os == "debian"
    assert vm.vmid == 201


def test_vm_requires_os() -> None:
    with pytest.raises(ValidationError):
        VM.model_validate({"ip": "10.0.0.3", "vmid": 201})


# ── Unmanaged OS ──────────────────────────────────────────────────────────────
# (the forbid-management-fields behaviour is covered in test_managed.py)


def test_unmanaged_os_vm_is_valid() -> None:
    # A real proxmox VM (keeps vmid) running an appliance OS, still proxied.
    vm = VM.model_validate(
        {
            "os": "unmanaged",
            "ip": "10.0.0.3",
            "vmid": 201,
            "web_services": [{"port": 8123, "proxy_name": "home"}],
        }
    )
    assert vm.os == "unmanaged"
    assert vm.vmid == 201
    assert vm.web_services is not None


def test_unmanaged_os_vm_still_requires_vmid() -> None:
    with pytest.raises(ValidationError):
        VM.model_validate({"os": "unmanaged", "ip": "10.0.0.3"})
