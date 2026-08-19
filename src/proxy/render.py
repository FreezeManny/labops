import os
from pathlib import Path
from typing import Optional

from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    PrefixLoader,
    StrictUndefined,
    Template,
    TemplateError,
)

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

# Prefix a custom template uses to reach the built-in one unambiguously, e.g.
# `{% extends "builtin/Caddyfile.j2" %}`. Needed because a custom template may
# itself be named Caddyfile.j2, in which case the bare name resolves to itself.
_BUILTIN_PREFIX = "builtin"


def _dedup(nets: list) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for net in nets:
        s = str(net)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def resolve_acl(
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

    * an inline token at all -> it is a secret that leaves the secret store and
      travels wherever the rendered Caddyfile goes;
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
    if inline_token is not None:
        # The inline token is rendered literally, so it ends up in whatever the
        # Caddyfile touches: the terminal on `proxy render`, any `-o` file, the
        # extravars ansible-runner writes under .ansible-autogenerate, and the
        # file on the target. `{env.<VAR>}` (the default) avoids all of that.
        out.append(
            f"proxy.tls: settings.proxy.tls.token is set inline and will be written "
            f"in clear text into the rendered Caddyfile — printed by `proxy render`, "
            f"saved by `-o`, and stored on the deploy target. Prefer removing it and "
            f"setting {spec.token_env} in Caddy's environment, which labops renders "
            f"as a {{env.{spec.token_env}}} placeholder instead."
        )
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
    """Build the variables a Caddyfile template is rendered with.

    This is the contract for ``settings.proxy.template``, so treat additions as
    additive and removals as breaking:

    * ``proxy_suffix`` — e.g. ``.example.com``; the site address is ``*`` + this.
    * ``tls_lines``   — directives for the ``tls`` block, or None when TLS is off
      (no ``tls:`` block, or ``provider: none``) and the site is plain HTTP.
    * ``tls_plugin``  — caddy-dns module the image needs, or None when TLS is off.
    * ``routes``      — one dict per routed web_service, each with:
        ``name``     matcher label (the validated proxy_name),
        ``host``     full hostname (name + proxy_suffix),
        ``target``   upstream, scheme included only when it speaks HTTPS,
        ``insecure`` True when the upstream's TLS cert must not be verified,
        ``accept``   allowed CIDRs as strings, or None for no restriction,
        ``deny``     blocked CIDRs as strings, or None.
    """
    proxy = config.settings.proxy
    if proxy is None:
        raise ValueError("settings.proxy is not configured; cannot render a Caddyfile.")

    routes = find_routes(config) if routes is None else routes
    spec: Optional[TlsProviderSpec] = _tls_spec(proxy)

    rendered_routes = []
    for r in routes:
        accept, deny = resolve_acl(r, proxy)
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


def _load_template(proxy: Proxy) -> Template:
    """Load the Caddyfile template: the built-in one, or ``settings.proxy.template``.

    A custom template's own directory is searched first, so its relative
    ``include``/``import`` paths work, with the built-in directory behind it and
    also mounted under ``builtin/``. That lets an override reuse the shipped
    structure — ``{% extends "builtin/Caddyfile.j2" %}`` plus a block or two —
    rather than restating the whole file, and the prefixed name stays
    unambiguous even when the custom template is itself called Caddyfile.j2.

    ``StrictUndefined``: a typo'd variable is an error, not a silently empty
    stretch of Caddyfile that only fails once it reaches the target.
    """
    search_dirs: list[str] = [_TEMPLATE_DIR]
    name: str = _TEMPLATE_NAME
    if proxy.template is not None:
        search_dirs.insert(0, str(proxy.template.parent))
        name = proxy.template.name

    env = Environment(
        loader=ChoiceLoader(
            [
                FileSystemLoader(search_dirs),
                PrefixLoader({_BUILTIN_PREFIX: FileSystemLoader(_TEMPLATE_DIR)}),
            ]
        ),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    return env.get_template(name)


def render_caddyfile(
    config: YamlRoot, routes: Optional[list[RouteResult]] = None
) -> str:
    """Render the full Caddyfile from the config's web_services + settings.proxy.

    The context handed to the template is fixed by ``_render_context`` and is the
    contract a custom ``settings.proxy.template`` writes against.
    """
    proxy = config.settings.proxy
    if proxy is None:
        raise ValueError("settings.proxy is not configured; cannot render a Caddyfile.")
    context: dict = _render_context(config, routes)

    try:
        return _load_template(proxy).render(**context)
    except TemplateError as e:
        # A broken custom template is a config problem, not a labops bug — report
        # it like one, with the file that caused it. ValueError is what the CLI
        # already turns into a clean message.
        where: str = (
            str(proxy.template)
            if proxy.template is not None
            else f"the built-in template ({_TEMPLATE_NAME})"
        )
        raise ValueError(f"could not render {where}: {e}") from e
