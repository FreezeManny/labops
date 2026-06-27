"""Validator shared by Host/VM/LXC for nodes whose OS is ``unmanaged``.

A node with ``os == "unmanaged"`` (an appliance like HomeAssistant OS, an
unsupported distro, or a box you don't own) is kept for ip/web_services but is
never updated or provisioned by labops. It therefore must not declare
management-only fields (docker stacks, nested lxc/vm) — labops cannot deploy to
a box it doesn't manage.
"""

from typing import TypeVar

from ..custom_types import UNMANAGED_OS

T = TypeVar("T")

# Fields that require labops to actively manage the node — disallowed when
# the OS is unmanaged.
_MANAGEMENT_FIELDS = ("docker", "lxc", "vm")


def forbid_management_fields_when_unmanaged(obj: T) -> T:
    if getattr(obj, "os", None) == UNMANAGED_OS:
        for field in _MANAGEMENT_FIELDS:
            if getattr(obj, field, None) is not None:
                raise ValueError(f"Field '{field}' is not allowed when os is 'unmanaged'")
    return obj
