from models.dns.record import DnsRecord
from models.input_conf.dns import Dns
from models.nodes import node_dns_labels
from models.input_conf.yaml_root import YamlRoot


def find_records(config: YamlRoot) -> list[DnsRecord]:
    """Every local DNS record the config asks for, at any nesting depth.

    One record per published label per node: the node's own name, or each entry of
    its ``dns_name``. A node with ``dns: false`` contributes none. Unlike the proxy
    routes, this walks nodes rather than web_services — a record is about where a
    machine *is*, not what it serves, so a node with no services still gets one.

    Raises ValueError when ``settings.dns`` is absent, since there is no suffix to
    build hostnames from.
    """
    dns: Dns | None = config.settings.dns
    if dns is None:
        raise ValueError(
            "settings.dns is not configured; set local_dns_suffix and "
            "pihole_location to publish local DNS records."
        )

    return [
        DnsRecord(
            hostname=f"{label}.{dns.suffix}",
            ip=ref.node.ip,
            path=ref.path,
        )
        for ref in config.iter_nodes()
        for label in node_dns_labels(ref.node)
    ]
