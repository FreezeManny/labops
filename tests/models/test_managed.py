"""Tests for the shared unmanaged-OS validator (common_validators/managed.py).

The forbid-management-fields logic lives in one place and is reused by Host, VM
and LXC, so it's tested once directly here. A single parametrized test then
confirms each model actually wires it up.
"""

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from models.input_conf.common_validators.managed import (
    forbid_management_fields_when_unmanaged,
)
from models.input_conf.host import Host
from models.input_conf.lxc import LXC
from models.input_conf.vm import VM


def _node(os: str, **overrides: object) -> SimpleNamespace:
    fields: dict[str, Any] = {"os": os, "docker": None, "lxc": None, "vm": None}
    fields.update(overrides)
    return SimpleNamespace(**fields)


# ── The shared validator in isolation ─────────────────────────────────────────


def test_managed_os_allows_management_fields() -> None:
    node = _node("debian", docker={"x": 1}, lxc={"a": 1}, vm={"b": 1})
    assert forbid_management_fields_when_unmanaged(node) is node


def test_unmanaged_os_without_management_fields_passes() -> None:
    node = _node("unmanaged")
    assert forbid_management_fields_when_unmanaged(node) is node


@pytest.mark.parametrize("field", ["docker", "lxc", "vm"])
def test_unmanaged_os_rejects_management_field(field: str) -> None:
    node = _node("unmanaged", **{field: {"x": 1}})
    with pytest.raises(ValueError, match=f"'{field}' is not allowed when os is 'unmanaged'"):
        forbid_management_fields_when_unmanaged(node)


# ── Each model wires the validator ────────────────────────────────────────────


@pytest.mark.parametrize(
    "model_cls, base",
    [
        (Host, {"os": "unmanaged", "ip": "10.0.0.1"}),
        (VM, {"os": "unmanaged", "ip": "10.0.0.1", "vmid": 1}),
        (LXC, {"os": "unmanaged", "ip": "10.0.0.1", "vmid": 1}),
    ],
)
def test_models_reject_docker_when_unmanaged(
    model_cls: type[BaseModel], base: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError, match="not allowed when os is 'unmanaged'"):
        model_cls.model_validate({**base, "docker": {"root_path": "/srv", "stacks": {}}})
