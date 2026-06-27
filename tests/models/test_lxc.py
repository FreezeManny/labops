"""Tests for models/input_conf/lxc.py — os handling and the unmanaged OS.

An LXC running an unsupported distro (e.g. NixOS) keeps its ip/vmid/web_services
but can't be package-managed by labops, so it carries ``os: unmanaged``.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.lxc import LXC


def _base_lxc(**extra: object) -> dict[str, Any]:
    base: dict[str, Any] = {"os": "alpine", "ip": "10.0.0.2", "vmid": 101}
    base.update(extra)
    return base


def test_managed_lxc_is_valid() -> None:
    lxc = LXC.model_validate(_base_lxc())
    assert lxc.os == "alpine"
    assert lxc.vmid == 101


def test_lxc_requires_os() -> None:
    with pytest.raises(ValidationError):
        LXC.model_validate({"ip": "10.0.0.2", "vmid": 101})


def test_unmanaged_os_lxc_is_valid() -> None:
    # An unsupported-distro container (e.g. NixOS), still proxied.
    # (forbid-management-fields behaviour is covered in test_managed.py)
    lxc = LXC.model_validate(
        {
            "os": "unmanaged",
            "ip": "10.0.0.2",
            "vmid": 101,
            "web_services": [{"port": 8080, "proxy_name": "nix"}],
        }
    )
    assert lxc.os == "unmanaged"
    assert lxc.web_services is not None
