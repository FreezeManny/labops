"""Upgrading the Pi-hole software.

The odd one out in this package: everything else here talks to Pi-hole's REST API,
but there is no API endpoint that upgrades the installation, so this runs Pi-hole's
own updater over SSH (or pct, for an LXC) like the rest of labops.

It is also not covered by ``host update`` / ``lxc update``. Those run the package
manager, and Pi-hole installs from its own installer rather than a distro repo — so
a Pi-hole container can have every Debian package current while Pi-hole itself sits
at the version you installed.

The target is ``settings.dns.pihole_location``, the same field the API uses. That
field may be a bare IP of something outside the config, which is fine for records
but leaves nothing to SSH into — hence the checks in ``resolve_upgrade_target``.
"""

from ansible_runner import Runner

from models.input_conf.custom_types import UNMANAGED_OS
from models.input_conf.dns import Dns
from models.input_conf.yaml_root import YamlRoot
from src.dns.location import SETTING, PiholeLocation, resolve_location
from src.dns.sync import require_dns
from src.utils.ansible_runner import run_playbook
from src.utils.target import ResolvedTarget

# Inventory alias only (single-host run against the Pi-hole).
_ALIAS = "pihole"


def resolve_upgrade_target(config: YamlRoot) -> ResolvedTarget:
    """The node to upgrade, or a ValueError explaining why there isn't one.

    Three things have to hold that do not matter for records:

    * the location must not be a **docker stack** — `pihole -up` upgrades an
      installation, and a container is upgraded by pulling a new image;
    * it must be a **node in the config** — an off-config IP is a perfectly good API
      endpoint, but there are no credentials to SSH in with;
    * that node must not be ``os: unmanaged`` — labops does not run commands on a
      box it is told it does not manage, and the alternative is an SSH failure
      halfway through that reads like a network fault.

    The Docker case is reliable precisely because it is declared: naming the stack
    in ``pihole_location`` is the user saying Pi-hole is containerised, rather than
    labops inferring it from stack names.
    """
    dns: Dns = require_dns(config)
    location: PiholeLocation = resolve_location(config, dns)

    if location.is_stack:
        raise ValueError(
            f"{SETTING} '{location.target}' is a docker stack on {location.where}. "
            "`dns upgrade` runs Pi-hole's own updater, which does not apply to a "
            "container — pull a new image instead with `labops docker stack "
            f"--stack {location.target} update`."
        )
    if location.node is None:
        raise ValueError(
            f"{SETTING} '{location.target}' is an address, not a node in this "
            "config, so labops has no credentials to connect with. Add the Pi-hole "
            "host to the config and name it here to upgrade it."
        )
    if location.node.node.os == UNMANAGED_OS:
        raise ValueError(
            f"{SETTING} '{location.target}' resolves to a node with os: "
            f"{UNMANAGED_OS}, which labops does not run commands on. Give it a real "
            "os (debian, alpine, redhat) to let labops upgrade Pi-hole on it."
        )
    return location.node


def upgrade_pihole(
    config: YamlRoot, dry_run: bool = False, verbose: bool = False
) -> Runner:
    """Run Pi-hole's updater on the configured Pi-hole host."""
    dns: Dns = require_dns(config)
    resolved: ResolvedTarget = resolve_upgrade_target(config)
    inventory: dict = {
        "all": {"hosts": {f"{_ALIAS}_{resolved.node.name}": resolved.host_vars}}
    }
    return run_playbook(
        playbook="dns/upgrade.yml",
        inventory=inventory,
        extravars={"pihole_upgrade_command": dns.upgrade_command},
        dry_run=dry_run,
        verbose=verbose,
    )
