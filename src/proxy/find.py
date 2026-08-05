from models.input_conf.yaml_root import YamlRoot
from models.proxy.route_result import RouteResult


def find_routes(config: YamlRoot) -> list[RouteResult]:
    """Return every reverse-proxy route at any nesting depth across all hosts.

    A web_service is routable only once it has a ``proxy_name`` — that is the
    hostname label — so entries without one stay in the config but are skipped
    here. The upstream is always the address of the node the service is reached
    at, docker stacks included: a stack's services are published on the docker
    host's own IP, which is why the stack name is not part of the path.
    """
    return [
        RouteResult(
            proxy_name=ref.web_service.proxy_name,
            target_ip=ref.node.ip,
            port=ref.web_service.port,
            access=ref.web_service.access,
            path=ref.path,
            https=ref.web_service.https,
        )
        for ref in config.iter_web_services()
        if ref.web_service.proxy_name is not None
    ]
