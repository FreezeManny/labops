"""Upgrading the DNS server software itself.

Not part of ``DnsBackend``, because it is not something every server has: a
file-based backend has nothing to upgrade, and for the ones that do the mechanism
is entirely their own — Pi-hole runs its own installer over SSH. So this is a
dispatch, not an interface: each backend that can upgrade itself gets a branch, and
one that cannot says so plainly.

It exists as a command at all because ``host update`` / ``lxc update`` run the
package manager, and a DNS server installed from its own installer never appears
there.
"""

from ansible_runner import Runner

from models.input_conf.dns import Dns
from models.input_conf.yaml_root import YamlRoot
from src.dns.backend import require_dns
from src.dns.pihole import upgrade_pihole


def upgrade_dns(
    config: YamlRoot, dry_run: bool = False, verbose: bool = False
) -> Runner:
    """Upgrade the configured DNS server, or explain why it cannot be upgraded."""
    dns: Dns = require_dns(config)

    # One branch per server that can upgrade itself.
    if dns.pihole is not None:
        return upgrade_pihole(config, dns.pihole, dry_run=dry_run, verbose=verbose)

    raise ValueError(
        "settings.dns names no DNS server, so there is nothing to upgrade. Add a "
        "`pihole:` block naming the machine running it."
    )
