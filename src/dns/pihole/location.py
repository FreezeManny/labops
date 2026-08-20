"""Binding ``settings.dns.pihole`` to the generic location resolver.

The lookup itself — a config node or a docker stack — is not Pi-hole's and lives in
src/dns/location.py. All that belongs here is which config
block those keys were read from, so a message quotes the key the user actually
wrote.

Takes the block rather than reaching for it through ``settings.dns``: whether
``settings.dns`` exists at all is the generic layer's check, and nothing in this
package should have to know about it. The *unset block* case is reported here, and
it is deliberately not a config-validation error — deriving records is useful on
its own, and ``dns list`` never comes through here.
"""

from typing import Optional

from models.input_conf.pihole import Pihole
from models.input_conf.yaml_root import YamlRoot
from src.dns.location import ServiceLocation, resolve_service_location

SETTING = "settings.dns.pihole"


def resolve_pihole_location(
    config: YamlRoot, pihole: Optional[Pihole]
) -> ServiceLocation:
    """Where Pi-hole is, per ``settings.dns.pihole``."""
    if pihole is None:
        raise ValueError(
            f"{SETTING} is not set, so labops does not know which Pi-hole to talk "
            "to. Add a `pihole:` block naming the node Pi-hole is installed on "
            "(`target:`, by name or IP) or the docker stack running it "
            "(`docker_stack:`). `dns list` works without it."
        )
    return resolve_service_location(
        config,
        setting=SETTING,
        target=pihole.target,
        docker_stack=pihole.docker_stack,
    )
