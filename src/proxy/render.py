import os
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from models.input_conf.yaml_root import YamlRoot
from models.input_conf.settings import Proxy
from models.proxy.route_result import RouteResult
from src.proxy.find import find_routes

# Repo layout: <root>/src/proxy/render.py -> <root>
_project_root: str = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
_TEMPLATE_DIR: str = os.path.join(_project_root, "ansible", "files", "proxy")
_TEMPLATE_NAME = "Caddyfile.j2"


def _dedup(nets: list) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for net in nets:
        s = str(net)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _resolve_acl(
    route: RouteResult, proxy: Proxy
) -> tuple[Optional[list[str]], Optional[list[str]]]:
    """
    Resolve a route's access to (accept_cidrs, deny_cidrs), unioning the referenced
    lists. Unset access falls back to the default list. Empty -> None (no rule).
    """
    names: list[str] = route.access if route.access else [proxy.default_access_list]
    accept: list = []
    deny: list = []
    for name in names:
        al = proxy.access_lists[name]
        accept.extend(al.accept or [])
        deny.extend(al.deny or [])
    return (_dedup(accept) or None, _dedup(deny) or None)


def _render_context(
    config: YamlRoot, routes: Optional[list[RouteResult]] = None
) -> dict:
    proxy = config.settings.proxy
    if proxy is None:
        raise ValueError("settings.proxy is not configured; cannot render a Caddyfile.")

    routes = find_routes(config) if routes is None else routes

    rendered_routes = []
    for r in routes:
        accept, deny = _resolve_acl(r, proxy)
        rendered_routes.append(
            {
                "name": r.proxy_name,
                "host": f"{r.proxy_name}{proxy.proxy_suffix}",
                "target": f"{r.target_ip}:{r.port}",
                "accept": accept,
                "deny": deny,
            }
        )
    return {
        "proxy_suffix": proxy.proxy_suffix,
        "routes": rendered_routes,
    }


def render_caddyfile(
    config: YamlRoot, routes: Optional[list[RouteResult]] = None
) -> str:
    """Render the full Caddyfile from the config's web_services + settings.proxy."""
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    template = env.get_template(_TEMPLATE_NAME)
    return template.render(**_render_context(config, routes))
