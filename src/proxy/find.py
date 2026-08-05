from typing import Union

from models.input_conf.yaml_root import YamlRoot
from models.input_conf.host import Host
from models.input_conf.lxc import LXC
from models.input_conf.vm import VM
from models.input_conf.web_services import WebServices
from models.proxy.route_result import RouteResult


def _collect(
    ws: WebServices | None,
    node: Union[Host, VM, LXC],
    path: list[str],
    routes: list[RouteResult],
) -> None:
    """Turn a node's web_services into routes, using the node's own IP as the upstream target."""
    if not ws:
        return
    for entry in ws.root:
        if entry.proxy_name is None:
            # Not routable without a hostname label — skip.
            continue
        routes.append(
            RouteResult(
                proxy_name=entry.proxy_name,
                target_ip=node.ip,
                port=entry.port,
                access=entry.access,
                path=list(path),
                https=entry.https,
            )
        )


def _walk(
    node: Union[Host, VM, LXC], path: list[str], routes: list[RouteResult]
) -> None:
    """Recursively collect routes from any node that can carry web_services/docker/vm/lxc."""
    _collect(getattr(node, "web_services", None), node, path, routes)

    # A docker stack's services are reached at the docker host's own IP.
    docker = getattr(node, "docker", None)
    if docker:
        for stack in docker.stacks.values():
            _collect(getattr(stack, "web_services", None), node, path, routes)

    for name, child in (getattr(node, "vm", None) or {}).items():
        _walk(child, path + [name], routes)
    for name, child in (getattr(node, "lxc", None) or {}).items():
        _walk(child, path + [name], routes)


def find_routes(config: YamlRoot) -> list[RouteResult]:
    """Return every reverse-proxy route at any nesting depth across all hosts."""
    routes: list[RouteResult] = []
    if config.hosts is None:
        return routes
    for host_name, host in config.hosts.items():
        _walk(host, [host_name], routes)
    return routes
