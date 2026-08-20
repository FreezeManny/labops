"""Upgrading the Pi-hole software.

The odd one out in this package: everything else here talks to Pi-hole's REST API,
but there is no API endpoint that upgrades the installation, so this runs Pi-hole's
own updater over SSH (or pct, for an LXC) like the rest of labops.

It is also not covered by ``host update`` / ``lxc update``. Those run the package
manager, and Pi-hole installs from its own installer rather than a distro repo — so
a Pi-hole container can have every Debian package current while Pi-hole itself sits
at the version you installed.

The target is the ``settings.dns.pihole`` block, the same one the API uses. It may
name a docker stack, or a node labops is told not to manage — both fine for records
but with nothing to run a command on — hence the checks in
``resolve_upgrade_target``. It is attempted rather than opted into: every failure is
decidable from the config, so refusing with a reason beats making everyone declare
something labops already knows.
"""

from ansible_runner import Runner

from models.input_conf.custom_types import UNMANAGED_OS
from models.input_conf.pihole import Pihole
from models.input_conf.yaml_root import YamlRoot
from src.dns.location import ServiceLocation, StackLocation
from src.dns.pihole.location import resolve_pihole_location
from src.utils.ansible_runner import run_playbook
from src.utils.inventory import NodeConnection

# Inventory alias only (single-host run against the Pi-hole).
_ALIAS = "pihole"


def _require_upgradable(location: ServiceLocation) -> NodeConnection:
    """The node to upgrade, or a ValueError explaining why there isn't one.

    Two things have to hold that do not matter for records:

    * the location must not be a **docker stack** — `pihole -up` upgrades an
      installation, and a container is upgraded by pulling a new image;
    * the node must not be ``os: unmanaged`` — labops does not run commands on a
      box it is told it does not manage, and the alternative is an SSH failure
      halfway through that reads like a network fault.

    The second is what a Pi-hole labops only publishes to looks like now that
    ``target:`` must name a node: declared and refused on its os, rather than an
    off-config address refused for having nothing behind it. Both cases are reliable
    precisely because they are declared — writing ``docker_stack:`` is the user
    saying Pi-hole is containerised, rather than labops inferring it from an address
    that a container and an installation share. The playbook still probes for the
    updater, which catches the remaining mistake — a containerised Pi-hole named
    with ``target:`` instead.
    """
    if isinstance(location, StackLocation):
        raise ValueError(
            f"{location.setting} '{location.target}' is a docker stack on "
            f"{location.where}. `dns upgrade` runs Pi-hole's own updater, which "
            "does not apply to a container — pull a new image instead with `labops "
            f"docker stack --stack {location.target} update`."
        )
    # Not a stack, so this is a NodeLocation and `location.node` is a node.
    if location.node.node.os == UNMANAGED_OS:
        raise ValueError(
            f"{location.setting} '{location.target}' resolves to a node with os: "
            f"{UNMANAGED_OS}, which labops does not run commands on. Give it a real "
            "os (debian, alpine, redhat) to let labops upgrade Pi-hole on it."
        )
    return location.node


def resolve_upgrade_target(config: YamlRoot, pihole: Pihole) -> NodeConnection:
    """The node ``dns upgrade`` would run on, or a ValueError saying why not."""
    return _require_upgradable(resolve_pihole_location(config, pihole))


def upgrade_pihole(
    config: YamlRoot, pihole: Pihole, dry_run: bool = False, verbose: bool = False
) -> Runner:
    """Run Pi-hole's updater on the configured Pi-hole host."""
    resolved: NodeConnection = resolve_upgrade_target(config, pihole)
    inventory: dict = {
        "all": {"hosts": {f"{_ALIAS}_{resolved.node.name}": resolved.host_vars}}
    }
    return run_playbook(
        playbook="dns/upgrade.yml",
        inventory=inventory,
        dry_run=dry_run,
        verbose=verbose,
    )
