"""Tests for models/input_conf/custom_types.py — OSType and HostType literal rejection."""

import pytest
from pydantic import ValidationError

from models.input_conf.host import Host


def test_invalid_os_rejected() -> None:
    with pytest.raises(ValidationError):
        Host.model_validate({"os": "ubuntu", "ip": "10.0.0.1"})


def test_invalid_host_type_rejected() -> None:
    with pytest.raises(ValidationError):
        Host.model_validate({"type": "hypervisor", "os": "debian", "ip": "10.0.0.1"})
