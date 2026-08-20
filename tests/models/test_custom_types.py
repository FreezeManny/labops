"""Tests for models/input_conf/custom_types.py — OSType and Hypervisor literal rejection."""

import pytest
from pydantic import ValidationError

from models.input_conf.host import Host


def test_invalid_os_rejected() -> None:
    with pytest.raises(ValidationError):
        Host.model_validate({"os": "ubuntu", "ip": "10.0.0.1"})


def test_invalid_hypervisor_rejected() -> None:
    with pytest.raises(ValidationError):
        Host.model_validate({"hypervisor": "vmware", "os": "debian", "ip": "10.0.0.1"})


def test_bare_metal_is_no_longer_a_hypervisor() -> None:
    # The old spelling of "hosts no guests". Clean break: it fails as a literal
    # rather than being accepted as an alias for `none`.
    with pytest.raises(ValidationError):
        Host.model_validate(
            {"hypervisor": "bare-metal", "os": "debian", "ip": "10.0.0.1"}
        )
