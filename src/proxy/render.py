import os
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from models.input_conf.yaml_root import YamlRoot
from models.input_conf.proxy import Proxy
from models.proxy.route_result import RouteResult
from src.proxy.find import find_routes
from src.proxy.tls_providers import TlsProviderSpec, spec_for
from src.utils.env_file import resolve_env_file, read_env_file

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


def _tls_spec(proxy: Proxy) -> Optional[TlsProviderSpec]:
    """The selected provider's Caddy details, or None when TLS is off.

    TLS is off in two ways — no ``tls`` block at all, or ``provider: none`` — and
    both collapse here so callers ask the question once, and the ``"none"``
    comparison lives in exactly one place.
    """
    if proxy.tls is None or proxy.tls.provider == "none":
        return None
    return spec_for(proxy.tls.provider)


def _tls_lines(token: Optional[str], spec: TlsProviderSpec) -> list[str]:
    """Render the provider's ``dns`` directive for placement in a ``tls`` block.

    An inline ``token`` is emitted literally; otherwise a ``{env.<TOKEN_ENV>}``
    placeholder is emitted for Caddy to resolve from its runtime environment.
    """
    secret = token if token is not None else f"{{env.{spec.token_env}}}"
    return [f"dns {spec.caddy_module} {secret}"]


def tls_warnings(config: YamlRoot, config_path: Path) -> list[str]:
    """Non-fatal checks on the selected provider's token source.

    labops can only see what's local — an inline ``tls.token`` and the ``.env``
    secret store — not the deploy target's own environment, so these are
    warnings, not errors:

    * no token in either place -> the DNS-01 challenge will fail unless the token
      reaches Caddy's environment some other way;
    * a token in *both* places that disagree -> the inline value wins on render,
      which is easy to do by accident.
    """
    proxy = config.settings.proxy
    if proxy is None:
        return []
    spec: Optional[TlsProviderSpec] = _tls_spec(proxy)
    if spec is None:  # TLS off -> no cert to provision, so no token to check.
        return []
    inline_token: Optional[str] = proxy.tls.token if proxy.tls else None
    env_path: Path = resolve_env_file(config_path, config.settings.env_file)
    file_token: Optional[str] = read_env_file(env_path).get(spec.token_env)

    out: list[str] = []
    if inline_token is None and file_token is None:
        out.append(
            f"proxy.tls: no TLS token found — none inline and {spec.token_env} is "
            f"not set in {env_path}. Caddy's DNS-01 challenge will fail unless the "
            f"token reaches the Caddy container's environment."
        )
    elif (
        inline_token is not None
        and file_token is not None
        and inline_token != file_token
    ):
        out.append(
            f"proxy.tls: the inline token differs from {spec.token_env} in "
            f"{env_path}; the inline value will be rendered into the Caddyfile."
        )
    return out


def _render_context(
    config: YamlRoot, routes: Optional[list[RouteResult]] = None
) -> dict:
    proxy = config.settings.proxy
    if proxy is None:
        raise ValueError("settings.proxy is not configured; cannot render a Caddyfile.")

    routes = find_routes(config) if routes is None else routes
    spec: Optional[TlsProviderSpec] = _tls_spec(proxy)

    rendered_routes = []
    for r in routes:
        accept, deny = _resolve_acl(r, proxy)
        scheme = "https://" if r.https else ""
        rendered_routes.append(
            {
                "name": r.proxy_name,
                "host": f"{r.proxy_name}{proxy.proxy_suffix}",
                "target": f"{scheme}{r.target_ip}:{r.port}",
                "insecure": r.https,
                "accept": accept,
                "deny": deny,
            }
        )
    return {
        "proxy_suffix": proxy.proxy_suffix,
        # Both None when TLS is off -> the template renders a plain-HTTP site.
        "tls_lines": (
            _tls_lines(proxy.tls.token if proxy.tls else None, spec) if spec else None
        ),
        # Recorded as a header comment: the image must carry this plugin, and
        # labops can't check that for you.
        "tls_plugin": spec.plugin if spec else None,
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
